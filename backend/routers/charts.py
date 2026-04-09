"""
Charts Router
-------------
GET  /api/charts/all    — Generate all charts for a session.
GET  /api/charts/single — Generate a single chart by type.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.chart_engine import generate_all_charts, generate_single_chart
from utils.validators import validate_chart_type, validate_column_exists
from routers.analyze import get_cleaned_df, get_cached_eda

router = APIRouter()

# Chart cache — charts are expensive to regenerate on every request
_chart_cache: dict[str, dict] = {}


@router.get("/all")
def all_charts(
    session_id: str,
    max_scatter_pairs: int = 5,
    max_categorical_cols: int = 8,
    max_numeric_cols: int = 10,
    force_refresh: bool = False,
):
    """Generate and return all charts for the session's dataset.

    Charts are cached after the first generation. Use force_refresh=true
    to regenerate (e.g. after applying filters).

    Returns Plotly figure dicts for every chart type.
    """
    if not force_refresh and session_id in _chart_cache:
        return {"session_id": session_id, "charts": _chart_cache[session_id], "cached": True}

    df = get_cleaned_df(session_id)
    eda = get_cached_eda(session_id)

    charts = generate_all_charts(
        df,
        eda,
        max_scatter_pairs=max_scatter_pairs,
        max_categorical_cols=max_categorical_cols,
        max_numeric_cols=max_numeric_cols,
    )

    _chart_cache[session_id] = charts
    return {"session_id": session_id, "charts": charts, "cached": False}


@router.get("/single")
def single_chart(
    session_id: str,
    chart_type: str,
    col: str = "",
    col_a: str = "",
    col_b: str = "",
    numeric_col: str = "",
    cat_col: str = "",
):
    """Generate a single chart by type.

    Parameters
    ----------
    chart_type:
        One of: histogram | bar | line | scatter | box | heatmap
    col:
        Column name (for histogram, bar, line).
    col_a / col_b:
        Column names for scatter plot.
    numeric_col / cat_col:
        Column names for box plot.
    """
    validate_chart_type(chart_type)

    df = get_cleaned_df(session_id)
    eda = get_cached_eda(session_id)
    all_cols = df.columns.tolist()

    kwargs: dict = {}

    if chart_type in ("histogram", "bar", "line"):
        validate_column_exists(col, all_cols)
        kwargs["col"] = col

    elif chart_type == "scatter":
        validate_column_exists(col_a, all_cols)
        validate_column_exists(col_b, all_cols)
        kwargs["col_a"] = col_a
        kwargs["col_b"] = col_b
        # Attach r value from EDA if available
        pairs = eda["correlations"].get("strong_pairs", [])
        for p in pairs:
            if {p["col_a"], p["col_b"]} == {col_a, col_b}:
                kwargs["r"] = p["r"]
                break

    elif chart_type == "box":
        validate_column_exists(numeric_col, all_cols)
        kwargs["numeric_col"] = numeric_col
        if cat_col:
            validate_column_exists(cat_col, all_cols)
            kwargs["cat_col"] = cat_col

    elif chart_type == "heatmap":
        kwargs["matrix"] = eda["correlations"]["matrix"]

    fig = generate_single_chart(df, chart_type, **kwargs)
    return {"session_id": session_id, "chart_type": chart_type, "figure": fig}
