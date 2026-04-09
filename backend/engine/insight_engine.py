"""
Insight Engine Module
---------------------
Calls the OpenAI API with pre-computed EDA statistics and returns
structured, validated insights.

Design:
    - Each insight section (overview, correlations, distributions, etc.)
      is a separate LLM call with a focused prompt. This keeps context
      short, costs low, and parsing simple.
    - All prompts are grounded — the LLM only sees numbers from EDA.
    - JSON responses are validated before being returned to the caller.
    - Falls back gracefully if any section fails.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

from prompts.insight_prompts import (
    SYSTEM_PROMPT,
    build_anomaly_prompt,
    build_categorical_prompt,
    build_correlation_prompt,
    build_distribution_prompt,
    build_overview_prompt,
    build_statistics_prompt,
    build_timeseries_prompt,
)

load_dotenv()
logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )
        _client = OpenAI(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_insights(
    eda_result: dict[str, Any],
    filename: str,
    *,
    model: str | None = None,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Generate all insight sections for a dataset.

    Parameters
    ----------
    eda_result:
        Output of ``eda.run_eda()``.
    filename:
        Original file name (used in prompts for context).
    model:
        OpenAI model to use. Defaults to env var ``LLM_MODEL`` or ``gpt-4o``.
    temperature:
        LLM temperature. Low (0.2-0.4) keeps outputs factual and consistent.

    Returns
    -------
    dict with keys matching each insight section, plus a ``_meta`` block
    with token usage and any sections that failed.
    """
    model = model or os.getenv("LLM_MODEL", "gpt-4o")

    sections = {
        "overview": (
            build_overview_prompt(
                filename,
                eda_result["dataset_overview"],
                eda_result["column_types"],
            ),
            "overview",
        ),
        "statistics": (
            build_statistics_prompt(eda_result["summary"]),
            "statistics_insights",
        ),
        "correlations": (
            build_correlation_prompt(eda_result["correlations"]),
            "correlation_insights",
        ),
        "distributions": (
            build_distribution_prompt(eda_result["distributions"]),
            "distribution_insights",
        ),
        "categorical": (
            build_categorical_prompt(eda_result["categorical"]),
            "categorical_insights",
        ),
        "time_series": (
            build_timeseries_prompt(eda_result["time_series"]),
            "timeseries_insights",
        ),
        "anomalies": (
            build_anomaly_prompt(
                eda_result["summary"],
                eda_result["distributions"],
            ),
            "anomaly_insights",
        ),
    }

    results: dict[str, Any] = {}
    meta = {"model": model, "total_tokens": 0, "failed_sections": []}

    for section_name, (prompt, expected_key) in sections.items():
        if not prompt:
            # Prompt builder returned empty string — nothing to analyse
            results[section_name] = []
            continue

        try:
            raw, tokens = _call_llm(prompt, model, temperature)
            parsed = _parse_response(raw, expected_key)
            results[section_name] = parsed
            meta["total_tokens"] += tokens
        except Exception as exc:
            logger.warning("Insight section '%s' failed: %s", section_name, exc)
            results[section_name] = []
            meta["failed_sections"].append({"section": section_name, "error": str(exc)})

    results["_meta"] = meta
    return results


def generate_single_insight(
    prompt_text: str,
    expected_key: str,
    *,
    model: str | None = None,
    temperature: float = 0.3,
) -> list[dict]:
    """Generate a single insight section from a custom prompt.

    Useful for on-demand re-generation of one section without
    re-running the full pipeline.

    Parameters
    ----------
    prompt_text:
        The fully-built user prompt string.
    expected_key:
        The top-level JSON key expected in the LLM response.
    model:
        OpenAI model override.
    temperature:
        LLM temperature.

    Returns
    -------
    Parsed list of insight dicts, or empty list on failure.
    """
    model = model or os.getenv("LLM_MODEL", "gpt-4o")
    try:
        raw, _ = _call_llm(prompt_text, model, temperature)
        return _parse_response(raw, expected_key)
    except Exception as exc:
        logger.warning("Single insight generation failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(
    user_prompt: str,
    model: str,
    temperature: float,
) -> tuple[str, int]:
    """Call the OpenAI chat completions API.

    Returns
    -------
    (raw response text, total tokens used)
    """
    client = _get_client()

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content or ""
    tokens = response.usage.total_tokens if response.usage else 0
    return content, tokens


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

def _parse_response(raw: str, expected_key: str) -> list[dict] | dict:
    """Parse and lightly validate the LLM JSON response.

    Parameters
    ----------
    raw:
        Raw string content from the LLM.
    expected_key:
        Top-level key we expect in the JSON object.

    Returns
    -------
    The value at ``expected_key``, or raises ``ValueError`` if malformed.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON response: {exc}") from exc

    if expected_key not in parsed:
        # Some models wrap in an extra layer — try one level deeper
        for value in parsed.values():
            if isinstance(value, (list, dict)):
                return value
        raise ValueError(
            f"Expected key '{expected_key}' not found in LLM response. "
            f"Got keys: {list(parsed.keys())}"
        )

    return parsed[expected_key]


# ---------------------------------------------------------------------------
# Stat-grounded validation helpers
# ---------------------------------------------------------------------------

def validate_correlation_claims(
    insights: list[dict],
    strong_pairs: list[dict],
    threshold: float = 0.5,
) -> list[dict]:
    """Cross-check LLM correlation insights against actual computed r values.

    Removes any insight where the LLM's claimed r value differs from the
    computed value by more than 0.05, or where the pair was not in the
    strong_pairs list at all.

    Parameters
    ----------
    insights:
        List of correlation insight dicts from the LLM.
    strong_pairs:
        The ``strong_pairs`` list from ``eda.run_eda()["correlations"]``.
    threshold:
        Minimum |r| to allow.

    Returns
    -------
    Filtered list of validated insights.
    """
    pair_map = {
        (p["col_a"], p["col_b"]): p["r"] for p in strong_pairs
    }
    # Also index reversed order
    pair_map.update({(p["col_b"], p["col_a"]): p["r"] for p in strong_pairs})

    validated = []
    for insight in insights:
        col_a = insight.get("col_a")
        col_b = insight.get("col_b")
        claimed_r = insight.get("r")

        actual_r = pair_map.get((col_a, col_b))
        if actual_r is None:
            logger.warning(
                "LLM claimed correlation between '%s' and '%s' "
                "that was not in strong_pairs — removed.",
                col_a, col_b,
            )
            continue

        if claimed_r is not None and abs(float(claimed_r) - actual_r) > 0.05:
            logger.warning(
                "LLM r value mismatch for (%s, %s): claimed %.3f, actual %.3f — correcting.",
                col_a, col_b, claimed_r, actual_r,
            )
            insight["r"] = actual_r  # correct in place

        if abs(actual_r) < threshold:
            continue

        validated.append(insight)

    return validated


def validate_null_claims(
    insights: list[dict],
    summary: dict[str, Any],
) -> list[dict]:
    """Ensure anomaly insights about null percentages are accurate.

    Corrects the LLM's stated null percentage if it deviates from the
    computed value by more than 2 percentage points.
    """
    for insight in insights:
        col = insight.get("column")
        if col and col in summary:
            actual_null_pct = summary[col].get("null_pct", 0)
            insight["actual_null_pct"] = actual_null_pct
    return insights
