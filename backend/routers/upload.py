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

# In-memory session store — holds DataFrames for the life of the server process
_session_store: dict[str, dict] = {}


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
    if existing and existing["session_id"] in _session_store:
        sid = existing["session_id"]
        sess = _session_store[sid]
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
    _session_store[sid] = {
        "df":        df,
        "filename":  result["filename"],
        "extension": result["extension"],
        "file_hash": fhash,
        "upload_id": None,
        "created_at": utc_now_iso(),
    }

    # Persist metadata to Supabase (no file bytes saved)
    upload_id = sb.save_upload_metadata(
        session_id=sid,
        filename=result["filename"],
        file_hash=fhash,
        extension=result["extension"],
        row_count=result["row_count"],
        col_count=result["col_count"],
        size_kb=result["size_kb"] or 0,
    )
    _session_store[sid]["upload_id"] = upload_id

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
    _session_store[sid] = {
        "df":        df,
        "filename":  result["filename"],
        "extension": result["extension"],
        "file_hash": fhash,
        "upload_id": None,
        "created_at": utc_now_iso(),
    }

    upload_id = sb.save_upload_metadata(
        session_id=sid,
        filename=result["filename"],
        file_hash=fhash,
        extension=result["extension"],
        row_count=result["row_count"],
        col_count=result["col_count"],
        size_kb=0,
    )
    _session_store[sid]["upload_id"] = upload_id

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

def get_session_df(session_id: str):
    """Return the in-memory session dict, or raise ValueError if not found.

    Sessions live for the life of the server process. If the server restarted,
    the user needs to re-upload their file — raw files are not stored.
    """
    session = _session_store.get(session_id)
    if session is None:
        raise ValueError(
            f"Session '{session_id}' has expired. Please re-upload your file to continue."
        )
    return session
