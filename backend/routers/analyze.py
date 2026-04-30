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

# In-memory L1 caches — populated on first access, survive only for process lifetime
_eda_cache: dict[str, dict] = {}
_cleaned_cache: dict[str, object] = {}  # session_id -> cleaned DataFrame


@router.post("")
def analyze(
    session_id: str,
    numeric_fill_strategy: str = "median",
    drop_high_null_cols: bool = True,
    null_col_threshold: float = 0.9,
):
    """Clean the uploaded DataFrame and run full EDA."""
    validate_cleaning_strategy(numeric_fill_strategy)

    session = get_session_df(session_id)
    df_raw = session["df"]

    df_clean, cleaning_report = clean(
        df_raw,
        numeric_fill_strategy=numeric_fill_strategy,
        drop_high_null_cols=drop_high_null_cols,
        null_col_threshold=null_col_threshold,
    )

    eda_result = run_eda(df_clean)

    # L1 cache
    _cleaned_cache[session_id] = df_clean
    _eda_cache[session_id] = eda_result

    # L2 persistence — cleaned DataFrame to Storage, EDA to session_state
    sb.upload_dataframe(session_id, df_clean, "cleaned")
    sb.save_session_state(session_id, eda_result=eda_result)

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
    """Return the cleaned DataFrame. Checks L1 memory, then Supabase Storage."""
    df = _cleaned_cache.get(session_id)
    if df is not None:
        return df

    df = sb.download_dataframe(session_id, "cleaned")
    if df is None:
        raise ValueError(
            f"No cleaned data found for session '{session_id}'. "
            "Call POST /api/analyze first."
        )

    _cleaned_cache[session_id] = df
    return df


def get_cached_eda(session_id: str) -> dict:
    """Public accessor for the EDA cache — used by other routers."""
    return _get_cached_eda(session_id)


def _get_cached_eda(session_id: str) -> dict:
    eda = _eda_cache.get(session_id)
    if eda is not None:
        return eda

    state = sb.get_session_state(session_id)
    if state and state.get("eda_result"):
        eda = state["eda_result"]
        _eda_cache[session_id] = eda
        return eda

    raise ValueError(
        f"No EDA found for session '{session_id}'. "
        "Call POST /api/analyze first."
    )
