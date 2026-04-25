"""
Insight Engine — NVIDIA NIM (OpenAI-compatible)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

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

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _get_client() -> OpenAI:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise EnvironmentError("NVIDIA_API_KEY is not set. Add it to your .env file.")
    return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)


def generate_insights(
    eda_result: dict[str, Any],
    filename: str,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    model_name = model or os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")

    sections = {
        "overview":      (build_overview_prompt(filename, eda_result["dataset_overview"], eda_result["column_types"]), "overview"),
        "statistics":    (build_statistics_prompt(eda_result["summary"]), "statistics_insights"),
        "correlations":  (build_correlation_prompt(eda_result["correlations"]), "correlation_insights"),
        "distributions": (build_distribution_prompt(eda_result["distributions"]), "distribution_insights"),
        "categorical":   (build_categorical_prompt(eda_result["categorical"]), "categorical_insights"),
        "time_series":   (build_timeseries_prompt(eda_result["time_series"]), "timeseries_insights"),
        "anomalies":     (build_anomaly_prompt(eda_result["summary"], eda_result["distributions"]), "anomaly_insights"),
    }

    results: dict[str, Any] = {}
    meta: dict[str, Any] = {"model": model_name, "failed_sections": []}

    for section_name, (prompt, expected_key) in sections.items():
        if not prompt:
            results[section_name] = []
            continue
        try:
            raw = _call_llm(prompt, model_name)
            results[section_name] = _parse_response(raw, expected_key)
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
    model_name = model or os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")
    try:
        raw = _call_llm(prompt_text, model_name)
        return _parse_response(raw, expected_key)
    except Exception as exc:
        logger.warning("Single insight generation failed: %s", exc)
        return []


def _call_llm(user_prompt: str, model_name: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=1024,
    )
    return response.choices[0].message.content or ""


def _parse_response(raw: str, expected_key: str) -> list[dict] | dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON: {exc}") from exc

    if expected_key not in parsed:
        for value in parsed.values():
            if isinstance(value, (list, dict)):
                return value
        raise ValueError(f"Expected key '{expected_key}' not found. Got: {list(parsed.keys())}")

    return parsed[expected_key]


def validate_correlation_claims(
    insights: list[dict],
    strong_pairs: list[dict],
    threshold: float = 0.5,
) -> list[dict]:
    pair_map = {(p["col_a"], p["col_b"]): p["r"] for p in strong_pairs}
    pair_map.update({(p["col_b"], p["col_a"]): p["r"] for p in strong_pairs})
    validated = []
    for insight in insights:
        col_a, col_b = insight.get("col_a"), insight.get("col_b")
        actual_r = pair_map.get((col_a, col_b))
        if actual_r is None:
            continue
        claimed_r = insight.get("r")
        if claimed_r is not None and abs(float(claimed_r) - actual_r) > 0.05:
            insight["r"] = actual_r
        if abs(actual_r) >= threshold:
            validated.append(insight)
    return validated


def validate_null_claims(insights: list[dict], summary: dict[str, Any]) -> list[dict]:
    for insight in insights:
        col = insight.get("column")
        if col and col in summary:
            insight["actual_null_pct"] = summary[col].get("null_pct", 0)
    return insights
