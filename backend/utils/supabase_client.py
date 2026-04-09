"""
Supabase Client
---------------
Thin wrapper around the Supabase Python SDK for:
    - File storage  : upload / download / delete raw data files
    - Results cache : store and retrieve EDA + insight JSON blobs
    - Session index : track upload history per session

All methods are optional — if SUPABASE_URL or SUPABASE_KEY are not
set, the client initialises in "disabled" mode and every method
returns a graceful no-op result. This keeps the backend functional
for local development without Supabase credentials.

Supabase table schema (create these in your Supabase project):

    uploads (
        id           uuid primary key default gen_random_uuid(),
        session_id   text not null,
        filename     text not null,
        file_hash    text not null,
        storage_path text not null,
        extension    text not null,
        row_count    int,
        col_count    int,
        size_kb      float,
        created_at   timestamptz default now()
    )

    results (
        id           uuid primary key default gen_random_uuid(),
        upload_id    uuid references uploads(id) on delete cascade,
        eda_json     jsonb,
        insights_json jsonb,
        created_at   timestamptz default now()
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_STORAGE_BUCKET = "dataweaver-uploads"


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

def _get_client():
    """Return a Supabase client or None if credentials are missing."""
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
    """Return True if Supabase credentials are configured."""
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------

def upload_file(
    file_bytes: bytes,
    storage_path: str,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Upload raw file bytes to Supabase Storage.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the uploaded file.
    storage_path:
        Path within the storage bucket, e.g. ``"session-id/filename.csv"``.
    content_type:
        MIME type of the file.

    Returns
    -------
    dict with ``"path"`` on success, or ``"error"`` if Supabase is
    disabled or the upload fails.
    """
    client = _get_client()
    if client is None:
        return {"path": None, "error": "Supabase not configured"}

    try:
        client.storage.from_(b_=_STORAGE_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"},
        )
        return {"path": storage_path, "error": None}
    except Exception as exc:
        logger.error("Supabase file upload failed: %s", exc)
        return {"path": None, "error": str(exc)}


def download_file(storage_path: str) -> bytes | None:
    """Download a file from Supabase Storage.

    Parameters
    ----------
    storage_path:
        Path within the storage bucket.

    Returns
    -------
    Raw bytes, or None if unavailable.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        return client.storage.from_(b_=_STORAGE_BUCKET).download(storage_path)
    except Exception as exc:
        logger.error("Supabase file download failed: %s", exc)
        return None


def delete_file(storage_path: str) -> bool:
    """Delete a file from Supabase Storage.

    Returns True on success, False on failure.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        client.storage.from_(b_=_STORAGE_BUCKET).remove([storage_path])
        return True
    except Exception as exc:
        logger.error("Supabase file delete failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Upload metadata
# ---------------------------------------------------------------------------

def save_upload_metadata(
    session_id: str,
    filename: str,
    file_hash: str,
    storage_path: str,
    extension: str,
    row_count: int,
    col_count: int,
    size_kb: float,
) -> str | None:
    """Insert a row into the ``uploads`` table.

    Returns
    -------
    The new row's ``id`` (UUID string), or None on failure.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("uploads")
            .insert({
                "session_id": session_id,
                "filename": filename,
                "file_hash": file_hash,
                "storage_path": storage_path,
                "extension": extension,
                "row_count": row_count,
                "col_count": col_count,
                "size_kb": size_kb,
            })
            .execute()
        )
        return response.data[0]["id"] if response.data else None
    except Exception as exc:
        logger.error("Failed to save upload metadata: %s", exc)
        return None


def get_upload_by_hash(file_hash: str) -> dict | None:
    """Look up a previous upload by its file hash to detect duplicates.

    Returns
    -------
    The matching upload row dict, or None if not found.
    """
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


def list_uploads(session_id: str) -> list[dict]:
    """Return all uploads for a given session, newest first.

    Parameters
    ----------
    session_id:
        The session UUID to filter by.

    Returns
    -------
    List of upload row dicts.
    """
    client = _get_client()
    if client is None:
        return []
    try:
        response = (
            client.table("uploads")
            .select("id, filename, extension, row_count, col_count, size_kb, created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        logger.error("Failed to list uploads: %s", exc)
        return []


# ---------------------------------------------------------------------------
# EDA + insight results cache
# ---------------------------------------------------------------------------

def save_results(
    upload_id: str,
    eda_json: dict[str, Any],
    insights_json: dict[str, Any],
) -> bool:
    """Persist EDA and insight results linked to an upload.

    Returns True on success.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        client.table("results").insert({
            "upload_id": upload_id,
            "eda_json": eda_json,
            "insights_json": insights_json,
        }).execute()
        return True
    except Exception as exc:
        logger.error("Failed to save results: %s", exc)
        return False


def get_results(upload_id: str) -> dict | None:
    """Retrieve cached EDA and insight results for an upload.

    Returns
    -------
    Dict with ``eda_json`` and ``insights_json``, or None if not cached.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("results")
            .select("eda_json, insights_json, created_at")
            .eq("upload_id", upload_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as exc:
        logger.error("Failed to retrieve results: %s", exc)
        return None
