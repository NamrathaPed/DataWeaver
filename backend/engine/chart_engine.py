"""
Chart Engine Module
-------------------
Auto-generates Plotly charts based on EDA results and column types.
Returns Plotly figure dicts (JSON-serialisable) so they can be sent
directly from FastAPI and rendered by Plotly.js on the React frontend.

Chart selection logic:
    - Numeric column          : Histogram + Box plot
    - Categorical column      : Bar chart (value counts)
    - Datetime column         : Line chart (record count over time)
    - Numeric pair (r >= 0.5) : Scatter plot
    - Numeric vs Categorical  : Grouped box plot
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ---------------------------------------------------------------------------
# Theme / defaults
# ---------------------------------------------------------------------------

_PALETTE = px.colors.qualitative.Set2
_TEMPLATE = "plotly_white"
_DEFAULT_HEIGHT = 400


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_all_charts(
    df: pd.DataFrame,
    eda_result: dict[str, Any],
    *,
    max_scatter_pairs: int = 5,
    max_categorical_cols: int = 8,
    max_numeric_cols: int = 10,
) -> dict[str, list[dict]]:
    """Generate all charts for a dataset.

    Parameters
    ----------
    df:
        Cleaned DataFrame.
    eda_result:
        Output of ``eda.run_eda()``.
    max_scatter_pairs:
        Limit scatter plots to top N correlated pairs.
    max_categorical_cols:
        Limit bar charts to first N categorical columns.
    max_numeric_cols:
        Limit histograms to first N numeric columns.

    Returns
    -------
    dict with keys:
        - ``histograms``   : list of histogram + box subplot figures
        - ``bar_charts``   : list of categorical bar chart figures
        - ``line_charts``  : list of time series line chart figures
        - ``scatter_plots``: list of scatter plot figures
        - ``box_plots``    : list of numeric-vs-categorical box figures
        - ``correlation_heatmap``: single heatmap figure (or None)
    """
    col_types = eda_result["column_types"]
    correlations = eda_result["correlations"]

    numeric_cols = col_types["numeric"][:max_numeric_cols]
    cat_cols = col_types["categorical"][:max_categorical_cols]
    dt_cols = col_types["datetime"]
    strong_pairs = correlations["strong_pairs"][:max_scatter_pairs]

    return {
        "histograms": [
            _histogram_with_box(df, col) for col in numeric_cols
        ],
        "bar_charts": [
            _bar_chart(df, col) for col in cat_cols
        ],
        "line_charts": [
            _line_chart(df, col) for col in dt_cols
        ],
        "scatter_plots": [
            _scatter_plot(df, pair["col_a"], pair["col_b"], pair["r"])
            for pair in strong_pairs
        ],
        "box_plots": _numeric_vs_categorical_boxes(df, numeric_cols, cat_cols),
        "correlation_heatmap": _correlation_heatmap(correlations["matrix"])
        if len(numeric_cols) >= 2
        else None,
    }


def generate_single_chart(
    df: pd.DataFrame,
    chart_type: str,
    **kwargs,
) -> dict:
    """Generate a single chart by type name.

    Parameters
    ----------
    df:
        Cleaned DataFrame.
    chart_type:
        One of ``"histogram"``, ``"bar"``, ``"line"``, ``"scatter"``,
        ``"box"``, ``"heatmap"``.
    **kwargs:
        Column names and options specific to the chart type.

    Returns
    -------
    Plotly figure as a JSON-serialisable dict.
    """
    dispatch = {
        "histogram": lambda: _histogram_with_box(df, kwargs["col"]),
        "bar": lambda: _bar_chart(df, kwargs["col"]),
        "line": lambda: _line_chart(df, kwargs["col"]),
        "scatter": lambda: _scatter_plot(
            df, kwargs["col_a"], kwargs["col_b"], kwargs.get("r")
        ),
        "box": lambda: _box_plot(df, kwargs["numeric_col"], kwargs.get("cat_col")),
        "heatmap": lambda: _correlation_heatmap(kwargs["matrix"]),
    }
    if chart_type not in dispatch:
        raise ValueError(
            f"Unknown chart type '{chart_type}'. "
            f"Choose from: {', '.join(dispatch.keys())}"
        )
    return dispatch[chart_type]()


# ---------------------------------------------------------------------------
# Individual chart builders
# ---------------------------------------------------------------------------

def _histogram_with_box(df: pd.DataFrame, col: str) -> dict:
    """Histogram (top) + box plot (bottom) for a numeric column."""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.05,
    )

    # Histogram
    fig.add_trace(
        go.Histogram(
            x=df[col].dropna(),
            name=col,
            marker_color=_PALETTE[0],
            opacity=0.85,
            nbinsx=30,
            showlegend=False,
        ),
        row=1, col=1,
    )

    # Box plot
    fig.add_trace(
        go.Box(
            x=df[col].dropna(),
            name=col,
            marker_color=_PALETTE[0],
            boxmean="sd",
            showlegend=False,
        ),
        row=2, col=1,
    )

    fig.update_layout(
        title=f"Distribution of {col}",
        template=_TEMPLATE,
        height=_DEFAULT_HEIGHT,
        margin=dict(t=50, b=40, l=60, r=20),
    )
    fig.update_xaxes(title_text=col, row=2, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1)

    return fig.to_dict()


def _bar_chart(df: pd.DataFrame, col: str) -> dict:
    """Horizontal bar chart for a categorical column (sorted by frequency)."""
    counts = df[col].value_counts().head(20)

    fig = go.Figure(
        go.Bar(
            x=counts.values.tolist(),
            y=counts.index.astype(str).tolist(),
            orientation="h",
            marker_color=_PALETTE[1],
            text=counts.values.tolist(),
            textposition="outside",
        )
    )

    fig.update_layout(
        title=f"Value Counts — {col}",
        xaxis_title="Count",
        yaxis_title=col,
        template=_TEMPLATE,
        height=max(_DEFAULT_HEIGHT, len(counts) * 28 + 80),
        margin=dict(t=50, b=40, l=160, r=60),
        yaxis=dict(autorange="reversed"),
    )

    return fig.to_dict()


def _line_chart(df: pd.DataFrame, col: str) -> dict:
    """Line chart showing record count aggregated over time."""
    s = df[col].dropna().sort_values()

    # Infer a sensible aggregation frequency
    range_days = (s.max() - s.min()).days
    if range_days <= 7:
        freq = "h"
        freq_label = "Hourly"
    elif range_days <= 90:
        freq = "D"
        freq_label = "Daily"
    elif range_days <= 730:
        freq = "W"
        freq_label = "Weekly"
    else:
        freq = "ME"
        freq_label = "Monthly"

    counts = (
        df.set_index(col)
        .resample(freq)
        .size()
        .reset_index(name="count")
    )

    fig = px.line(
        counts,
        x=col,
        y="count",
        title=f"{freq_label} Record Count — {col}",
        template=_TEMPLATE,
        color_discrete_sequence=[_PALETTE[2]],
        markers=True,
    )

    fig.update_layout(
        height=_DEFAULT_HEIGHT,
        margin=dict(t=50, b=40, l=60, r=20),
        xaxis_title=col,
        yaxis_title="Record Count",
    )

    return fig.to_dict()


def _scatter_plot(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    r: float | None = None,
) -> dict:
    """Scatter plot for two correlated numeric columns with trend line."""
    subset = df[[col_a, col_b]].dropna()

    title = f"{col_a} vs {col_b}"
    if r is not None:
        title += f"  (r = {r:+.2f})"

    fig = px.scatter(
        subset,
        x=col_a,
        y=col_b,
        trendline="ols",
        trendline_color_override=_PALETTE[3],
        title=title,
        template=_TEMPLATE,
        color_discrete_sequence=[_PALETTE[4]],
        opacity=0.65,
    )

    fig.update_layout(
        height=_DEFAULT_HEIGHT,
        margin=dict(t=50, b=40, l=60, r=20),
    )

    return fig.to_dict()


def _box_plot(
    df: pd.DataFrame,
    numeric_col: str,
    cat_col: str | None = None,
) -> dict:
    """Box plot — optionally grouped by a categorical column."""
    if cat_col and cat_col in df.columns:
        fig = px.box(
            df,
            x=cat_col,
            y=numeric_col,
            title=f"{numeric_col} by {cat_col}",
            template=_TEMPLATE,
            color=cat_col,
            color_discrete_sequence=_PALETTE,
        )
    else:
        fig = px.box(
            df,
            y=numeric_col,
            title=f"Box Plot — {numeric_col}",
            template=_TEMPLATE,
            color_discrete_sequence=[_PALETTE[0]],
        )

    fig.update_layout(
        height=_DEFAULT_HEIGHT,
        margin=dict(t=50, b=40, l=60, r=20),
        showlegend=False,
    )

    return fig.to_dict()


def _numeric_vs_categorical_boxes(
    df: pd.DataFrame,
    numeric_cols: list[str],
    cat_cols: list[str],
    max_pairs: int = 4,
) -> list[dict]:
    """Generate box plots for the top numeric × categorical combinations.

    Picks the categorical column with the highest cardinality (most groups)
    up to a limit, paired with each numeric column.
    """
    if not numeric_cols or not cat_cols:
        return []

    # Use the first categorical column (usually most meaningful)
    cat_col = cat_cols[0]
    pairs = numeric_cols[:max_pairs]

    return [_box_plot(df, num_col, cat_col) for num_col in pairs]


def _correlation_heatmap(matrix: dict[str, dict]) -> dict:
    """Heatmap of the Pearson correlation matrix."""
    if not matrix:
        return {}

    cols = list(matrix.keys())
    z = [[matrix[row].get(col) for col in cols] for row in cols]

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=cols,
            y=cols,
            colorscale="RdBu",
            zmid=0,
            zmin=-1,
            zmax=1,
            text=[[f"{v:.2f}" if v is not None else "" for v in row] for row in z],
            texttemplate="%{text}",
            textfont=dict(size=11),
            hoverongaps=False,
        )
    )

    fig.update_layout(
        title="Correlation Heatmap",
        template=_TEMPLATE,
        height=max(400, len(cols) * 45 + 100),
        margin=dict(t=60, b=80, l=80, r=20),
        xaxis=dict(tickangle=-45),
    )

    return fig.to_dict()
