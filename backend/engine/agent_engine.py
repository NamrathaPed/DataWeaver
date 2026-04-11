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
You are DataWeaver, an expert AI data analyst. You analyse data systematically \
and always ground your conclusions in actual numbers.

You have access to these tools:
- get_dataset_overview   — no args needed
- get_column_stats       — args: {"columns": ["col1", "col2"]}
- get_value_distribution — args: {"column": "col_name", "top_n": 20}
- filter_and_group       — args: {"group_by": "col", "value_column": "col", "agg": "mean|sum|count|median|max|min", "filter_col": "col (optional)", "filter_val": "val (optional)"}
- run_correlation        — args: {"col_a": "col", "col_b": "col"}
- generate_chart         — args: {"chart_type": "bar|histogram|line|scatter|box", "title": "...", "col": "...", "col_a": "...", "col_b": "..."}
- write_finding          — args: {"headline": "...", "detail": "...", "stat": "..."}

HOW TO CALL A TOOL — respond with ONLY this JSON (no other text):
{"action": "tool_name", "args": {...}}

HOW TO FINISH — when your analysis is complete, write your final report as plain \
markdown. Start it with "## " so I know it is the report.

ANALYSIS APPROACH:
1. Start with get_dataset_overview
2. Form hypotheses relevant to the problem
3. Use filter_and_group, run_correlation, get_value_distribution to test them
4. Call write_finding for each confirmed insight
5. Generate 2-4 charts for the most important findings
6. Write the final markdown report

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
        f"Dataset: {overview['rows']:,} rows x {overview['cols']} columns\n"
        f"Columns: {', '.join(overview['columns'][:40])}\n"
        f"Numeric: {col_types.get('numeric', [])}\n"
        f"Categorical: {col_types.get('categorical', [])}\n"
        f"Datetime: {col_types.get('datetime', [])}\n"
        f"Missing values: {overview['null_pct']}% overall"
    )

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Dataset context:\n{dataset_context}\n\nAnalysis problem: {problem}"},
    ]

    max_iterations = 25

    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
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

            messages.append({"role": "user", "content": result_text})

        # ---- Detect final report ---------------------------------------------
        elif text.startswith("##") or (len(text) > 300 and not text.startswith("{")):
            yield {"type": "report", "markdown": text}
            yield {"type": "done"}
            return

        # ---- Thinking text ---------------------------------------------------
        else:
            yield {"type": "thinking", "text": text}
            messages.append({"role": "user", "content": "Continue your analysis."})

    yield {"type": "done"}


# ---------------------------------------------------------------------------
# JSON tool-call parser
# ---------------------------------------------------------------------------

def _parse_tool_call(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if "action" in data:
                return data
        except json.JSONDecodeError:
            pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "action" in data:
                return data
        except json.JSONDecodeError:
            pass

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
            "col_a": col_a, "col_b": col_b,
            "r": round(float(r), 4),
            "p_value": round(float(p), 6),
            "significant": bool(p < 0.05),
            "strength": _correlation_label(r),
            "direction": "positive" if r > 0 else "negative",
            "n": len(valid),
        }, None

    if tool_name == "generate_chart":
        chart_type: str = args["chart_type"]
        title: str = args["title"]
        col = args.get("col")
        col_a = args.get("col_a")
        col_b = args.get("col_b")
        all_cols = df.columns.tolist()
        kwargs: dict = {}

        try:
            if chart_type in ("histogram", "line"):
                target = col or col_a
                if target and target in all_cols:
                    kwargs["col"] = target
            elif chart_type == "bar":
                if col_a and col_b and col_a in all_cols and col_b in all_cols:
                    kwargs["col_a"] = col_a
                    kwargs["col_b"] = col_b
                elif col and col in all_cols:
                    kwargs["col"] = col
                elif col_a and col_a in all_cols:
                    kwargs["col"] = col_a
            elif chart_type == "scatter":
                if col_a and col_b and col_a in all_cols and col_b in all_cols:
                    kwargs["col_a"] = col_a
                    kwargs["col_b"] = col_b
            elif chart_type == "box":
                target = col or col_a
                if target and target in all_cols:
                    kwargs["numeric_col"] = target
                    if col_b and col_b in all_cols:
                        kwargs["cat_col"] = col_b

            figure = generate_single_chart(df, chart_type, **kwargs)
            if figure and "layout" in figure:
                figure["layout"]["title"] = {"text": title}

            return {"chart_generated": True, "title": title}, {
                "type": "chart", "figure": figure, "title": title,
            }
        except Exception as exc:
            return {"error": f"Chart failed: {exc}"}, None

    if tool_name == "write_finding":
        headline: str = args["headline"]
        detail: str = args["detail"]
        stat: str = args.get("stat", "")
        return {"recorded": True}, {
            "type": "finding", "headline": headline, "detail": detail, "stat": stat,
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
    if tool_name == "generate_chart":
        return f"Generated: {result.get('title', '?')}"
    if tool_name == "write_finding":
        return "Finding recorded"
    return str(result)[:120]
