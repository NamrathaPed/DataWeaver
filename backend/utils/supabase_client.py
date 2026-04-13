"""
Supabase Client
---------------
Persists session metadata and chat messages to Supabase.
Raw dataset files are NOT stored — sessions are in-memory only.

Tables required (run in Supabase SQL Editor):

    uploads (
        id           uuid primary key default gen_random_uuid(),
        session_id   text not null,
        filename     text not null,
        file_hash    text not null,
        extension    text not null,
        row_count    int,
        col_count    int,
        size_kb      float,
        created_at   timestamptz default now()
    )

    chat_messages (
        id         uuid primary key default gen_random_uuid(),
        session_id text not null,
        role       text not null,
        content    text not null,
        created_at timestamptz default now()
    )

All methods are no-ops when SUPABASE_URL / SUPABASE_KEY are not set.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def _get_client():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        logger.warning("Supabase client init failed: %s", exc)
        return None


def is_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------

def save_upload_metadata(
    session_id: str,
    filename: str,
    file_hash: str,
    extension: str,
    row_count: int,
    col_count: int,
    size_kb: float,
) -> str | None:
    """Insert a row into the uploads table. Returns the new row id or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("uploads")
            .insert({
                "session_id": session_id,
                "filename":   filename,
                "file_hash":  file_hash,
                "extension":  extension,
                "row_count":  row_count,
                "col_count":  col_count,
                "size_kb":    size_kb,
            })
            .execute()
        )
        return response.data[0]["id"] if response.data else None
    except Exception as exc:
        logger.error("Failed to save upload metadata: %s", exc)
        return None


def get_upload_by_hash(file_hash: str) -> dict | None:
    """Return an existing upload row matching the file hash, or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("uploads")
            .select("*")
            .eq("file_hash", file_hash)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as exc:
        logger.error("Upload hash lookup failed: %s", exc)
        return None


def list_all_sessions(limit: int = 50) -> list[dict]:
    """Return the most recent upload sessions, newest first, deduplicated."""
    client = _get_client()
    if client is None:
        return []
    try:
        response = (
            client.table("uploads")
            .select("session_id, filename, row_count, col_count, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        seen: set[str] = set()
        unique = []
        for row in (response.data or []):
            if row["session_id"] not in seen:
                seen.add(row["session_id"])
                unique.append(row)
        return unique
    except Exception as exc:
        logger.error("Failed to list sessions: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

def save_chat_message(session_id: str, role: str, content: str) -> bool:
    """Persist a single chat message. role is 'user' or 'assistant'."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.table("chat_messages").insert({
            "session_id": session_id,
            "role":       role,
            "content":    content,
        }).execute()
        return True
    except Exception as exc:
        logger.error("Failed to save chat message: %s", exc)
        return False


def get_chat_messages(session_id: str) -> list[dict]:
    """Return all chat messages for a session, oldest first."""
    client = _get_client()
    if client is None:
        return []
    try:
        response = (
            client.table("chat_messages")
            .select("role, content, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.error("Failed to load chat messages: %s", exc)
        return []
