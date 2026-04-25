"""
Analyze Router
--------------
POST /api/analyze        — Clean data + run full EDA.
GET  /api/analyze/summary — Return summary statistics for a session.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.data_cleaning import clean
from engine.eda import run_eda
from utils.validators import validate_cleaning_strategy
from utils import supabase_client as sb
from routers.upload import get_session_df

router = APIRouter()

# Cache EDA results in memory per session to avoid re-computation
_eda_cache: dict[str, dict] = {}
_cleaned_cache: dict[str, object] = {}  # session_id -> cleaned DataFrame


@router.post("")
def analyze(
    session_id: str,
    numeric_fill_strategy: str = "median",
    drop_high_null_cols: bool = True,
    null_col_threshold: float = 0.9,
):
    """Clean the uploaded DataFrame and run full EDA.

    Parameters
    ----------
    session_id:
        Session ID returned by the upload endpoint.
    numeric_fill_strategy:
        How to fill missing numeric values: median | mean | zero | none.
    drop_high_null_cols:
        Drop columns where null fraction exceeds threshold.
    null_col_threshold:
        Null fraction threshold for dropping columns (0.0 - 1.0).

    Returns
    -------
    Cleaning report + full EDA result dict.
    """
    validate_cleaning_strategy(numeric_fill_strategy)

    session = get_session_df(session_id)
    df_raw = session["df"]

    # Clean
    df_clean, cleaning_report = clean(
        df_raw,
        numeric_fill_strategy=numeric_fill_strategy,
        drop_high_null_cols=drop_high_null_cols,
        null_col_threshold=null_col_threshold,
    )

    # EDA
    eda_result = run_eda(df_clean)

    # Cache in memory
    _cleaned_cache[session_id] = df_clean
    _eda_cache[session_id] = eda_result

    # upload_id persisted via save_upload_metadata in the upload router

    return {
        "session_id": session_id,
        "cleaning_report": cleaning_report.to_dict(),
        "eda": eda_result,
    }


@router.get("/summary")
def get_summary(session_id: str):
    """Return only the summary statistics section of the EDA result."""
    eda = _get_cached_eda(session_id)
    return {
        "session_id": session_id,
        "summary": eda["summary"],
        "dataset_overview": eda["dataset_overview"],
    }


@router.get("/correlations")
def get_correlations(session_id: str):
    """Return the correlation matrix and strong pairs."""
    eda = _get_cached_eda(session_id)
    return {"session_id": session_id, "correlations": eda["correlations"]}


@router.get("/column-types")
def get_column_types(session_id: str):
    """Return the column type classification."""
    eda = _get_cached_eda(session_id)
    return {"session_id": session_id, "column_types": eda["column_types"]}


# ---------------------------------------------------------------------------
# Internal helpers used by other routers
# ---------------------------------------------------------------------------

def get_cleaned_df(session_id: str):
    """Return the cached cleaned DataFrame for a session."""
    df = _cleaned_cache.get(session_id)
    if df is None:
        raise ValueError(
            f"No cleaned data found for session '{session_id}'. "
            "Call POST /api/analyze first."
        )
    return df


def get_cached_eda(session_id: str) -> dict:
    """Public accessor for the EDA cache — used by other routers."""
    return _get_cached_eda(session_id)


def _get_cached_eda(session_id: str) -> dict:
    eda = _eda_cache.get(session_id)
    if eda is None:
        raise ValueError(
            f"No EDA found for session '{session_id}'. "
            "Call POST /api/analyze first."
        )
    return eda
