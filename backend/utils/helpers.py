"""
Helpers
-------
Shared utility functions used across the backend.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# DataFrame serialisation
# ---------------------------------------------------------------------------

def df_to_json_records(
    df: pd.DataFrame,
    max_rows: int | None = None,
) -> list[dict]:
    """Convert a DataFrame to a list of JSON-serialisable dicts.

    Parameters
    ----------
    df:
        The DataFrame to convert.
    max_rows:
        If set, only return the first N rows.

    Returns
    -------
    List of row dicts safe for JSON serialisation.
    """
    if max_rows is not None:
        df = df.head(max_rows)

    # Convert non-serialisable types (datetime, numpy, etc.)
    return json.loads(
        df.to_json(orient="records", date_format="iso", default_handler=str)
    )


def df_summary_json(df: pd.DataFrame) -> dict[str, Any]:
    """Return a lightweight shape + dtype summary of a DataFrame."""
    return {
        "rows": len(df),
        "cols": len(df.columns),
        "columns": df.columns.tolist(),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": df.isnull().sum().to_dict(),
    }


# ---------------------------------------------------------------------------
# Apply dashboard filters to a DataFrame
# ---------------------------------------------------------------------------

def apply_filters(
    df: pd.DataFrame,
    numeric_filters: dict[str, dict] | None = None,
    category_filters: dict[str, list] | None = None,
    date_filters: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """Apply user-selected dashboard filters to a DataFrame.

    Parameters
    ----------
    df:
        The cleaned DataFrame.
    numeric_filters:
        Dict mapping column name to ``{"min": float, "max": float}``.
    category_filters:
        Dict mapping column name to a list of allowed values.
    date_filters:
        Dict mapping column name to ``{"start": "ISO date", "end": "ISO date"}``.

    Returns
    -------
    Filtered DataFrame (copy).
    """
    df = df.copy()

    if numeric_filters:
        for col, bounds in numeric_filters.items():
            if col not in df.columns:
                continue
            lo = bounds.get("min")
            hi = bounds.get("max")
            if lo is not None:
                df = df[df[col] >= lo]
            if hi is not None:
                df = df[df[col] <= hi]

    if category_filters:
        for col, values in category_filters.items():
            if col not in df.columns or not values:
                continue
            df = df[df[col].isin(values)]

    if date_filters:
        for col, bounds in date_filters.items():
            if col not in df.columns:
                continue
            start = bounds.get("start")
            end = bounds.get("end")
            if start:
                df = df[df[col] >= pd.Timestamp(start)]
            if end:
                df = df[df[col] <= pd.Timestamp(end)]

    return df


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------

def file_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of a file's bytes.

    Used to detect duplicate uploads without storing the file twice.
    """
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# ID / timestamp helpers
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    """Generate a new UUID4 session identifier."""
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# JSON serialisation safe-guards
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """Extend the default JSON encoder to handle numpy and pandas types."""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            f = float(obj)
            if np.isnan(f) or np.isinf(f):
                return None
            return f
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, (pd.NA, float)) and pd.isna(obj):
            return None
        return super().default(obj)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Serialise an object to JSON, safely handling numpy/pandas types."""
    return json.dumps(obj, cls=_SafeEncoder, **kwargs)


def safe_json_loads(s: str) -> Any:
    """Deserialise a JSON string."""
    return json.loads(s)


# ---------------------------------------------------------------------------
# Dataframe from bytes (for Supabase downloads)
# ---------------------------------------------------------------------------

def df_from_bytes(data: bytes, extension: str) -> pd.DataFrame:
    """Reconstruct a DataFrame from raw bytes and a file extension.

    Parameters
    ----------
    data:
        Raw file bytes (e.g. downloaded from Supabase Storage).
    extension:
        File extension without dot: ``"csv"``, ``"xlsx"``, or ``"xls"``.

    Returns
    -------
    Parsed DataFrame.
    """
    buf = io.BytesIO(data)
    if extension == "csv":
        for enc in ("utf-8", "latin-1", "cp1252"):
            try:
                buf.seek(0)
                return pd.read_csv(buf, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode CSV bytes.")
    return pd.read_excel(buf)
