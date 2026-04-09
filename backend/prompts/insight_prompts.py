"""
Insight Prompt Templates
------------------------
All prompts used by the insight engine to query the LLM.
Prompts are grounded in pre-computed statistics — the LLM is only
allowed to interpret facts it has been explicitly given.

Design principles:
    - Every claim the LLM can make is backed by a number from EDA.
    - The LLM is instructed to cite the specific stat it references.
    - Sections are separated so the engine can call them independently.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are DataWeaver's data analyst assistant.
Your job is to generate clear, accurate, human-readable insights from
pre-computed statistical data about a dataset.

Rules you must follow:
1. Only make claims that are supported by the statistics you have been given.
2. Always cite the specific number, column name, or metric you are referencing.
3. Do not speculate about causes — only describe what the data shows.
4. Use plain English. Avoid jargon unless it is standard data terminology.
5. If a statistic is borderline (e.g. correlation r=0.51), say "moderate" not "strong".
6. Format your response as valid JSON matching the schema you are given.
7. Keep each insight concise — 1 to 2 sentences maximum.
"""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_overview_prompt(
    filename: str,
    overview: dict[str, Any],
    column_types: dict[str, list[str]],
) -> str:
    """Prompt for a high-level dataset summary.

    Returns a prompt string asking the LLM to describe the dataset
    in 3-5 bullet points.
    """
    return f"""You are analysing a dataset called "{filename}".

Dataset overview:
{json.dumps(overview, indent=2)}

Column classification:
- Numeric columns   : {column_types.get("numeric", [])}
- Categorical columns: {column_types.get("categorical", [])}
- Datetime columns  : {column_types.get("datetime", [])}
- Boolean columns   : {column_types.get("boolean", [])}

Task: Write a dataset overview with 3 to 5 bullet points.
Each bullet should highlight one meaningful fact about the dataset's
structure, completeness, or composition.

Respond with this JSON schema:
{{
  "overview": [
    {{"point": "<concise bullet point text>", "stat_referenced": "<the specific number or metric you used>"}}
  ]
}}"""


def build_statistics_prompt(summary: dict[str, Any]) -> str:
    """Prompt for interpreting summary statistics per column."""
    # Only send numeric columns to keep the prompt focused
    numeric_summary = {
        col: info for col, info in summary.items()
        if info.get("type") == "numeric"
    }

    return f"""You have the following summary statistics for numeric columns:
{json.dumps(numeric_summary, indent=2)}

Task: For each numeric column, write one insight that is meaningful to a business user.
Focus on: range, spread, skewness (if provided), or any column where nulls are high.

Respond with this JSON schema:
{{
  "statistics_insights": [
    {{
      "column": "<column name>",
      "insight": "<1-2 sentence insight>",
      "stat_referenced": "<specific number cited>"
    }}
  ]
}}"""


def build_correlation_prompt(correlations: dict[str, Any]) -> str:
    """Prompt for interpreting correlation results."""
    strong_pairs = correlations.get("strong_pairs", [])

    if not strong_pairs:
        return ""

    return f"""The following statistically significant correlations were found
(threshold: |r| >= {correlations.get("threshold", 0.5)}):

{json.dumps(strong_pairs, indent=2)}

Task: For each correlated pair, explain what the relationship means in plain English.
Use the exact r value to qualify the strength. Do not imply causation.

Respond with this JSON schema:
{{
  "correlation_insights": [
    {{
      "col_a": "<column A>",
      "col_b": "<column B>",
      "r": <correlation coefficient as number>,
      "insight": "<1-2 sentence interpretation>",
      "direction": "positive" | "negative"
    }}
  ]
}}"""


def build_distribution_prompt(distributions: dict[str, Any]) -> str:
    """Prompt for interpreting distribution shapes and outliers."""
    # Flag only columns with notable skew or significant outliers
    notable = {
        col: info for col, info in distributions.items()
        if abs(info.get("skewness", 0)) >= 0.5
        or info.get("outlier_pct", 0) >= 5
    }

    if not notable:
        return ""

    return f"""The following numeric columns have notable distribution characteristics:
{json.dumps(notable, indent=2)}

Task: For each column, write one insight about its distribution shape or outlier situation.
If skewness is present, explain what it means practically (e.g. most values are low,
but a few extreme values pull the average up).
If outliers are present, note their percentage and potential impact on analysis.

Respond with this JSON schema:
{{
  "distribution_insights": [
    {{
      "column": "<column name>",
      "insight": "<1-2 sentence insight>",
      "skew_label": "<approximately symmetric | moderately skewed | highly skewed (right|left)>",
      "outlier_pct": <number>
    }}
  ]
}}"""


def build_categorical_prompt(categorical: dict[str, Any]) -> str:
    """Prompt for interpreting categorical column distributions."""
    # Exclude the internal _hierarchies key
    cat_data = {k: v for k, v in categorical.items() if not k.startswith("_")}

    if not cat_data:
        return ""

    # Trim value_counts to top 5 to keep prompt short
    trimmed = {}
    for col, info in cat_data.items():
        trimmed[col] = {
            **info,
            "value_counts": dict(list(info.get("value_counts", {}).items())[:5]),
        }

    hierarchies = categorical.get("_hierarchies", [])

    return f"""The following categorical columns were analysed:
{json.dumps(trimmed, indent=2)}

{"Detected column hierarchies: " + json.dumps(hierarchies) if hierarchies else ""}

Task: For each categorical column write one insight about its distribution.
Highlight dominant categories, imbalances, or interesting hierarchical relationships.

Respond with this JSON schema:
{{
  "categorical_insights": [
    {{
      "column": "<column name>",
      "insight": "<1-2 sentence insight>",
      "dominant_value": "<most frequent value or null>",
      "dominant_pct": <percentage as number or null>
    }}
  ]
}}"""


def build_timeseries_prompt(time_series: dict[str, Any]) -> str:
    """Prompt for interpreting time series columns."""
    if not time_series:
        return ""

    return f"""The following time series columns were detected:
{json.dumps(time_series, indent=2)}

Task: For each time series column, write one insight about the temporal
coverage, frequency, and any gaps detected.

Respond with this JSON schema:
{{
  "timeseries_insights": [
    {{
      "column": "<column name>",
      "insight": "<1-2 sentence insight>",
      "frequency": "<inferred frequency>",
      "has_gaps": <true | false>
    }}
  ]
}}"""


def build_anomaly_prompt(
    summary: dict[str, Any],
    distributions: dict[str, Any],
) -> str:
    """Prompt for flagging anomalies and data quality issues."""
    quality_flags = []

    for col, info in summary.items():
        null_pct = info.get("null_pct", 0)
        if null_pct >= 20:
            quality_flags.append({
                "column": col,
                "issue": "high_nulls",
                "detail": f"{null_pct}% missing values",
            })

    for col, info in distributions.items():
        outlier_pct = info.get("outlier_pct", 0)
        if outlier_pct >= 10:
            quality_flags.append({
                "column": col,
                "issue": "high_outliers",
                "detail": f"{outlier_pct}% outliers by IQR method",
            })

    if not quality_flags:
        return ""

    return f"""The following data quality issues were detected:
{json.dumps(quality_flags, indent=2)}

Task: For each issue, write a concise recommendation for how an analyst
should handle it before building models or dashboards.

Respond with this JSON schema:
{{
  "anomaly_insights": [
    {{
      "column": "<column name>",
      "issue": "<issue type>",
      "recommendation": "<1-2 sentence recommendation>"
    }}
  ]
}}"""
