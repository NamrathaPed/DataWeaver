"""
Agent Engine
------------
Agentic data analysis loop powered by Gemini function calling.
Takes a session + problem statement, yields streaming events as it works.

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
from typing import Any, AsyncGenerator

import google.generativeai as genai
import pandas as pd
from scipy import stats as scipy_stats

from engine.chart_engine import generate_single_chart

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAPI-style, passed to Gemini as function_declarations)
# ---------------------------------------------------------------------------

_TOOL_DECLARATIONS = [
    {
        "name": "get_dataset_overview",
        "description": (
            "Get the dataset overview: row count, column count, column names, "
            "data types, and which columns have missing values."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_column_stats",
        "description": (
            "Get detailed statistics for specific columns — mean, median, std, "
            "min, max, top values, null percentage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names to get statistics for",
                }
            },
            "required": ["columns"],
        },
    },
    {
        "name": "get_value_distribution",
        "description": (
            "Get the full value distribution for a categorical or low-cardinality "
            "column — unique values with their count and percentage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "column": {"type": "string"},
                "top_n": {
                    "type": "integer",
                    "description": "Max number of top values to return (default 20)",
                },
            },
            "required": ["column"],
        },
    },
    {
        "name": "filter_and_group",
        "description": (
            "Group the data by a column and compute an aggregate "
            "(mean/sum/count/median/max/min) on another column. "
            "Returns the top 20 groups sorted by the aggregate value. "
            "Optionally pre-filter rows by a condition."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "Column to group by"},
                "value_column": {"type": "string", "description": "Column to aggregate"},
                "agg": {
                    "type": "string",
                    "enum": ["mean", "sum", "count", "median", "max", "min"],
                },
                "filter_col": {
                    "type": "string",
                    "description": "Optional: filter rows where this column equals filter_val",
                },
                "filter_val": {
                    "type": "string",
                    "description": "Optional: value to match in filter_col (pass as string)",
                },
            },
            "required": ["group_by", "value_column", "agg"],
        },
    },
    {
        "name": "run_correlation",
        "description": (
            "Compute the Pearson correlation between two numeric columns. "
            "Returns r, p-value, significance, and interpretation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "col_a": {"type": "string"},
                "col_b": {"type": "string"},
            },
            "required": ["col_a", "col_b"],
        },
    },
    {
        "name": "generate_chart",
        "description": (
            "Generate a chart to visualise a finding. "
            "Use bar for group comparisons, histogram for distributions, "
            "scatter for correlations, line for time trends, box for spread by category."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "histogram", "line", "scatter", "box"],
                },
                "title": {"type": "string", "description": "Descriptive chart title"},
                "col": {
                    "type": "string",
                    "description": "Primary column (histogram, line, or bar value counts)",
                },
                "col_a": {
                    "type": "string",
                    "description": "X-axis column (scatter) or group-by column (bar)",
                },
                "col_b": {
                    "type": "string",
                    "description": "Y-axis column (scatter) or value column (bar)",
                },
            },
            "required": ["chart_type", "title"],
        },
    },
    {
        "name": "write_finding",
        "description": (
            "Record a confirmed key finding. Call this each time you discover "
            "a significant pattern backed by data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "One-sentence headline, e.g. 'Speed >40mph accounts for 78% of fatal crashes'",
                },
                "detail": {
                    "type": "string",
                    "description": "Supporting context and explanation",
                },
                "stat": {
                    "type": "string",
                    "description": "Key statistic that proves the finding, e.g. '78%' or 'r=0.82'",
                },
            },
            "required": ["headline", "detail"],
        },
    },
]

SYSTEM_PROMPT = """\
You are DataWeaver, an expert AI data analyst. Reason about data the way a senior analyst does: \
systematically, hypothesis-driven, always grounded in numbers.

For every analysis:
1. Call get_dataset_overview first to understand the data.
2. Form 3-5 hypotheses relevant to the user's problem.
3. Test each hypothesis using filter_and_group, run_correlation, get_value_distribution.
4. Call write_finding each time you confirm something significant.
5. Generate charts only for the most important findings (2-4 maximum).
6. When you have gathered enough evidence, write a final markdown narrative report.

Rules:
- Always cite actual numbers (percentages, counts, r values).
- Never state a finding without tool-call evidence first.
- Final report: open with the biggest finding, walk through each insight with evidence, \
  close with 2-3 concrete next steps.
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
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        yield {
            "type": "error",
            "message": "GOOGLE_API_KEY is not set. Add it to your .env file.",
        }
        return

    genai.configure(api_key=api_key)
    model_name = os.getenv("AGENT_MODEL", "gemini-2.0-flash")

    overview = eda["dataset_overview"]
    col_types = eda["column_types"]
    dataset_context = (
        f"Dataset: {overview['rows']:,} rows × {overview['cols']} columns\n"
        f"Columns: {', '.join(overview['columns'][:40])}\n"
        f"Numeric columns: {col_types.get('numeric', [])}\n"
        f"Categorical columns: {col_types.get('categorical', [])}\n"
        f"Datetime columns: {col_types.get('datetime', [])}\n"
        f"Overall missing values: {overview['null_pct']}%"
    )
    initial_message = f"Dataset context:\n{dataset_context}\n\nAnalysis problem: {problem}"

    try:
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
            tools=[{"function_declarations": _TOOL_DECLARATIONS}],
        )
        chat = model.start_chat()
    except Exception as exc:
        yield {"type": "error", "message": f"Failed to initialise Gemini: {exc}"}
        return

    max_iterations = 20
    response = None

    for iteration in range(max_iterations):
        try:
            if iteration == 0:
                response = chat.send_message(initial_message)
            # (subsequent iterations send tool results — see below)
        except Exception as exc:
            yield {"type": "error", "message": f"Gemini API error: {exc}"}
            return

        # Split parts into text and function calls
        text_parts: list[str] = []
        function_calls: list[Any] = []

        for part in response.parts:
            if part.text:
                text_parts.append(part.text)
            if part.function_call.name:
                function_calls.append(part.function_call)

        # Emit text
        for text in text_parts:
            if text.strip():
                event_type = "report" if not function_calls else "thinking"
                yield {"type": event_type, "text": text}

        # No function calls → model is done
        if not function_calls:
            # If text was yielded as "thinking" (model wrote text without calling tools
            # for its final turn), re-label the last text as report.
            # In practice the final turn should have no function calls and substantial text.
            yield {"type": "done"}
            return

        # Execute function calls and collect responses
        tool_response_parts: list[Any] = []

        for fc in function_calls:
            tool_name: str = fc.name
            tool_args: dict = dict(fc.args)

            yield {"type": "tool_call", "tool": tool_name, "args": tool_args}

            try:
                result, extra_event = _execute_tool(tool_name, tool_args, df, eda)
                if extra_event:
                    yield extra_event
                summary = _summarize_result(tool_name, result)
                yield {"type": "tool_result", "tool": tool_name, "summary": summary}
                serialised = json.dumps(result, default=str)
            except Exception as exc:
                error_msg = f"Tool '{tool_name}' failed: {exc}"
                logger.warning(error_msg)
                yield {"type": "tool_result", "tool": tool_name, "summary": error_msg}
                serialised = json.dumps({"error": error_msg})

            tool_response_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=tool_name,
                        response={"result": serialised},
                    )
                )
            )

        # Send all tool results back in one message
        try:
            response = chat.send_message(tool_response_parts)
        except Exception as exc:
            yield {"type": "error", "message": f"Gemini API error sending tool results: {exc}"}
            return

    yield {"type": "done"}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _execute_tool(
    tool_name: str,
    args: dict,
    df: pd.DataFrame,
    eda: dict[str, Any],
) -> tuple[Any, dict | None]:
    """Execute a single tool. Returns (result_dict, optional_extra_event)."""

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
        return {col: summary.get(col, {"error": "column not found"}) for col in columns}, None

    if tool_name == "get_value_distribution":
        col: str = args["column"]
        top_n: int = int(args.get("top_n", 20))
        if col not in df.columns:
            return {"error": f"Column '{col}' not found"}, None
        counts = df[col].value_counts().head(top_n)
        total = int(df[col].notna().sum())
        dist = {
            str(k): {"count": int(v), "pct": round(v / total * 100, 1)}
            for k, v in counts.items()
        }
        return {"column": col, "total_non_null": total, "distribution": dist}, None

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
            return {"error": "Column not found in dataset"}, None

        grouped = getattr(working.groupby(group_by)[value_col], agg)()
        top = grouped.sort_values(ascending=False).head(20)
        return {
            "group_by": group_by,
            "value_column": value_col,
            "agg": agg,
            "total_rows_analysed": len(working),
            "results": {
                str(k): round(float(v), 4) if isinstance(v, float) else int(v)
                for k, v in top.items()
            },
        }, None

    if tool_name == "run_correlation":
        col_a: str = args["col_a"]
        col_b: str = args["col_b"]
        if col_a not in df.columns or col_b not in df.columns:
            return {"error": "One or both columns not found"}, None
        valid = df[[col_a, col_b]].dropna()
        if len(valid) < 5:
            return {"error": "Not enough data points to compute correlation"}, None
        r, p = scipy_stats.pearsonr(valid[col_a], valid[col_b])
        return {
            "col_a": col_a,
            "col_b": col_b,
            "r": round(float(r), 4),
            "p_value": round(float(p), 6),
            "significant_at_0_05": bool(p < 0.05),
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
                "type": "chart",
                "figure": figure,
                "title": title,
            }
        except Exception as exc:
            return {"error": f"Chart generation failed: {exc}"}, None

    if tool_name == "write_finding":
        headline: str = args["headline"]
        detail: str = args["detail"]
        stat: str = args.get("stat", "")
        return {"recorded": True}, {
            "type": "finding",
            "headline": headline,
            "detail": detail,
            "stat": stat,
        }

    return {"error": f"Unknown tool: {tool_name}"}, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _correlation_label(r: float) -> str:
    abs_r = abs(r)
    if abs_r >= 0.9:
        return "very strong"
    if abs_r >= 0.7:
        return "strong"
    if abs_r >= 0.5:
        return "moderate"
    if abs_r >= 0.3:
        return "weak"
    return "negligible"


def _summarize_result(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    if tool_name == "get_dataset_overview":
        return f"{result.get('rows', '?'):,} rows, {result.get('cols', '?')} columns"
    if tool_name == "get_column_stats":
        return f"Stats for: {list(result.keys())}"
    if tool_name == "get_value_distribution":
        n = len(result.get("distribution", {}))
        return f"{n} unique values in '{result.get('column', '?')}'"
    if tool_name == "filter_and_group":
        top = list(result.get("results", {}).items())[:3]
        return f"Top groups by {result.get('agg', '?')}: {top}"
    if tool_name == "run_correlation":
        return (
            f"r={result.get('r')}, p={result.get('p_value')} "
            f"({result.get('strength')}, {result.get('direction')})"
        )
    if tool_name == "generate_chart":
        return f"Generated: {result.get('title', '?')}"
    if tool_name == "write_finding":
        return "Finding recorded"
    return str(result)[:120]
