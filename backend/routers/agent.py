"""
Agent Router
------------
POST /api/agent/run  — Start an agentic analysis session (SSE stream).
POST /api/agent/chat — Follow-up question in an ongoing analysis session.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from engine.agent_engine import run_agentic_analysis
from routers.analyze import get_cleaned_df, get_cached_eda
from utils import supabase_client as sb

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    session_id: str
    problem: str
    history: list[dict] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_agent(req: AgentRunRequest):
    """
    Start an agentic analysis. Streams Server-Sent Events.

    Each event is a JSON object on a ``data:`` line, separated by a blank line.
    The ``type`` field identifies the event kind — see agent_engine.py for the
    full list.
    """
    df = get_cleaned_df(req.session_id)
    eda = get_cached_eda(req.session_id)

    # Save the user's message to Supabase
    sb.save_chat_message(req.session_id, "user", req.problem)

    assistant_parts: list[str] = []

    async def event_stream():
        try:
            async for event in run_agentic_analysis(req.problem, df, eda, req.history):
                # Collect text content to persist as one assistant message
                if event.get("type") == "report":
                    assistant_parts.append(event.get("markdown", ""))
                elif event.get("type") == "finding":
                    assistant_parts.append(
                        f"**{event.get('headline', '')}** — {event.get('detail', '')}"
                    )
                elif event.get("type") == "done" and assistant_parts:
                    sb.save_chat_message(
                        req.session_id, "assistant", "\n\n".join(assistant_parts)
                    )

                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            logger.exception("Agent stream error")
            error_event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Chat history endpoint
# ---------------------------------------------------------------------------

@router.get("/history")
def get_history(session_id: str):
    """Return saved chat messages for a session from Supabase."""
    messages = sb.get_chat_messages(session_id)
    return {"session_id": session_id, "messages": messages}
