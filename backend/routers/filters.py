"""
Filters Router
--------------
POST /api/filters/apply — Apply dashboard filters and return filtered preview + re-run charts.
GET  /api/filters/options — Return filter options (ranges, categories, date bounds) for the UI.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from engine.chart_engine import generate_all_charts
from utils.helpers import apply_filters, df_to_json_records
from utils.validators import validate_filter_payload
from routers.analyze import get_cleaned_df, get_cached_eda

router = APIRouter()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class FilterRequest(BaseModel):
    session_id: str
    numeric_filters: dict[str, dict[str, float]] = {}
    category_filters: dict[str, list[str]] = {}
    date_filters: dict[str, dict[str, str]] = {}
    preview_rows: int = 100
    regenerate_charts: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/apply")
def apply(req: FilterRequest):
    """Apply user-selected filters to the cleaned DataFrame.

    Returns a filtered data preview, updated row count, and optionally
    regenerated charts reflecting the filtered data.
    """
    df = get_cleaned_df(req.session_id)
    eda = get_cached_eda(req.session_id)

    # Validate filter columns + types
    validate_filter_payload(
        {
            "numeric_filters": req.numeric_filters,
            "category_filters": req.category_filters,
            "date_filters": req.date_filters,
        },
        eda["column_types"],
    )

    df_filtered = apply_filters(
        df,
        numeric_filters=req.numeric_filters or None,
        category_filters=req.category_filters or None,
        date_filters=req.date_filters or None,
    )

    result: dict[str, Any] = {
        "session_id": req.session_id,
        "original_rows": len(df),
        "filtered_rows": len(df_filtered),
        "reduction_pct": round((1 - len(df_filtered) / max(len(df), 1)) * 100, 2),
        "preview": df_to_json_records(df_filtered, max_rows=req.preview_rows),
    }

    if req.regenerate_charts and len(df_filtered) > 0:
        result["charts"] = generate_all_charts(df_filtered, eda)

    return result


@router.get("/options")
def filter_options(session_id: str):
    """Return the available filter options for the frontend to build its UI.

    For numeric columns: min/max range.
    For categorical columns: list of unique values.
    For datetime columns: start/end bounds.
    """
    df = get_cleaned_df(session_id)
    eda = get_cached_eda(session_id)
    col_types = eda["column_types"]

    options: dict[str, Any] = {
        "numeric": {},
        "categorical": {},
        "datetime": {},
    }

    for col in col_types.get("numeric", []):
        s = df[col].dropna()
        options["numeric"][col] = {
            "min": float(s.min()) if not s.empty else None,
            "max": float(s.max()) if not s.empty else None,
            "step": _infer_step(s),
        }

    for col in col_types.get("categorical", []):
        options["categorical"][col] = sorted(
            df[col].dropna().unique().astype(str).tolist()
        )

    for col in col_types.get("datetime", []):
        s = df[col].dropna()
        options["datetime"][col] = {
            "start": str(s.min()) if not s.empty else None,
            "end": str(s.max()) if not s.empty else None,
        }

    return {"session_id": session_id, "options": options}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _infer_step(s) -> float:
    """Infer a sensible slider step size for a numeric series."""
    rng = float(s.max() - s.min())
    if rng == 0:
        return 1.0
    if rng <= 1:
        return 0.01
    if rng <= 100:
        return 0.1
    if rng <= 10_000:
        return 1.0
    return round(rng / 1000, 2)
