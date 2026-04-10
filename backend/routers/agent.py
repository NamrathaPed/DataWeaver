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

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    session_id: str
    problem: str


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

    async def event_stream():
        try:
            async for event in run_agentic_analysis(
                req.problem, df, eda
            ):
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
