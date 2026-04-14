"""
Agent Engine
------------
Agentic data analysis loop using NVIDIA NIM (OpenAI-compatible API).
Uses a JSON text-based tool-call loop that works with any chat model.

Event types emitted:
  {"type": "thinking",    "text": "..."}
  {"type": "tool_call",   "tool": "...", "args": {...}}
  {"type": "tool_result", "tool": "...", "summary": "..."}
  {"type": "chart",       "figure": {...}, "title": "..."}
  {"type": "finding",     "headline": "...", "detail": "...", "stat": "..."}
  {"type": "report",      "markdown": "..."}
  {"type": "done"}
  {"type": "error",       "message": "..."}
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncGenerator

import numpy as np
import pandas as pd
from openai import OpenAI
from scipy import stats as scipy_stats

from engine.chart_engine import generate_single_chart

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are DataWeaver, an expert AI data analyst — a senior data scientist who is \
methodical, curious, and always grounds every conclusion in actual numbers.

━━━ TOOLS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- get_dataset_overview   — no args; ALWAYS call this first
- get_column_stats       — {"columns": ["col1", "col2"]}
- get_value_distribution — {"column": "col_name", "top_n": 20}
- filter_and_group       — {"group_by": "col", "value_column": "col", \
"agg": "mean|sum|count|median|max|min", "filter_col": "(optional)", "filter_val": "(optional)"}
- run_correlation        — {"col_a": "col", "col_b": "col"}
- run_linear_regression  — {"target": "col", "features": ["col1", "col2"]}
- generate_chart         — {"chart_type": "bar|histogram|line|scatter|box", \
"title": "...", "col": "col_name", "col_a": "col_name", "col_b": "col_name"}
- write_finding          — {"headline": "...", "detail": "...", "stat": "..."}
- write_response         — {"content": "..."} — conversational reply only

━━━ HOW TO CALL A TOOL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Respond with ONLY this JSON — nothing before or after it:
{"action": "tool_name", "args": {...}}

━━━ HOW TO FINISH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When analysis is complete, write a final markdown report starting with "## ".
The report MUST be comprehensive — include a dedicated section for each chart \
you generated, explaining what the chart shows and what it means for the data.

━━━ ANALYSIS APPROACH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Always call get_dataset_overview first (required before any analysis)
2. INTRO/GREETING requests (e.g. "introduce", "tell me about", "what's in this"):
   - Call get_dataset_overview only
   - Then write_response with 3-4 interesting observations + one question
   - Do NOT generate charts or run a full analysis
3. ANALYSIS/VISUALISATION requests: follow the CHART-FIRST PATTERN below
4. For regression: run_linear_regression when asked about "what predicts X", \
   "what drives X", "factors affecting X"
5. Use run_correlation before scatter charts to confirm relationship exists
6. Always cite specific numbers — never state findings without tool evidence

━━━ CHART-FIRST PATTERN (for any visualisation or analysis request) ━━━━━━━━

When the user asks for charts, visualisations, or a comprehensive analysis:

  STEP A — Explore the data with get_dataset_overview + get_column_stats
  STEP B — For EACH insight you want to visualise:
            1. Run the supporting tool (filter_and_group, run_correlation, etc.)
            2. Call generate_chart to produce the visualisation
            3. IMMEDIATELY call write_finding with:
               - headline: what the chart title says in plain English
               - detail: 2-3 sentences explaining what the chart reveals,
                 including the most important numbers visible in it
               - stat: the single most striking number from the data
  STEP C — After ALL charts and findings, write the final "## " report
            The report must have one section per chart, referencing its numbers

Generate as many charts as the analysis requires — do not artificially limit \
to 2 or 3 if more are needed to tell the full story. A visualisation report \
should typically have 4-6 charts.

━━━ CHART SYNTAX ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- histogram : {"col": "column_name"}
- bar       : grouped → {"col_a": "categorical_col", "col_b": "numeric_col"}
              counts  → {"col": "column_name"}
- scatter   : {"col_a": "x_col", "col_b": "y_col"}
- line      : {"col": "datetime_or_sequential_col"}
- box       : grouped → {"col_a": "numeric_col", "col_b": "categorical_col"}
              single  → {"col": "numeric_col"}

Only use column names that ACTUALLY EXIST in the dataset.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Always cite specific numbers. Never state a finding without tool evidence first.
"""


# ---------------------------------------------------------------------------
# Main agentic loop
# ---------------------------------------------------------------------------

async def run_agentic_analysis(
    problem: str,
    df: pd.DataFrame,
    eda: dict[str, Any],
) -> AsyncGenerator[dict, None]:
    """Run the agentic analysis and yield streaming events."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        yield {"type": "error", "message": "NVIDIA_API_KEY is not set. Add it to your .env file."}
        return

    model_name = os.getenv("AGENT_MODEL", "meta/llama-3.1-70b-instruct")
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    overview = eda["dataset_overview"]
    col_types = eda["column_types"]
    dataset_context = (
        f"Dataset: {overview['rows']:,} rows × {overview['cols']} columns\n"
        f"Columns: {', '.join(overview['columns'][:40])}\n"
        f"Numeric columns: {col_types.get('numeric', [])}\n"
        f"Categorical columns: {col_types.get('categorical', [])}\n"
        f"Datetime columns: {col_types.get('datetime', [])}\n"
        f"Missing values: {overview['null_pct']}% overall"
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Dataset context:\n{dataset_context}\n\nUser request: {problem}",
        },
    ]

    max_iterations = 50

    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=4096,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            yield {"type": "error", "message": f"NVIDIA API error: {exc}"}
            return

        if not text:
            continue

        messages.append({"role": "assistant", "content": text})

        # ---- Detect tool call ------------------------------------------------
        tool_call = _parse_tool_call(text)

        if tool_call:
            tool_name = tool_call.get("action", "")
            tool_args = tool_call.get("args", {})

            yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

            try:
                result, extra_event = _execute_tool(tool_name, tool_args, df, eda)
                if extra_event:
                    yield extra_event
                summary = _summarize_result(tool_name, result)
                yield {"type": "tool_result", "tool": tool_name, "summary": summary}
                result_text = f"Tool result for {tool_name}:\n{json.dumps(result, default=str)}"
            except Exception as exc:
                error_msg = f"Tool '{tool_name}' failed: {exc}"
                logger.warning(error_msg)
                yield {"type": "tool_result", "tool": tool_name, "summary": error_msg}
                result_text = f"Tool error: {error_msg}"

            # write_response is terminal — it sends the reply and stops
            if tool_name == "write_response":
                yield {"type": "done"}
                return

            messages.append({"role": "user", "content": result_text})

        # ---- Detect final report ---------------------------------------------
        elif (
            text.startswith("##")
            or "## " in text[:120]   # report buried after brief preamble
            or (len(text) > 300 and not text.strip().startswith("{"))
        ):
            # If there's a preamble before the ## heading, trim it
            idx = text.find("## ")
            markdown = text[idx:] if idx > 0 else text
            yield {"type": "report", "markdown": markdown}
            yield {"type": "done"}
            return

        # ---- Thinking / planning text ----------------------------------------
        else:
            yield {"type": "thinking", "text": text}
            messages.append({"role": "user", "content": "Continue your analysis."})

    yield {"type": "done"}


# ---------------------------------------------------------------------------
# JSON tool-call parser
# ---------------------------------------------------------------------------

def _parse_tool_call(text: str) -> dict | None:
    """Parse a tool call from LLM output.

    Handles three formats:
    1. Raw JSON starting with { (cleanest output)
    2. JSON inside ```json ... ``` code blocks
    3. JSON embedded anywhere in free text (llama-3.1 often adds preamble)
    """
    stripped = text.strip()

    # 1. Clean JSON starting at the beginning
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if "action" in data:
                return data
        except json.JSONDecodeError:
            pass

    # 2. JSON in backtick code blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "action" in data:
                return data
        except json.JSONDecodeError:
            pass

    # 3. JSON object embedded anywhere in the text (model adds preamble text)
    # Find the first { that could start a valid JSON object containing "action"
    for m in re.finditer(r'\{', text):
        start = m.start()
        # Try expanding from this { to find a complete JSON object
        depth = 0
        for i, ch in enumerate(text[start:]):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:start + i + 1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict) and "action" in data:
                            return data
                    except json.JSONDecodeError:
                        pass
                    break

    return None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _execute_tool(
    tool_name: str,
    args: dict,
    df: pd.DataFrame,
    eda: dict[str, Any],
) -> tuple[Any, dict | None]:

    if tool_name == "get_dataset_overview":
        overview = eda["dataset_overview"]
        col_types = eda["column_types"]
        return {
            "rows": overview["rows"],
            "cols": overview["cols"],
            "columns": overview["columns"],
            "numeric_columns": col_types.get("numeric", []),
            "categorical_columns": col_types.get("categorical", []),
            "datetime_columns": col_types.get("datetime", []),
            "null_pct": overview["null_pct"],
            "columns_with_nulls": {
                col: count
                for col, count in overview["null_per_column"].items()
                if count > 0
            },
        }, None

    if tool_name == "get_column_stats":
        columns: list[str] = args.get("columns", [])
        summary = eda["summary"]
        return {col: summary.get(col, {"error": "not found"}) for col in columns}, None

    if tool_name == "get_value_distribution":
        col: str = args["column"]
        top_n: int = int(args.get("top_n", 20))
        if col not in df.columns:
            return {"error": f"Column '{col}' not found"}, None
        counts = df[col].value_counts().head(top_n)
        total = int(df[col].notna().sum())
        return {
            "column": col,
            "total_non_null": total,
            "distribution": {
                str(k): {"count": int(v), "pct": round(v / total * 100, 1)}
                for k, v in counts.items()
            },
        }, None

    if tool_name == "filter_and_group":
        group_by: str = args["group_by"]
        value_col: str = args["value_column"]
        agg: str = args["agg"]
        filter_col: str | None = args.get("filter_col")
        filter_val = args.get("filter_val")

        working = df.copy()
        if filter_col and filter_val is not None and filter_col in working.columns:
            working = working[working[filter_col] == filter_val]

        if group_by not in working.columns or value_col not in working.columns:
            return {"error": "Column not found"}, None

        grouped = getattr(working.groupby(group_by)[value_col], agg)()
        top = grouped.sort_values(ascending=False).head(20)
        return {
            "group_by": group_by,
            "value_column": value_col,
            "agg": agg,
            "total_rows": len(working),
            "results": {
                str(k): round(float(v), 4) if isinstance(v, float) else int(v)
                for k, v in top.items()
            },
        }, None

    if tool_name == "run_correlation":
        col_a: str = args["col_a"]
        col_b: str = args["col_b"]
        if col_a not in df.columns or col_b not in df.columns:
            return {"error": "Column not found"}, None
        valid = df[[col_a, col_b]].dropna()
        if len(valid) < 5:
            return {"error": "Not enough data"}, None
        r, p = scipy_stats.pearsonr(valid[col_a], valid[col_b])
        return {
            "col_a": col_a,
            "col_b": col_b,
            "r": round(float(r), 4),
            "p_value": round(float(p), 6),
            "significant": bool(p < 0.05),
            "strength": _correlation_label(r),
            "direction": "positive" if r > 0 else "negative",
            "n": len(valid),
        }, None

    if tool_name == "run_linear_regression":
        target: str = args["target"]
        features: list[str] = args.get("features", [])

        if target not in df.columns:
            return {"error": f"Target column '{target}' not found"}, None
        missing_feats = [f for f in features if f not in df.columns]
        if missing_feats:
            return {"error": f"Feature columns not found: {missing_feats}"}, None
        if not features:
            return {"error": "No feature columns specified"}, None

        cols = [target] + features
        data = df[cols].dropna()
        if len(data) < 10:
            return {"error": "Not enough data for regression (need ≥ 10 rows)"}, None

        # Encode categorical features
        X_parts = []
        feature_names = []
        for feat in features:
            if data[feat].dtype == object or str(data[feat].dtype) == "category":
                dummies = pd.get_dummies(data[feat], prefix=feat, drop_first=True)
                X_parts.append(dummies.values)
                feature_names.extend(dummies.columns.tolist())
            else:
                X_parts.append(data[feat].values.reshape(-1, 1))
                feature_names.append(feat)

        X = np.hstack(X_parts).astype(float)
        y = data[target].values.astype(float)

        # Use numpy for multi-feature (handles both single and multi-feature)
        X_design = np.column_stack([np.ones(len(X)), X])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(X_design, y, rcond=None)
        except Exception as exc:
            return {"error": f"Regression failed: {exc}"}, None

        y_pred = X_design @ coeffs
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        rmse = float(np.sqrt(ss_res / len(y)))

        coeff_dict = {name: round(float(c), 6) for name, c in zip(feature_names, coeffs[1:])}
        coeff_dict["intercept"] = round(float(coeffs[0]), 6)

        # Individual correlations for context
        individual_r = {}
        for feat in features:
            try:
                r_val, _ = scipy_stats.pearsonr(data[feat].astype(float), y)
                individual_r[feat] = round(float(r_val), 4)
            except Exception:
                pass

        return {
            "target": target,
            "features": features,
            "n_observations": len(data),
            "r_squared": round(r_squared, 4),
            "r_squared_pct": f"{r_squared * 100:.1f}%",
            "rmse": round(rmse, 4),
            "coefficients": coeff_dict,
            "individual_correlations": individual_r,
            "interpretation": (
                f"The model explains {r_squared * 100:.1f}% of variance in '{target}'. "
                f"RMSE = {rmse:.4f}. "
                + (
                    f"Strongest predictor: '{max(individual_r, key=lambda k: abs(individual_r[k]))}' "
                    f"(r = {max(individual_r.values(), key=abs):.3f})."
                    if individual_r else ""
                )
            ),
        }, None

    if tool_name == "generate_chart":
        chart_type: str = args.get("chart_type", "bar")
        title: str = args.get("title", "")
        col = args.get("col")
        col_a = args.get("col_a")
        col_b = args.get("col_b")
        all_cols = df.columns.tolist()
        kwargs: dict = {}

        try:
            if chart_type == "histogram":
                target = col or col_a
                if target and target in all_cols:
                    kwargs["col"] = target
                else:
                    return {"error": f"Column not found for histogram"}, None

            elif chart_type == "line":
                target = col or col_a
                if target and target in all_cols:
                    kwargs["col"] = target
                else:
                    return {"error": f"Column not found for line chart"}, None

            elif chart_type == "bar":
                if col_a and col_b and col_a in all_cols and col_b in all_cols:
                    kwargs["col_a"] = col_a
                    kwargs["col_b"] = col_b
                elif col and col in all_cols:
                    kwargs["col"] = col
                elif col_a and col_a in all_cols:
                    kwargs["col"] = col_a
                else:
                    return {"error": "No valid column for bar chart"}, None

            elif chart_type == "scatter":
                if col_a and col_b and col_a in all_cols and col_b in all_cols:
                    kwargs["col_a"] = col_a
                    kwargs["col_b"] = col_b
                else:
                    return {"error": "scatter requires col_a and col_b"}, None

            elif chart_type == "box":
                numeric = col or col_a
                if numeric and numeric in all_cols:
                    kwargs["numeric_col"] = numeric
                    cat = col_b
                    if cat and cat in all_cols:
                        kwargs["cat_col"] = cat
                else:
                    return {"error": "No valid numeric column for box chart"}, None

            figure = generate_single_chart(df, chart_type, **kwargs)
            if figure and "layout" in figure:
                figure["layout"]["title"] = {"text": title}

            return {"chart_generated": True, "title": title}, {
                "type": "chart",
                "figure": figure,
                "title": title,
            }
        except Exception as exc:
            return {"error": f"Chart failed: {exc}"}, None

    if tool_name == "write_finding":
        headline: str = args.get("headline", "")
        detail: str = args.get("detail", "")
        stat: str = args.get("stat", "")
        return {"recorded": True}, {
            "type": "finding",
            "headline": headline,
            "detail": detail,
            "stat": stat,
        }

    if tool_name == "write_response":
        # Conversational reply — rendered as a report (plain text, no ## needed)
        content: str = args.get("content", "")
        return {"sent": True}, {
            "type": "report",
            "markdown": content,
        }

    return {"error": f"Unknown tool: {tool_name}"}, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _correlation_label(r: float) -> str:
    abs_r = abs(r)
    if abs_r >= 0.9: return "very strong"
    if abs_r >= 0.7: return "strong"
    if abs_r >= 0.5: return "moderate"
    if abs_r >= 0.3: return "weak"
    return "negligible"


def _summarize_result(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    if tool_name == "get_dataset_overview":
        return f"{result.get('rows', '?'):,} rows, {result.get('cols', '?')} columns"
    if tool_name == "get_column_stats":
        return f"Stats for: {list(result.keys())}"
    if tool_name == "get_value_distribution":
        return f"{len(result.get('distribution', {}))} unique values in '{result.get('column', '?')}'"
    if tool_name == "filter_and_group":
        top = list(result.get("results", {}).items())[:3]
        return f"Top groups: {top}"
    if tool_name == "run_correlation":
        return f"r={result.get('r')}, p={result.get('p_value')} ({result.get('strength')})"
    if tool_name == "run_linear_regression":
        return f"R²={result.get('r_squared_pct')} — {result.get('interpretation', '')[:80]}"
    if tool_name == "generate_chart":
        return f"Generated: {result.get('title', '?')}"
    if tool_name == "write_finding":
        return "Finding recorded"
    if tool_name == "write_response":
        return "Response sent"
    return str(result)[:120]
