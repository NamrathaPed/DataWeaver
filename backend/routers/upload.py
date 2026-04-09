"""
Upload Router
-------------
POST /api/upload        — Upload a CSV or Excel file.
GET  /api/upload/sheets — List sheets in an uploaded Excel file.
GET  /api/upload/history — List previous uploads for a session.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from engine.data_ingestion import load_file, get_sheet_names
from utils.validators import validate_upload
from utils.helpers import file_hash, new_session_id, utc_now_iso, df_to_json_records
from utils import supabase_client as sb

router = APIRouter()

# In-memory session store (replace with Redis for multi-instance deployments)
_session_store: dict[str, dict] = {}


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    sheet_name: str = Form(default=""),
):
    """Upload a CSV or Excel file and return a session ID + data preview.

    - Validates extension and file size.
    - Detects duplicate uploads via SHA-256 hash.
    - Stores file in Supabase Storage if configured.
    - Returns a session_id used for all subsequent API calls.
    """
    raw = await file.read()

    # Validate
    validate_upload(file.filename, len(raw))

    # Dedup check via hash
    fhash = file_hash(raw)
    existing = sb.get_upload_by_hash(fhash)
    if existing:
        sid = existing["session_id"]
        cached = sb.get_results(existing["id"])
        if cached:
            return {
                "session_id": sid,
                "upload_id": existing["id"],
                "filename": existing["filename"],
                "row_count": existing["row_count"],
                "col_count": existing["col_count"],
                "cached": True,
                "eda": cached["eda_json"],
                "insights": cached["insights_json"],
            }

    # Parse file — wrap bytes in a BytesIO with .name so data_ingestion
    # recognises it as an uploaded file object.
    import io

    def _make_buf(data: bytes, name: str):
        buf = io.BytesIO(data)
        buf.name = name  # required by data_ingestion._is_uploaded_file
        return buf

    # Handle multi-sheet Excel
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xls") and not sheet_name:
        sheets = get_sheet_names(_make_buf(raw, file.filename))
        if len(sheets) > 1:
            return JSONResponse(
                status_code=200,
                content={
                    "requires_sheet_selection": True,
                    "sheets": sheets,
                    "filename": file.filename,
                },
            )

    result = load_file(_make_buf(raw, file.filename))
    df = result["df"]

    # Assign session
    sid = session_id or new_session_id()
    _session_store[sid] = {
        "df": df,
        "filename": result["filename"],
        "extension": result["extension"],
        "file_hash": fhash,
        "upload_id": None,
        "created_at": utc_now_iso(),
    }

    # Persist to Supabase
    storage_path = f"{sid}/{result['filename']}"
    sb.upload_file(raw, storage_path)
    upload_id = sb.save_upload_metadata(
        session_id=sid,
        filename=result["filename"],
        file_hash=fhash,
        storage_path=storage_path,
        extension=result["extension"],
        row_count=result["row_count"],
        col_count=result["col_count"],
        size_kb=result["size_kb"] or 0,
    )
    _session_store[sid]["upload_id"] = upload_id

    preview = df_to_json_records(df, max_rows=100)

    return {
        "session_id": sid,
        "upload_id": upload_id,
        "filename": result["filename"],
        "extension": result["extension"],
        "row_count": result["row_count"],
        "col_count": result["col_count"],
        "size_kb": result["size_kb"],
        "columns": df.columns.tolist(),
        "preview": preview,
        "cached": False,
    }


@router.post("/sheet")
async def select_sheet(
    file: UploadFile = File(...),
    sheet_name: str = Form(...),
    session_id: str = Form(default=""),
):
    """Load a specific sheet from a previously uploaded Excel file."""
    from engine.data_ingestion import load_excel_sheet
    import io

    raw = await file.read()
    buf = io.BytesIO(raw)
    buf.name = file.filename

    result = load_excel_sheet(buf, sheet_name)
    df = result["df"]

    sid = session_id or new_session_id()
    _session_store[sid] = {
        "df": df,
        "filename": result["filename"],
        "extension": result["extension"],
        "file_hash": file_hash(raw),
        "upload_id": None,
        "created_at": utc_now_iso(),
    }

    return {
        "session_id": sid,
        "sheet_name": sheet_name,
        "filename": result["filename"],
        "row_count": result["row_count"],
        "col_count": result["col_count"],
        "columns": df.columns.tolist(),
        "preview": df_to_json_records(df, max_rows=100),
    }


@router.get("/history")
def upload_history(session_id: str):
    """Return previous uploads for a session from Supabase."""
    uploads = sb.list_uploads(session_id)
    return {"session_id": session_id, "uploads": uploads}


# ---------------------------------------------------------------------------
# Internal helper — other routers use this to retrieve the session DataFrame
# ---------------------------------------------------------------------------

def get_session_df(session_id: str):
    """Return the DataFrame stored for a session, or raise ValueError."""
    session = _session_store.get(session_id)
    if session is None:
        raise ValueError(
            f"Session '{session_id}' not found. Please upload a file first."
        )
    return session
