"""
Chat Router
-----------
POST /api/chat/message  — Send a natural language message and get a response.
GET  /api/chat/history  — Get chat history for a session.
POST /api/chat/clear    — Clear chat history for a session.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from fastapi import APIRouter
from pydantic import BaseModel

from engine.chart_engine import generate_single_chart
from routers.analyze import get_cleaned_df, get_cached_eda

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory chat history per session (role, text pairs for display)
_chat_history: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    chart: Optional[Dict] = None
    chart_config: Optional[Dict] = None
    data_table: Optional[List[Dict]] = None
    suggested_questions: List[str] = []


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(eda: dict, filename: str) -> str:
    overview = eda["dataset_overview"]
    col_types = eda["column_types"]
    summary = eda["summary"]
    correlations = eda["correlations"]["strong_pairs"]

    numeric_summaries = [
        f"  - {col}: mean={info.get('mean')}, min={info.get('min')}, "
        f"max={info.get('max')}, nulls={info.get('null_pct')}%"
        for col, info in summary.items()
        if info.get("type") == "numeric"
    ]

    cat_summaries = [
        f"  - {col}: top values = {list(info.get('top_values', {}).keys())[:3]}"
        for col, info in summary.items()
        if info.get("type") == "categorical"
    ]

    corr_summary = [
        f"  - {p['col_a']} vs {p['col_b']}: r={p['r']} ({p['strength']})"
        for p in correlations[:5]
    ]

    return f"""You are DataWeaver, an expert AI data analyst.
You are analysing a dataset called "{filename}".

Dataset overview:
- {overview['rows']} rows, {overview['cols']} columns
- {overview['null_pct']}% missing values overall

Column types:
- Numeric: {col_types.get('numeric', [])}
- Categorical: {col_types.get('categorical', [])}
- Datetime: {col_types.get('datetime', [])}
- Boolean: {col_types.get('boolean', [])}

Numeric column statistics:
{chr(10).join(numeric_summaries) if numeric_summaries else "  None"}

Categorical columns:
{chr(10).join(cat_summaries) if cat_summaries else "  None"}

Strong correlations:
{chr(10).join(corr_summary) if corr_summary else "  None found"}

Your behaviour:
1. Answer questions concisely using the statistics above.
2. When a chart would help, include a chart_request in your response.
3. Always cite specific numbers from the data.
4. If asked something you cannot answer from the data, say so clearly.
5. Suggest follow-up questions when relevant.

When you want to generate a chart, include this JSON block in your response:
<chart_request>
{{
  "chart_type": "bar|histogram|line|scatter|box|heatmap",
  "col": "column_name",
  "col_a": "column_name_for_scatter_x",
  "col_b": "column_name_for_scatter_y",
  "title": "chart title"
}}
</chart_request>

Only include ONE chart per response. Only request charts for columns that exist in the dataset.
"""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/message", response_model=ChatResponse)
def chat_message(req: ChatMessage):
    """Process a chat message and return a response with optional chart."""
    eda = get_cached_eda(req.session_id)
    df = get_cleaned_df(req.session_id)

    from routers.upload import get_session_df
    session = get_session_df(req.session_id)
    filename = session.get("filename", "dataset")

    history = _chat_history.setdefault(req.session_id, [])

    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        reply, chart_config = _rule_based_response(req.message, eda)
        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": reply})
        chart = _build_chart(df, chart_config, eda) if chart_config else None
        return ChatResponse(
            reply=reply,
            chart=chart,
            chart_config=chart_config,
            suggested_questions=_suggest_questions(eda),
        )

    model_name = os.getenv("LLM_MODEL", "meta/llama-3.1-70b-instruct")
    system_prompt = _build_system_prompt(eda, filename)
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": req.message})

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )
    raw_reply = response.choices[0].message.content or ""

    chart_config = _extract_chart_request(raw_reply)
    clean_reply = _remove_chart_block(raw_reply)

    chart = None
    if chart_config:
        try:
            chart = _build_chart(df, chart_config, eda)
        except Exception as exc:
            logger.warning("Chart generation failed: %s", exc)

    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": clean_reply})

    return ChatResponse(
        reply=clean_reply,
        chart=chart,
        chart_config=chart_config,
        suggested_questions=_suggest_questions(eda),
    )


@router.get("/history")
def get_history(session_id: str):
    history = _chat_history.get(session_id, [])
    return {
        "session_id": session_id,
        "history": [m for m in history if m["role"] in ("user", "assistant")],
    }


@router.post("/clear")
def clear_history(session_id: str):
    _chat_history.pop(session_id, None)
    return {"session_id": session_id, "cleared": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_chart_request(text: str) -> dict | None:
    match = re.search(r"<chart_request>\s*(\{.*?\})\s*</chart_request>", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _remove_chart_block(text: str) -> str:
    return re.sub(r"<chart_request>.*?</chart_request>", "", text, flags=re.DOTALL).strip()


def _build_chart(df, chart_config: dict, eda: dict) -> dict | None:
    chart_type = chart_config.get("chart_type", "bar")
    all_cols = df.columns.tolist()
    kwargs: dict[str, Any] = {}

    if chart_type in ("histogram", "bar", "line"):
        col = chart_config.get("col", "")
        if col not in all_cols:
            return None
        kwargs["col"] = col
    elif chart_type == "scatter":
        col_a = chart_config.get("col_a", "")
        col_b = chart_config.get("col_b", "")
        if col_a not in all_cols or col_b not in all_cols:
            return None
        kwargs["col_a"] = col_a
        kwargs["col_b"] = col_b
        for p in eda["correlations"]["strong_pairs"]:
            if {p["col_a"], p["col_b"]} == {col_a, col_b}:
                kwargs["r"] = p["r"]
                break
    elif chart_type == "box":
        col = chart_config.get("col", chart_config.get("col_a", ""))
        if col not in all_cols:
            return None
        kwargs["numeric_col"] = col
        cat_col = chart_config.get("col_b", "")
        if cat_col and cat_col in all_cols:
            kwargs["cat_col"] = cat_col
    elif chart_type == "heatmap":
        kwargs["matrix"] = eda["correlations"]["matrix"]

    try:
        return generate_single_chart(df, chart_type, **kwargs)
    except Exception as exc:
        logger.warning("Chart build failed: %s", exc)
        return None


def _rule_based_response(message: str, eda: dict) -> tuple[str, dict | None]:
    """Fallback when no API key is configured."""
    msg_lower = message.lower()
    overview = eda["dataset_overview"]
    col_types = eda["column_types"]

    if any(w in msg_lower for w in ["how many", "rows", "size", "large"]):
        return (
            f"The dataset has **{overview['rows']:,} rows** and **{overview['cols']} columns**.",
            None,
        )
    if any(w in msg_lower for w in ["missing", "null", "empty"]):
        null_cols = {k: v for k, v in overview["null_per_column"].items() if v > 0}
        if null_cols:
            worst = max(null_cols, key=null_cols.get)  # type: ignore[arg-type]
            return (
                f"**{overview['null_pct']}%** of all values are missing. "
                f"Worst column: **{worst}** ({null_cols[worst]:,} missing).",
                None,
            )
        return ("No missing values found.", None)
    if any(w in msg_lower for w in ["correlat", "relationship"]):
        pairs = eda["correlations"]["strong_pairs"]
        if pairs:
            top = pairs[0]
            return (
                f"Strongest correlation: **{top['col_a']}** vs **{top['col_b']}** "
                f"(r={top['r']}, {top['strength']}).",
                {"chart_type": "heatmap"},
            )
        return ("No strong correlations found above 0.5.", None)
    if any(w in msg_lower for w in ["column", "variable", "feature"]):
        return (
            f"{len(col_types.get('numeric', []))} numeric, "
            f"{len(col_types.get('categorical', []))} categorical, "
            f"{len(col_types.get('datetime', []))} datetime columns.",
            None,
        )
    return (
        f"Dataset has **{overview['rows']:,} rows**. "
        "Ask about correlations, missing values, column types, or request a chart.",
        None,
    )


def _suggest_questions(eda: dict) -> list[str]:
    questions = []
    col_types = eda["column_types"]
    pairs = eda["correlations"]["strong_pairs"]

    if pairs:
        p = pairs[0]
        questions.append(f"Show me a scatter plot of {p['col_a']} vs {p['col_b']}")
    if col_types.get("datetime"):
        questions.append(f"Show me a line chart over time for {col_types['datetime'][0]}")
    if col_types.get("categorical"):
        questions.append(f"What are the most common values in {col_types['categorical'][0]}?")
    if col_types.get("numeric"):
        questions.append(f"Show me the distribution of {col_types['numeric'][0]}")
    questions.append("What are the main data quality issues?")

    return questions[:4]
