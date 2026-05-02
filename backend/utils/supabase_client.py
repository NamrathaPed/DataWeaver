"""
Supabase Client
---------------
Persists session metadata, DataFrames, computed state, and chat messages.

Tables required (run supabase_schema.sql in the Supabase SQL Editor):

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

    session_state (
        session_id   text primary key,
        eda_result   jsonb,
        chart_cache  jsonb,
        insight_cache jsonb,
        updated_at   timestamptz default now()
    )

    chat_messages (
        id         uuid primary key default gen_random_uuid(),
        session_id text not null,
        role       text not null,
        content    text not null,
        created_at timestamptz default now()
    )

Storage bucket required: "session-files" (private)
    {session_id}/raw.parquet      — raw uploaded DataFrame
    {session_id}/cleaned.parquet  — cleaned DataFrame after /analyze

All methods are no-ops when SUPABASE_URL / SUPABASE_KEY are not set.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

STORAGE_BUCKET = "session-files"


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
# JSON serialization helpers (handles numpy / pandas scalar types)
# ---------------------------------------------------------------------------

def _json_default(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float) and np.isnan(obj):
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    raise TypeError(f"Not JSON serializable: {type(obj)}")


def _to_json_safe(obj) -> object:
    """Round-trip through JSON to strip all numpy types."""
    return json.loads(json.dumps(obj, default=_json_default))


# ---------------------------------------------------------------------------
# DataFrame storage (Supabase Storage — gzipped CSV + dtype sidecar)
# ---------------------------------------------------------------------------

def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return gzip.compress(buf.getvalue())


def _csv_bytes_to_df(data: bytes, dtypes: dict | None = None) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(gzip.decompress(data)))
    if dtypes:
        for col, dtype in dtypes.items():
            if col not in df.columns:
                continue
            try:
                if "datetime" in dtype:
                    df[col] = pd.to_datetime(df[col])
                elif dtype in ("bool", "boolean"):
                    df[col] = df[col].astype(bool)
                else:
                    df[col] = df[col].astype(dtype)
            except Exception:
                pass
    return df


def _storage_upload(storage, path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload or overwrite a file in Supabase Storage."""
    try:
        storage.upload(path, data, {"content-type": content_type, "upsert": "true"})
    except Exception:
        try:
            storage.remove([path])
        except Exception:
            pass
        storage.upload(path, data, {"content-type": content_type})


def upload_dataframe(session_id: str, df: pd.DataFrame, key: str) -> bool:
    """Save a DataFrame to Supabase Storage as gzipped CSV.

    key is "raw" or "cleaned". Stores a dtype sidecar JSON alongside
    so datetime/bool columns are reconstructed correctly on load.
    """
    client = _get_client()
    if client is None:
        return False
    try:
        storage = client.storage.from_(STORAGE_BUCKET)
        csv_bytes = _df_to_csv_bytes(df)
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
        dtypes_bytes = json.dumps(dtypes).encode()
        _storage_upload(storage, f"{session_id}/{key}.csv.gz", csv_bytes)
        _storage_upload(storage, f"{session_id}/{key}_dtypes.json", dtypes_bytes, "application/json")
        return True
    except Exception as exc:
        logger.error("Failed to upload dataframe (%s/%s): %s", session_id, key, exc)
        return False


def download_dataframe(session_id: str, key: str) -> pd.DataFrame | None:
    """Load a DataFrame from Supabase Storage. Returns None if not found."""
    client = _get_client()
    if client is None:
        return None
    try:
        storage = client.storage.from_(STORAGE_BUCKET)
        csv_bytes = storage.download(f"{session_id}/{key}.csv.gz")
        try:
            dtypes_bytes = storage.download(f"{session_id}/{key}_dtypes.json")
            dtypes = json.loads(dtypes_bytes)
        except Exception:
            dtypes = None
        return _csv_bytes_to_df(csv_bytes, dtypes)
    except Exception as exc:
        logger.warning("Failed to download dataframe (%s/%s): %s", session_id, key, exc)
        return None


# ---------------------------------------------------------------------------
# Session state (EDA / charts / insights in Postgres JSONB)
# ---------------------------------------------------------------------------

def save_session_state(session_id: str, **fields) -> bool:
    """Upsert one or more state fields (eda_result, chart_cache, insight_cache)."""
    client = _get_client()
    if client is None:
        return False
    try:
        safe_fields = {k: _to_json_safe(v) for k, v in fields.items()}
        payload = {"session_id": session_id, **safe_fields}
        client.table("session_state").upsert(payload).execute()
        return True
    except Exception as exc:
        logger.error("Failed to save session state (%s): %s", session_id, exc)
        return False


def get_session_state(session_id: str) -> dict | None:
    """Return the full session_state row for a session, or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("session_state")
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as exc:
        logger.error("Failed to get session state (%s): %s", session_id, exc)
        return None


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


def get_session_metadata(session_id: str) -> dict | None:
    """Return the most recent uploads row for a session, or None."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = (
            client.table("uploads")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as exc:
        logger.error("Failed to get session metadata (%s): %s", session_id, exc)
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


def clear_chat_messages(session_id: str) -> bool:
    """Delete all chat messages for a session."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.table("chat_messages").delete().eq("session_id", session_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to clear chat messages: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Backwards compat stub
# ---------------------------------------------------------------------------

def save_results(upload_id: str, eda: dict, insights: dict) -> bool:
    """No-op stub kept for import compatibility. Use save_session_state instead."""
    return True
