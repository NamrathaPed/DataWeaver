"""
Upload Router
-------------
POST /api/upload         — Upload a CSV or Excel file.
POST /api/upload/sheet   — Select a sheet from a multi-sheet Excel file.
GET  /api/upload/sessions — List all past sessions from Supabase.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from engine.data_ingestion import load_file, get_sheet_names
from utils.validators import validate_upload
from utils.helpers import file_hash, new_session_id, utc_now_iso, df_to_json_records
from utils import supabase_client as sb

router = APIRouter()

# In-memory L1 cache — avoids round-tripping Supabase Storage within the same process
_session_store: dict[str, dict] = {}


def _store_session(sid: str, df, filename: str, extension: str, fhash: str, upload_id=None):
    """Write session to memory and persist DataFrame + metadata to Supabase."""
    _session_store[sid] = {
        "df":        df,
        "filename":  filename,
        "extension": extension,
        "file_hash": fhash,
        "upload_id": upload_id,
        "created_at": utc_now_iso(),
    }
    sb.upload_dataframe(sid, df, "raw")


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    sheet_name: str = Form(default=""),
):
    """Upload a CSV or Excel file and return a session ID + data preview."""
    raw = await file.read()
    validate_upload(file.filename, len(raw))

    fhash = file_hash(raw)

    # Dedup: if we've seen this exact file before, reuse the session
    existing = sb.get_upload_by_hash(fhash)
    if existing:
        sid = existing["session_id"]
        # Try to serve from memory or re-load from Supabase Storage
        try:
            sess = get_session_df(sid)
            df = sess["df"]
            return {
                "session_id": sid,
                "upload_id":  existing["id"],
                "filename":   existing["filename"],
                "extension":  existing["extension"],
                "row_count":  existing["row_count"],
                "col_count":  existing["col_count"],
                "size_kb":    existing["size_kb"],
                "columns":    df.columns.tolist(),
                "preview":    df_to_json_records(df, max_rows=100),
                "cached":     True,
            }
        except ValueError:
            pass  # file not in storage, fall through to re-parse

    def _make_buf(data: bytes, name: str):
        buf = io.BytesIO(data)
        buf.name = name
        return buf

    # Handle multi-sheet Excel
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls") and not sheet_name:
        sheets = get_sheet_names(_make_buf(raw, file.filename))
        if len(sheets) > 1:
            return JSONResponse(status_code=200, content={
                "requires_sheet_selection": True,
                "sheets": sheets,
                "filename": file.filename,
            })

    result = load_file(_make_buf(raw, file.filename))
    df = result["df"]

    sid = session_id or new_session_id()

    upload_id = sb.save_upload_metadata(
        session_id=sid,
        filename=result["filename"],
        file_hash=fhash,
        extension=result["extension"],
        row_count=result["row_count"],
        col_count=result["col_count"],
        size_kb=result["size_kb"] or 0,
    )

    _store_session(sid, df, result["filename"], result["extension"], fhash, upload_id)

    return {
        "session_id": sid,
        "upload_id":  upload_id,
        "filename":   result["filename"],
        "extension":  result["extension"],
        "row_count":  result["row_count"],
        "col_count":  result["col_count"],
        "size_kb":    result["size_kb"],
        "columns":    df.columns.tolist(),
        "preview":    df_to_json_records(df, max_rows=100),
        "cached":     False,
    }


@router.post("/sheet")
async def select_sheet(
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    session_id: str = Form(default=""),
):
    """Load a specific sheet from a multi-sheet Excel file."""
    from engine.data_ingestion import load_excel_sheet

    raw = await file.read()
    buf = io.BytesIO(raw)
    buf.name = file.filename

    result = load_excel_sheet(buf, sheet_name)
    df = result["df"]
    fhash = file_hash(raw)

    sid = session_id or new_session_id()

    upload_id = sb.save_upload_metadata(
        session_id=sid,
        filename=result["filename"],
        file_hash=fhash,
        extension=result["extension"],
        row_count=result["row_count"],
        col_count=result["col_count"],
        size_kb=0,
    )

    _store_session(sid, df, result["filename"], result["extension"], fhash, upload_id)

    return {
        "session_id": sid,
        "upload_id":  upload_id,
        "sheet_name": sheet_name,
        "filename":   result["filename"],
        "row_count":  result["row_count"],
        "col_count":  result["col_count"],
        "columns":    df.columns.tolist(),
        "preview":    df_to_json_records(df, max_rows=100),
        "cached":     False,
    }


@router.get("/sessions")
def list_sessions():
    """Return all past sessions from Supabase for the sidebar."""
    sessions = sb.list_all_sessions(limit=50)
    return {"sessions": sessions}


# ---------------------------------------------------------------------------
# Internal helper used by all other routers
# ---------------------------------------------------------------------------

def get_session_df(session_id: str) -> dict:
    """Return the session dict (including raw DataFrame).

    Checks in-memory L1 cache first; falls back to Supabase Storage + uploads
    table so sessions survive server restarts and cold serverless starts.
    """
    session = _session_store.get(session_id)
    if session is not None:
        return session

    # L2: Supabase Storage
    meta = sb.get_session_metadata(session_id)
    df = sb.download_dataframe(session_id, "raw")

    if meta is None or df is None:
        raise ValueError(
            f"Session '{session_id}' not found. Please re-upload your file to continue."
        )

    session = {
        "df":        df,
        "filename":  meta["filename"],
        "extension": meta["extension"],
        "file_hash": meta["file_hash"],
        "upload_id": meta["id"],
        "created_at": meta["created_at"],
    }
    _session_store[session_id] = session  # warm the L1 cache
    return session
