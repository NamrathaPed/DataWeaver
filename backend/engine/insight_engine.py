"""
Insight Engine Module
---------------------
Calls the Gemini API with pre-computed EDA statistics and returns
structured, validated insights.

Design:
    - Each insight section (overview, correlations, distributions, etc.)
      is a separate LLM call with a focused prompt. This keeps context
      short and parsing simple.
    - All prompts are grounded — the LLM only sees numbers from EDA.
    - JSON responses are validated before being returned to the caller.
    - Falls back gracefully if any section fails.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import google.generativeai as genai
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

_model: genai.GenerativeModel | None = None


def _get_model(model_name: str) -> genai.GenerativeModel:
    global _model
    # Re-create if model name changed
    if _model is None or getattr(_model, "_model_name", None) != model_name:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY is not set. Add it to your .env file."
            )
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )
        _model._model_name = model_name  # type: ignore[attr-defined]
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_insights(
    eda_result: dict[str, Any],
    filename: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate all insight sections for a dataset."""
    model_name = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")

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
    meta: dict[str, Any] = {"model": model_name, "failed_sections": []}

    for section_name, (prompt, expected_key) in sections.items():
        if not prompt:
            results[section_name] = []
            continue

        try:
            raw = _call_llm(prompt, model_name)
            parsed = _parse_response(raw, expected_key)
            results[section_name] = parsed
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
) -> list[dict]:
    """Generate a single insight section from a custom prompt."""
    model_name = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
    try:
        raw = _call_llm(prompt_text, model_name)
        return _parse_response(raw, expected_key)
    except Exception as exc:
        logger.warning("Single insight generation failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm(user_prompt: str, model_name: str) -> str:
    """Call the Gemini API and return the raw response text."""
    gemini_model = _get_model(model_name)
    response = gemini_model.generate_content(user_prompt)
    return response.text or ""


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

def _parse_response(raw: str, expected_key: str) -> list[dict] | dict:
    """Parse and lightly validate the LLM JSON response."""
    # Strip markdown code fences if Gemini wraps in ```json ... ```
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON response: {exc}") from exc

    if expected_key not in parsed:
        # Try one level deeper
        for value in parsed.values():
            if isinstance(value, (list, dict)):
                return value
        raise ValueError(
            f"Expected key '{expected_key}' not found. Got: {list(parsed.keys())}"
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
    """Cross-check LLM correlation insights against actual computed r values."""
    pair_map = {(p["col_a"], p["col_b"]): p["r"] for p in strong_pairs}
    pair_map.update({(p["col_b"], p["col_a"]): p["r"] for p in strong_pairs})

    validated = []
    for insight in insights:
        col_a = insight.get("col_a")
        col_b = insight.get("col_b")
        claimed_r = insight.get("r")

        actual_r = pair_map.get((col_a, col_b))
        if actual_r is None:
            logger.warning(
                "LLM claimed correlation (%s, %s) not in strong_pairs — removed.",
                col_a, col_b,
            )
            continue

        if claimed_r is not None and abs(float(claimed_r) - actual_r) > 0.05:
            insight["r"] = actual_r

        if abs(actual_r) < threshold:
            continue

        validated.append(insight)

    return validated


def validate_null_claims(
    insights: list[dict],
    summary: dict[str, Any],
) -> list[dict]:
    """Ensure anomaly insights about null percentages are accurate."""
    for insight in insights:
        col = insight.get("column")
        if col and col in summary:
            insight["actual_null_pct"] = summary[col].get("null_pct", 0)
    return insights
