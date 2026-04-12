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

import json
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _fig_to_dict(fig) -> dict:
    """Serialise a Plotly figure to a plain JSON-safe dict.

    fig.to_dict() in Plotly 6.x returns objects with non-serialisable types.
    Going through JSON ensures all values are native Python types.
    """
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# Theme / defaults
# ---------------------------------------------------------------------------

_PALETTE = [
    "#1d9694",  # brand teal
    "#6366f1",  # indigo
    "#f59e0b",  # amber
    "#10b981",  # emerald
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#3b82f6",  # blue
    "#f97316",  # orange
]
_DEFAULT_HEIGHT = 420

# Shared layout defaults applied to all charts
_LAYOUT_DEFAULTS = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#374151"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel=dict(
        bgcolor="white",
        font_size=12,
        font_family="Inter, system-ui, sans-serif",
        bordercolor="#e5e7eb",
    ),
    xaxis=dict(
        gridcolor="#f3f4f6",
        linecolor="#e5e7eb",
        tickfont=dict(size=11, color="#6b7280"),
        title_font=dict(size=12, color="#374151"),
        showgrid=True,
    ),
    yaxis=dict(
        gridcolor="#f3f4f6",
        linecolor="#e5e7eb",
        tickfont=dict(size=11, color="#6b7280"),
        title_font=dict(size=12, color="#374151"),
        showgrid=True,
    ),
    title=dict(
        font=dict(size=14, color="#111827", family="Inter, system-ui, sans-serif"),
        x=0,
        xanchor="left",
        pad=dict(l=0, b=8),
    ),
)


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
        "bar": lambda: (
            _grouped_bar_chart(df, kwargs["col_a"], kwargs["col_b"])
            if "col_a" in kwargs and "col_b" in kwargs
            else _bar_chart(df, kwargs["col"])
        ),
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

def _apply_defaults(fig, extra: dict | None = None) -> None:
    """Apply shared layout defaults to any figure in-place."""
    updates = {**_LAYOUT_DEFAULTS}
    if extra:
        updates.update(extra)
    fig.update_layout(**updates)


def _histogram_with_box(df: pd.DataFrame, col: str) -> dict:
    """Histogram (top) + mini box strip (bottom) for a numeric column."""
    series = df[col].dropna()
    mean_val = float(series.mean())
    median_val = float(series.median())

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.8, 0.2],
        vertical_spacing=0.04,
    )

    fig.add_trace(
        go.Histogram(
            x=series,
            name=col,
            marker=dict(color=_PALETTE[0], opacity=0.85, line=dict(color="white", width=0.5)),
            nbinsx=35,
            showlegend=False,
            hovertemplate="Range: %{x}<br>Count: %{y}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Mean and median lines
    for val, label, color in [(mean_val, "Mean", _PALETTE[1]), (median_val, "Median", _PALETTE[4])]:
        fig.add_vline(x=val, line_width=1.5, line_dash="dash", line_color=color,
                      annotation_text=f"{label}: {val:,.2f}",
                      annotation_font_size=10, annotation_font_color=color, row=1, col=1)

    fig.add_trace(
        go.Box(
            x=series,
            name=col,
            marker=dict(color=_PALETTE[0], size=4),
            line=dict(color=_PALETTE[0]),
            fillcolor=f"rgba(29,150,148,0.15)",
            boxmean=True,
            showlegend=False,
            hovertemplate="Q1: %{q1:.2f}<br>Median: %{median:.2f}<br>Q3: %{q3:.2f}<extra></extra>",
        ),
        row=2, col=1,
    )

    _apply_defaults(fig, dict(
        title=dict(text=f"Distribution of <b>{col}</b>", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=55, b=45, l=65, r=25),
    ))
    fig.update_xaxes(title_text=col, row=2, col=1, showgrid=False)
    fig.update_yaxes(title_text="Count", row=1, col=1, gridcolor="#f3f4f6")
    fig.update_yaxes(showticklabels=False, row=2, col=1, showgrid=False)

    return _fig_to_dict(fig)


def _bar_chart(df: pd.DataFrame, col: str) -> dict:
    """Horizontal bar chart — value counts of a categorical column."""
    counts = df[col].value_counts().head(20)
    pcts   = (counts / counts.sum() * 100).round(1)

    fig = go.Figure(
        go.Bar(
            x=counts.values.tolist(),
            y=counts.index.astype(str).tolist(),
            orientation="h",
            marker=dict(
                color=counts.values.tolist(),
                colorscale=[[0, f"rgba(29,150,148,0.4)"], [1, _PALETTE[0]]],
                showscale=False,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=[f"{p}%" for p in pcts.values],
            textposition="outside",
            textfont=dict(size=11, color="#6b7280"),
            hovertemplate="%{y}: %{x:,} (%{text})<extra></extra>",
        )
    )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col}</b> — Top Categories", **_LAYOUT_DEFAULTS["title"]),
        xaxis_title="Count",
        yaxis=dict(**_LAYOUT_DEFAULTS["yaxis"], autorange="reversed"),
        height=max(_DEFAULT_HEIGHT, len(counts) * 32 + 90),
        margin=dict(t=55, b=50, l=170, r=80),
    ))

    return _fig_to_dict(fig)


def _grouped_bar_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> dict:
    """Vertical bar chart — mean of a numeric column grouped by a categorical column."""
    grouped = (
        df.groupby(cat_col)[num_col]
        .agg(["mean", "count"])
        .sort_values("mean", ascending=False)
        .head(20)
    )

    fig = go.Figure(
        go.Bar(
            x=grouped.index.astype(str).tolist(),
            y=grouped["mean"].round(2).tolist(),
            marker=dict(
                color=grouped["mean"].tolist(),
                colorscale=[[0, "rgba(29,150,148,0.4)"], [1, _PALETTE[0]]],
                showscale=False,
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=[f"{v:,.2f}" for v in grouped["mean"]],
            textposition="outside",
            textfont=dict(size=11, color="#6b7280"),
            hovertemplate="%{x}<br>Mean: %{y:,.2f}<extra></extra>",
        )
    )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{num_col}</b> by <b>{cat_col}</b>", **_LAYOUT_DEFAULTS["title"]),
        xaxis_title=cat_col,
        yaxis_title=f"Mean {num_col}",
        height=_DEFAULT_HEIGHT,
        margin=dict(t=55, b=80, l=65, r=25),
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-35),
    ))

    return _fig_to_dict(fig)


def _line_chart(df: pd.DataFrame, col: str) -> dict:
    """Line chart showing record count aggregated over time."""
    s = df[col].dropna().sort_values()

    range_days = (s.max() - s.min()).days
    if range_days <= 7:
        freq, freq_label = "h", "Hourly"
    elif range_days <= 90:
        freq, freq_label = "D", "Daily"
    elif range_days <= 730:
        freq, freq_label = "W", "Weekly"
    else:
        freq, freq_label = "ME", "Monthly"

    counts = df.set_index(col).resample(freq).size().reset_index(name="count")

    fig = px.line(
        counts, x=col, y="count",
        color_discrete_sequence=[_PALETTE[0]],
    )
    fig.update_traces(
        line=dict(width=2.5),
        mode="lines+markers",
        marker=dict(size=5, color=_PALETTE[0]),
        hovertemplate="%{x}<br>Count: %{y:,}<extra></extra>",
    )
    # Fill under line
    fig.update_traces(fill="tozeroy", fillcolor=f"rgba(29,150,148,0.08)")

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{freq_label} Record Count</b> — {col}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=55, b=50, l=65, r=25),
        xaxis_title=col,
        yaxis_title="Count",
    ))

    return _fig_to_dict(fig)


def _scatter_plot(df: pd.DataFrame, col_a: str, col_b: str, r: float | None = None) -> dict:
    """Scatter plot with OLS trend line and correlation annotation."""
    subset = df[[col_a, col_b]].dropna()

    r_label = f"  (r = {r:+.2f})" if r is not None else ""

    fig = px.scatter(
        subset, x=col_a, y=col_b,
        trendline="ols",
        trendline_color_override=_PALETTE[1],
        color_discrete_sequence=[_PALETTE[0]],
        opacity=0.55,
    )
    fig.update_traces(
        selector=dict(mode="markers"),
        marker=dict(size=6, line=dict(color="white", width=0.5)),
        hovertemplate=f"{col_a}: %{{x:,.2f}}<br>{col_b}: %{{y:,.2f}}<extra></extra>",
    )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col_a}</b> vs <b>{col_b}</b>{r_label}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=55, b=50, l=65, r=25),
        xaxis_title=col_a,
        yaxis_title=col_b,
    ))

    return _fig_to_dict(fig)


def _box_plot(df: pd.DataFrame, numeric_col: str, cat_col: str | None = None) -> dict:
    """Box plot — optionally grouped by a categorical column."""
    if cat_col and cat_col in df.columns:
        # Limit categories to top 12 by count
        top_cats = df[cat_col].value_counts().head(12).index.tolist()
        plot_df  = df[df[cat_col].isin(top_cats)]
        fig = px.box(
            plot_df, x=cat_col, y=numeric_col,
            color=cat_col,
            color_discrete_sequence=_PALETTE,
            points=False,
        )
        title_text = f"<b>{numeric_col}</b> by <b>{cat_col}</b>"
    else:
        fig = px.box(
            df, y=numeric_col,
            color_discrete_sequence=[_PALETTE[0]],
            points="outliers",
        )
        title_text = f"<b>{numeric_col}</b> — Box Plot"

    fig.update_traces(
        marker=dict(size=4, opacity=0.6),
        hovertemplate="Q1: %{q1:.2f}<br>Median: %{median:.2f}<br>Q3: %{q3:.2f}<extra></extra>",
    )
    _apply_defaults(fig, dict(
        title=dict(text=title_text, **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=55, b=60, l=65, r=25),
        showlegend=False,
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-30),
    ))

    return _fig_to_dict(fig)


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
            colorscale=[
                [0.0, "#ef4444"],
                [0.25, "#fca5a5"],
                [0.5, "#f9fafb"],
                [0.75, "#6ee7e7"],
                [1.0, "#1d9694"],
            ],
            zmid=0,
            zmin=-1,
            zmax=1,
            text=[[f"{v:.2f}" if v is not None else "" for v in row] for row in z],
            texttemplate="%{text}",
            textfont=dict(size=11, color="#374151"),
            hoverongaps=False,
            hovertemplate="%{x} × %{y}<br>r = %{z:.3f}<extra></extra>",
        )
    )

    n = len(cols)
    cell_size = 48
    _apply_defaults(fig, dict(
        title=dict(text="<b>Correlation Matrix</b>", **_LAYOUT_DEFAULTS["title"]),
        height=max(420, n * cell_size + 140),
        margin=dict(t=60, b=100, l=100, r=30),
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-40, side="bottom"),
        yaxis=dict(**_LAYOUT_DEFAULTS["yaxis"], autorange="reversed"),
    ))

    return _fig_to_dict(fig)
