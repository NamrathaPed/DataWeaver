"""
Chart Engine Module
-------------------
Auto-generates Plotly charts based on EDA results and column types.
Returns Plotly figure dicts (JSON-serialisable) so they can be sent
directly from FastAPI and rendered by Plotly.js on the React frontend.
"""

from __future__ import annotations

import json
import warnings
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats
from scipy.cluster import hierarchy as sch
from scipy.stats import gaussian_kde


def _fig_to_dict(fig) -> dict:
    return json.loads(fig.to_json())


# ---------------------------------------------------------------------------
# Theme / palette
# ---------------------------------------------------------------------------

_PALETTE = [
    "#1d9694",  # teal
    "#6366f1",  # indigo
    "#f59e0b",  # amber
    "#10b981",  # emerald
    "#ef4444",  # red
    "#8b5cf6",  # violet
    "#3b82f6",  # blue
    "#f97316",  # orange
    "#ec4899",  # pink
    "#14b8a6",  # cyan
]
_GREY = "#9ca3af"
_DEFAULT_HEIGHT = 480
_LAYOUT_DEFAULTS = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#374151"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hoverlabel=dict(bgcolor="white", font_size=12,
                    font_family="Inter, system-ui, sans-serif", bordercolor="#e5e7eb"),
    xaxis=dict(gridcolor="#f3f4f6", linecolor="#e5e7eb",
               tickfont=dict(size=11, color="#6b7280"),
               title_font=dict(size=12, color="#374151"), showgrid=True),
    yaxis=dict(gridcolor="#f3f4f6", linecolor="#e5e7eb",
               tickfont=dict(size=11, color="#6b7280"),
               title_font=dict(size=12, color="#374151"), showgrid=True),
    title=dict(font=dict(size=14, color="#111827", family="Inter, system-ui, sans-serif"),
               x=0, xanchor="left", pad=dict(l=0, b=4)),
)


def _apply_defaults(fig, extra: dict | None = None) -> None:
    updates = {**_LAYOUT_DEFAULTS}
    if extra:
        updates.update(extra)
    fig.update_layout(**updates)


def _subtitle(text: str) -> str:
    return f"<sub><span style='color:#6b7280;font-size:11px'>{text}</span></sub>"


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
    col_types   = eda_result["column_types"]
    correlations = eda_result["correlations"]

    numeric_cols  = col_types["numeric"][:max_numeric_cols]
    cat_cols      = col_types["categorical"][:max_categorical_cols]
    dt_cols       = col_types["datetime"]
    strong_pairs  = correlations["strong_pairs"][:max_scatter_pairs]

    return {
        "histograms":   [_histogram(df, col) for col in numeric_cols],
        "bar_charts":   [_bar_chart(df, col) for col in cat_cols],
        "line_charts":  [_line_chart(df, col) for col in dt_cols],
        "scatter_plots": [
            _scatter_plot(df, p["col_a"], p["col_b"], p["r"])
            for p in strong_pairs
        ],
        "box_plots":    _numeric_vs_categorical_boxes(df, numeric_cols, cat_cols),
        "correlation_heatmap": _correlation_heatmap(
            correlations["matrix"], df, eda_result.get("summary", {})
        ) if len(numeric_cols) >= 2 else None,
    }


def generate_single_chart(df: pd.DataFrame, chart_type: str, **kwargs) -> dict:
    """Generate a single chart. Applies smart selection rules before rendering."""

    # ── Smart selection overrides ────────────────────────────────────────────
    if chart_type == "histogram":
        col = kwargs.get("col")
        if col and col in df.columns:
            n_unique = df[col].nunique()
            if n_unique < 8:
                # Few unique values → bar chart is more readable
                return _bar_chart(df, col)

    if chart_type == "bar":
        col = kwargs.get("col") or kwargs.get("col_a")
        if col and col in df.columns and not kwargs.get("col_b"):
            if df[col].nunique() > 150:
                # Very high cardinality → treemap
                return _treemap(df, col)

    if chart_type == "line":
        col = kwargs.get("col")
        if col and col in df.columns:
            n_points = df[col].dropna().shape[0]
            if n_points < 6:
                return _scatter_plot(df, col, col)

    if chart_type == "scatter":
        col_a = kwargs.get("col_a")
        col_b = kwargs.get("col_b")
        if col_a and col_b:
            n = df[[col_a, col_b]].dropna().shape[0]
            if n > 2000:
                return _density_scatter(df, col_a, col_b, kwargs.get("r"))

    # ── Normal dispatch ──────────────────────────────────────────────────────
    dispatch = {
        "histogram": lambda: _histogram(df, kwargs["col"]),
        "bar": lambda: (
            _grouped_bar_chart(df, kwargs["col_a"], kwargs["col_b"])
            if "col_a" in kwargs and "col_b" in kwargs
            else _bar_chart(df, kwargs.get("col") or kwargs.get("col_a"))
        ),
        "line":      lambda: _line_chart(df, kwargs["col"]),
        "scatter":   lambda: _scatter_plot(df, kwargs["col_a"], kwargs["col_b"], kwargs.get("r"), kwargs.get("color_col")),
        "box":       lambda: _box_or_violin(df, kwargs["numeric_col"], kwargs.get("cat_col")),
        "violin":    lambda: _box_or_violin(df, kwargs["numeric_col"], kwargs.get("cat_col"), force_violin=True),
        "heatmap":   lambda: _correlation_heatmap(kwargs["matrix"], df),
        "treemap":   lambda: _treemap(df, kwargs.get("col"), kwargs.get("col_a"), kwargs.get("col_b")),
        "funnel":    lambda: _funnel_chart(df, kwargs["col_a"], kwargs["col_b"]),
        "waterfall": lambda: _waterfall_chart(df, kwargs["col_a"], kwargs["col_b"]),
        "bubble":    lambda: _bubble_chart(df, kwargs["col_a"], kwargs["col_b"], kwargs["col_c"], kwargs.get("col_d")),
        "pairplot":  lambda: _pairplot(df, kwargs["columns"]),
    }
    if chart_type not in dispatch:
        raise ValueError(f"Unknown chart type '{chart_type}'. Choose from: {', '.join(dispatch.keys())}")
    return dispatch[chart_type]()


# ---------------------------------------------------------------------------
# Histogram (with KDE + rug + adaptive bins + correct vlines)
# ---------------------------------------------------------------------------

def _histogram(df: pd.DataFrame, col: str) -> dict:
    series = df[col].dropna()
    n = len(series)
    if n == 0:
        return {}

    mean_val   = float(series.mean())
    median_val = float(series.median())
    std_val    = float(series.std())
    p25        = float(series.quantile(0.25))
    p75        = float(series.quantile(0.75))

    # Adaptive bin count: Freedman-Diaconis, capped sensibly
    iqr = p75 - p25
    if iqr > 0:
        h = 2 * iqr / (n ** (1 / 3))
        n_bins = int(np.ceil((series.max() - series.min()) / h)) if h > 0 else 30
        n_bins = max(10, min(n_bins, 80))
    else:
        n_bins = int(np.ceil(1 + 3.322 * np.log10(n)))  # Sturges

    # KDE
    kde_x = np.linspace(float(series.min()), float(series.max()), 300)
    try:
        kde = gaussian_kde(series, bw_method="scott")
        kde_y = kde(kde_x)
    except Exception:
        kde_y = None

    # Rug sample (max 500 points)
    rug_sample = series.sample(min(500, n), random_state=42) if n > 500 else series

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.88, 0.12],
        vertical_spacing=0.02,
    )

    # Histogram bars
    fig.add_trace(go.Histogram(
        x=series,
        name=col,
        nbinsx=n_bins,
        marker=dict(color=_PALETTE[0], opacity=0.80, line=dict(color="white", width=0.5)),
        showlegend=False,
        hovertemplate="Range: %{x}<br>Count: %{y}<br>(%{customdata:.1f}% of total)<extra></extra>",
        customdata=[100 / n] * n,
        yaxis="y1",
    ), row=1, col=1)

    # KDE curve (secondary y-axis)
    if kde_y is not None:
        fig.add_trace(go.Scatter(
            x=kde_x.tolist(), y=kde_y.tolist(),
            mode="lines",
            name="KDE",
            line=dict(color=_PALETTE[1], width=2.5),
            yaxis="y2",
            showlegend=True,
            hovertemplate="x: %{x:.2f}<br>Density: %{y:.4f}<extra>KDE</extra>",
        ), row=1, col=1)

    # Rug plot (row 2)
    fig.add_trace(go.Scatter(
        x=rug_sample.tolist(),
        y=[0] * len(rug_sample),
        mode="markers",
        marker=dict(symbol="line-ns-open", size=8, color=_PALETTE[0], opacity=0.4, line=dict(width=1)),
        showlegend=False,
        hovertemplate="%{x:.3f}<extra>Rug</extra>",
    ), row=2, col=1)

    # Vertical markers via add_shape (add_vline doesn't support row=)
    markers = [
        (mean_val,   _PALETTE[2], "Mean"),
        (median_val, _PALETTE[4], "Median"),
        (p25,        _PALETTE[5], "Q1"),
        (p75,        _PALETTE[3], "Q3"),
    ]
    for val, colour, label in markers:
        fig.add_shape(type="line", x0=val, x1=val, y0=0, y1=1,
                      xref="x", yref="y domain", line=dict(color=colour, width=1.5, dash="dash"), row=1, col=1)
        fig.add_annotation(x=val, y=1.02, xref="x", yref="y domain",
                           text=f"{label}<br>{val:,.2f}", showarrow=False,
                           font=dict(size=9, color=colour), yanchor="bottom", row=1, col=1)

    subtitle = f"Mean: {mean_val:,.2f} | Median: {median_val:,.2f} | Std: {std_val:,.2f} | n: {n:,}"
    _apply_defaults(fig, dict(
        title=dict(text=f"Distribution of <b>{col}</b><br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=40, l=65, r=25),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, showticklabels=False, title=""),
        legend=dict(x=0.98, y=0.98, xanchor="right", yanchor="top", bgcolor="rgba(255,255,255,0.7)"),
    ))
    fig.update_xaxes(title_text=col, row=2, col=1)
    fig.update_yaxes(title_text="Count", row=1, col=1, gridcolor="#f3f4f6")
    fig.update_yaxes(showticklabels=False, showgrid=False, row=2, col=1)

    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Bar chart (distinct colours, Other bucket, count+pct labels)
# ---------------------------------------------------------------------------

def _bar_chart(df: pd.DataFrame, col: str) -> dict:
    if col is None or col not in df.columns:
        return {}
    counts_full = df[col].value_counts()
    total = int(counts_full.sum())
    n_rows = len(df)

    top12 = counts_full.head(12)
    other_count = int(counts_full.iloc[12:].sum()) if len(counts_full) > 12 else 0

    labels  = top12.index.astype(str).tolist()
    values  = top12.values.tolist()
    colours = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]

    if other_count > 0:
        labels.append("Other")
        values.append(other_count)
        colours.append(_GREY)

    pcts = [v / total * 100 for v in values]
    text_labels = [f"{v:,} ({p:.1f}%)" for v, p in zip(values, pcts)]

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(color=colours, line=dict(color="rgba(0,0,0,0)", width=0)),
        text=text_labels,
        textposition="outside",
        textfont=dict(size=10, color="#374151"),
        hovertemplate="%{y}<br>Count: %{x:,}<br>Share: %{customdata:.1f}%<extra></extra>",
        customdata=pcts,
    ))

    subtitle = f"n = {n_rows:,} rows | {len(counts_full)} unique values"
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col}</b> — Category Counts<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        xaxis_title="Count",
        yaxis=dict(**_LAYOUT_DEFAULTS["yaxis"], autorange="reversed"),
        height=max(_DEFAULT_HEIGHT, len(labels) * 38 + 100),
        margin=dict(t=75, b=50, l=170, r=110),
    ))
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Grouped bar chart (mean of numeric by categorical, with error bars)
# ---------------------------------------------------------------------------

def _grouped_bar_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> dict:
    grouped = (
        df.groupby(cat_col)[num_col]
        .agg(["mean", "count", "std"])
        .sort_values("mean", ascending=False)
        .head(15)
    )
    # Standard error
    grouped["se"] = grouped["std"] / np.sqrt(grouped["count"])

    labels  = grouped.index.astype(str).tolist()
    colours = [_PALETTE[i % len(_PALETTE)] for i in range(len(labels))]

    fig = go.Figure(go.Bar(
        x=labels,
        y=grouped["mean"].round(3).tolist(),
        error_y=dict(type="data", array=grouped["se"].round(3).tolist(), visible=True,
                     color="#6b7280", thickness=1.5, width=4),
        marker=dict(color=colours, line=dict(color="rgba(0,0,0,0)", width=0)),
        text=[f"{v:,.2f}" for v in grouped["mean"]],
        textposition="outside",
        textfont=dict(size=10, color="#374151"),
        hovertemplate=(
            "%{x}<br>Mean: %{y:,.3f}<br>"
            "n: %{customdata[0]:,}<br>SE: ±%{customdata[1]:.3f}<extra></extra>"
        ),
        customdata=list(zip(grouped["count"].tolist(), grouped["se"].round(3).tolist())),
    ))

    overall_mean = float(df[num_col].mean())
    subtitle = f"Mean {num_col}: {overall_mean:,.2f} overall | error bars = ±1 SE"
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{num_col}</b> by <b>{cat_col}</b><br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-35),
        yaxis_title=f"Mean {num_col}",
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=90, l=65, r=25),
    ))
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Line chart (adaptive freq, range selector, peak/trough annotations, rolling avg)
# ---------------------------------------------------------------------------

def _line_chart(df: pd.DataFrame, col: str) -> dict:
    s = df[col].dropna().sort_values()
    if len(s) < 2:
        return {}

    range_minutes = (s.max() - s.min()).total_seconds() / 60

    if range_minutes <= 60 * 6:
        freq, freq_label = "15min", "15-Minute"
    elif range_minutes <= 60 * 24:
        freq, freq_label = "6h", "6-Hourly"
    elif range_minutes <= 60 * 24 * 7:
        freq, freq_label = "h", "Hourly"
    elif range_minutes <= 60 * 24 * 90:
        freq, freq_label = "D", "Daily"
    elif range_minutes <= 60 * 24 * 730:
        freq, freq_label = "W", "Weekly"
    elif range_minutes <= 60 * 24 * 365 * 3:
        freq, freq_label = "ME", "Monthly"
    else:
        freq, freq_label = "QE", "Quarterly"

    try:
        counts = df.set_index(col).resample(freq).size().reset_index(name="count")
    except Exception:
        counts = df.set_index(col).resample("D").size().reset_index(name="count")
        freq_label = "Daily"

    # Rolling average (7 periods)
    counts["rolling"] = counts["count"].rolling(7, min_periods=1).mean()

    peak_idx  = counts["count"].idxmax()
    trough_idx = counts["count"].idxmin()
    peak_row   = counts.loc[peak_idx]
    trough_row = counts.loc[trough_idx]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=counts[col], y=counts["count"],
        mode="lines+markers",
        name="Count",
        line=dict(color=_PALETTE[1], width=2),
        marker=dict(size=4, color=_PALETTE[1]),
        fill="tozeroy", fillcolor="rgba(99,102,241,0.07)",
        hovertemplate=f"{col}: %{{x}}<br>Count: %{{y:,}}<extra>Actual</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=counts[col], y=counts["rolling"].round(1),
        mode="lines",
        name="7-period avg",
        line=dict(color=_PALETTE[2], width=2, dash="dot"),
        hovertemplate="Rolling avg: %{y:.1f}<extra>7-period avg</extra>",
    ))

    # Peak annotation
    fig.add_annotation(
        x=peak_row[col], y=peak_row["count"],
        text=f"Peak: {peak_row['count']:,}",
        showarrow=True, arrowhead=2, arrowcolor=_PALETTE[4],
        font=dict(size=10, color=_PALETTE[4]), bgcolor="white",
        bordercolor=_PALETTE[4], borderwidth=1, borderpad=3,
    )
    # Trough annotation
    fig.add_annotation(
        x=trough_row[col], y=trough_row["count"],
        text=f"Low: {trough_row['count']:,}",
        showarrow=True, arrowhead=2, arrowcolor=_PALETTE[5],
        font=dict(size=10, color=_PALETTE[5]), bgcolor="white",
        bordercolor=_PALETTE[5], borderwidth=1, borderpad=3, ay=40,
    )

    subtitle = f"{freq_label} aggregation | {len(counts)} periods | 7-period rolling avg overlaid"
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{freq_label} Record Count</b> — {col}<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=60, l=65, r=25),
        xaxis=dict(
            **_LAYOUT_DEFAULTS["xaxis"],
            title_text=col,
            rangeselector=dict(
                buttons=[
                    dict(count=1,  label="1M", step="month", stepmode="backward"),
                    dict(count=3,  label="3M", step="month", stepmode="backward"),
                    dict(count=6,  label="6M", step="month", stepmode="backward"),
                    dict(count=1,  label="1Y", step="year",  stepmode="backward"),
                    dict(step="all", label="All"),
                ],
                bgcolor="rgba(0,0,0,0)", activecolor=_PALETTE[1],
                font=dict(size=10),
            ),
            rangeslider=dict(visible=False),
        ),
        yaxis_title="Count",
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.7)"),
    ))
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Scatter plot (R² annotation, density fallback, optional colour col)
# ---------------------------------------------------------------------------

def _scatter_plot(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    r: float | None = None,
    color_col: str | None = None,
) -> dict:
    subset = df[[col_a, col_b] + ([color_col] if color_col and color_col in df.columns else [])].dropna()
    n = len(subset)

    # Density fallback for large datasets
    if n > 2000:
        return _density_scatter(df, col_a, col_b, r)

    r_val = r
    if r_val is None and n >= 3:
        try:
            r_val, _ = scipy_stats.pearsonr(subset[col_a], subset[col_b])
        except Exception:
            pass

    r2 = r_val ** 2 if r_val is not None else None

    use_color = color_col and color_col in subset.columns
    if use_color:
        fig = px.scatter(
            subset, x=col_a, y=col_b,
            color=color_col,
            trendline="ols",
            color_discrete_sequence=_PALETTE,
            opacity=0.6,
        )
    else:
        fig = px.scatter(
            subset, x=col_a, y=col_b,
            trendline="ols",
            trendline_color_override=_PALETTE[4],
            color_discrete_sequence=[_PALETTE[6]],
            opacity=0.55,
        )

    fig.update_traces(
        selector=dict(mode="markers"),
        marker=dict(size=6, line=dict(color="white", width=0.4)),
        hovertemplate=(
            f"{col_a}: %{{x:,.3f}}<br>{col_b}: %{{y:,.3f}}"
            + (f"<br>Mean {col_a}: {subset[col_a].mean():,.2f}" if r_val else "")
            + "<extra></extra>"
        ),
    )

    r_label  = f"r = {r_val:+.3f}" if r_val is not None else ""
    r2_label = f"R² = {r2:.3f}" if r2 is not None else ""
    subtitle = f"{r_label} | {r2_label} | n = {n:,}" if r_label else f"n = {n:,}"

    if r2 is not None:
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.02 if (r_val or 0) < 0 else 0.98,
            y=0.97,
            xanchor="left" if (r_val or 0) < 0 else "right",
            text=f"<b>R² = {r2:.3f}</b><br>r = {r_val:+.3f}",
            showarrow=False,
            font=dict(size=11, color="#111827"),
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#e5e7eb", borderwidth=1, borderpad=4,
        )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col_a}</b> vs <b>{col_b}</b><br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=50, l=65, r=25),
        xaxis_title=col_a, yaxis_title=col_b,
    ))
    return _fig_to_dict(fig)


def _density_scatter(df: pd.DataFrame, col_a: str, col_b: str, r: float | None = None) -> dict:
    """2D density contour for large datasets with 300-point scatter overlay."""
    subset = df[[col_a, col_b]].dropna()
    sample = subset.sample(min(300, len(subset)), random_state=42)

    r_val = r
    if r_val is None:
        try:
            r_val, _ = scipy_stats.pearsonr(subset[col_a], subset[col_b])
        except Exception:
            pass

    r2 = r_val ** 2 if r_val is not None else None
    subtitle = (f"r = {r_val:+.3f} | R² = {r2:.3f} | n = {len(subset):,} (density + 300-pt sample)"
                if r_val is not None else f"n = {len(subset):,}")

    fig = go.Figure()
    fig.add_trace(go.Histogram2dContour(
        x=subset[col_a], y=subset[col_b],
        colorscale=[[0, "rgba(99,102,241,0)"], [0.5, "rgba(99,102,241,0.3)"], [1, _PALETTE[1]]],
        showscale=False, ncontours=12,
        hovertemplate=f"{col_a}: %{{x:.2f}}<br>{col_b}: %{{y:.2f}}<extra>Density</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=sample[col_a], y=sample[col_b],
        mode="markers",
        marker=dict(size=5, color=_PALETTE[6], opacity=0.5, line=dict(color="white", width=0.3)),
        showlegend=False,
        hovertemplate=f"{col_a}: %{{x:.3f}}<br>{col_b}: %{{y:.3f}}<extra>Sample</extra>",
    ))

    if r2 is not None:
        fig.add_annotation(
            xref="paper", yref="paper", x=0.98, y=0.97, xanchor="right",
            text=f"<b>R² = {r2:.3f}</b><br>r = {r_val:+.3f}",
            showarrow=False, font=dict(size=11, color="#111827"),
            bgcolor="rgba(255,255,255,0.8)", bordercolor="#e5e7eb", borderwidth=1, borderpad=4,
        )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col_a}</b> vs <b>{col_b}</b> — Density<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT, margin=dict(t=75, b=50, l=65, r=25),
        xaxis_title=col_a, yaxis_title=col_b,
    ))
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# Box / Violin (dynamic based on n per group + mean marker + n annotations)
# ---------------------------------------------------------------------------

def _box_or_violin(
    df: pd.DataFrame,
    numeric_col: str,
    cat_col: str | None = None,
    force_violin: bool = False,
) -> dict:
    if cat_col and cat_col in df.columns:
        top_cats = df[cat_col].value_counts().head(12).index.tolist()
        plot_df  = df[df[cat_col].isin(top_cats)].copy()
        group_counts = plot_df[cat_col].value_counts()
        avg_n = group_counts.mean()
        use_violin = force_violin or avg_n > 50
        show_points = "all" if avg_n < 300 else ("outliers" if avg_n < 2000 else False)

        if use_violin:
            fig = px.violin(
                plot_df, x=cat_col, y=numeric_col,
                color=cat_col,
                color_discrete_sequence=_PALETTE,
                box=True,
                points=show_points,
            )
        else:
            fig = px.box(
                plot_df, x=cat_col, y=numeric_col,
                color=cat_col,
                color_discrete_sequence=_PALETTE,
                points=show_points,
            )

        # Mean markers per group
        for i, cat in enumerate(top_cats):
            g = plot_df[plot_df[cat_col] == cat][numeric_col].dropna()
            if len(g) == 0:
                continue
            fig.add_trace(go.Scatter(
                x=[str(cat)], y=[g.mean()],
                mode="markers",
                marker=dict(symbol="diamond", size=10, color="white",
                            line=dict(color=_PALETTE[i % len(_PALETTE)], width=2)),
                showlegend=False,
                hovertemplate=f"Mean: %{{y:,.3f}}<extra>{cat}</extra>",
            ))

        # n= annotations below x-axis labels
        for cat in top_cats:
            n_cat = int(group_counts.get(cat, 0))
            fig.add_annotation(
                x=str(cat), y=-0.12, xref="x", yref="paper",
                text=f"n={n_cat:,}", showarrow=False,
                font=dict(size=9, color="#9ca3af"), yanchor="top",
            )

        title_text = f"<b>{numeric_col}</b> by <b>{cat_col}</b>"
        subtitle   = f"{'Violin' if use_violin else 'Box'} | {len(top_cats)} groups | mean = ◆"
    else:
        n_total  = df[numeric_col].dropna().shape[0]
        show_pts = "all" if n_total < 300 else ("outliers" if n_total < 2000 else False)
        use_violin = force_violin or n_total > 50

        if use_violin:
            fig = px.violin(df, y=numeric_col, color_discrete_sequence=[_PALETTE[5]],
                            box=True, points=show_pts)
        else:
            fig = px.box(df, y=numeric_col, color_discrete_sequence=[_PALETTE[5]],
                         points=show_pts)

        mean_v = float(df[numeric_col].mean())
        fig.add_trace(go.Scatter(
            x=[0], y=[mean_v], mode="markers",
            marker=dict(symbol="diamond", size=12, color="white",
                        line=dict(color=_PALETTE[5], width=2)),
            showlegend=False,
            hovertemplate=f"Mean: {mean_v:,.3f}<extra></extra>",
        ))
        title_text = f"<b>{numeric_col}</b>"
        subtitle   = f"n = {n_total:,} | mean = ◆"

    fig.update_traces(
        selector=dict(type="box"),
        hovertemplate="Q1: %{q1:.2f}<br>Median: %{median:.2f}<br>Q3: %{q3:.2f}<extra></extra>",
    )
    _apply_defaults(fig, dict(
        title=dict(text=f"{title_text}<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=80, l=65, r=25),
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
    if not numeric_cols or not cat_cols:
        return []
    cat_col = cat_cols[0]
    return [_box_or_violin(df, nc, cat_col) for nc in numeric_cols[:max_pairs]]


# ---------------------------------------------------------------------------
# Correlation heatmap (clustered, significance masking, readable text)
# ---------------------------------------------------------------------------

def _correlation_heatmap(
    matrix: dict[str, dict],
    df: pd.DataFrame | None = None,
    summary: dict | None = None,
) -> dict:
    if not matrix:
        return {}

    cols = list(matrix.keys())
    if len(cols) < 2:
        return {}

    raw_z = np.array([[matrix[r].get(c, None) for c in cols] for r in cols], dtype=float)

    # Hierarchical clustering to reorder columns
    try:
        dist = 1 - np.abs(np.nan_to_num(raw_z))
        np.fill_diagonal(dist, 0)
        linkage = sch.linkage(dist, method="average")
        order   = sch.leaves_list(linkage)
        cols    = [cols[i] for i in order]
        raw_z   = raw_z[np.ix_(order, order)]
    except Exception:
        pass

    # P-value matrix for significance masking
    p_matrix = np.ones_like(raw_z)
    if df is not None:
        for i, ci in enumerate(cols):
            for j, cj in enumerate(cols):
                if i == j or ci not in df.columns or cj not in df.columns:
                    continue
                pair = df[[ci, cj]].dropna()
                if len(pair) >= 5:
                    try:
                        _, p = scipy_stats.pearsonr(pair[ci], pair[cj])
                        p_matrix[i, j] = p
                    except Exception:
                        pass

    # Display values: grey out insignificant (p > 0.05)
    display_z = raw_z.copy()
    text_vals = []
    cell_colors = []
    for i in range(len(cols)):
        row_text   = []
        row_colors = []
        for j in range(len(cols)):
            v = raw_z[i, j]
            p = p_matrix[i, j]
            if i == j:
                row_text.append("1.00")
                row_colors.append(v)
            elif np.isnan(v):
                row_text.append("")
                row_colors.append(None)
                display_z[i, j] = None
            elif p > 0.05:
                row_text.append(f"{v:.2f}*")
                row_colors.append(None)   # will show grey
                display_z[i, j] = None
            else:
                row_text.append(f"{v:.2f}")
                row_colors.append(v)
        text_vals.append(row_text)

    # Font colour: white on dark cells, dark on light
    font_colors = []
    for i in range(len(cols)):
        row_fc = []
        for j in range(len(cols)):
            v = raw_z[i, j] if not np.isnan(raw_z[i, j]) else 0
            row_fc.append("white" if abs(v) > 0.5 else "#374151")
        font_colors.append(row_fc)

    n = len(cols)
    cell_px = max(36, min(64, int(480 / n)))
    dim = n * cell_px + 140

    fig = go.Figure(go.Heatmap(
        z=display_z.tolist(),
        x=cols, y=cols,
        colorscale=[
            [0.0, "#ef4444"], [0.25, "#fca5a5"],
            [0.5, "#f9fafb"],
            [0.75, "#6ee7e7"], [1.0, "#1d9694"],
        ],
        zmid=0, zmin=-1, zmax=1,
        text=text_vals,
        texttemplate="%{text}",
        textfont=dict(size=min(13, cell_px // 3 + 7)),
        hoverongaps=False,
        hovertemplate="%{x} × %{y}<br>r = %{z:.3f}<extra></extra>",
        showscale=True,
    ))

    # Grey overlay for insignificant cells
    for i in range(n):
        for j in range(n):
            if i != j and (np.isnan(raw_z[i, j]) or p_matrix[i, j] > 0.05):
                fig.add_shape(
                    type="rect",
                    x0=j - 0.5, x1=j + 0.5,
                    y0=i - 0.5, y1=i + 0.5,
                    fillcolor="rgba(243,244,246,0.75)",
                    line=dict(width=0),
                    layer="above",
                )

    _apply_defaults(fig, dict(
        title=dict(text=f"<b>Correlation Matrix</b><br>{_subtitle('* = p > 0.05 (not significant) | clustered by similarity')}",
                   **_LAYOUT_DEFAULTS["title"]),
        height=max(420, dim),
        width=max(420, dim),
        margin=dict(t=75, b=110, l=110, r=40),
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-45, side="bottom"),
        yaxis=dict(**_LAYOUT_DEFAULTS["yaxis"], autorange="reversed"),
    ))
    return _fig_to_dict(fig)


# ---------------------------------------------------------------------------
# New chart types
# ---------------------------------------------------------------------------

def _treemap(
    df: pd.DataFrame,
    col: str | None = None,
    col_a: str | None = None,
    col_b: str | None = None,
) -> dict:
    if col_a and col_b and col_a in df.columns and col_b in df.columns:
        # Two-level hierarchy
        grouped = df.groupby([col_a, col_b]).size().reset_index(name="count")
        grouped["root"] = "All"
        fig = px.treemap(
            grouped, path=["root", col_a, col_b], values="count",
            color="count",
            color_continuous_scale=["rgba(29,150,148,0.3)", _PALETTE[0]],
        )
        title_text = f"<b>{col_a} → {col_b}</b> Hierarchy"
        subtitle   = f"{len(grouped)} combinations"
    else:
        target = col or col_a
        if not target or target not in df.columns:
            return {}
        counts = df[target].value_counts().reset_index()
        counts.columns = [target, "count"]
        counts["root"] = "All"
        fig = px.treemap(
            counts, path=["root", target], values="count",
            color="count",
            color_continuous_scale=["rgba(99,102,241,0.3)", _PALETTE[1]],
        )
        title_text = f"<b>{target}</b> — Treemap"
        subtitle   = f"{len(counts)} categories"

    fig.update_traces(
        textinfo="label+value+percent root",
        hovertemplate="%{label}<br>Count: %{value:,}<br>%{percentRoot:.1%} of total<extra></extra>",
    )
    _apply_defaults(fig, dict(
        title=dict(text=f"{title_text}<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=20, l=10, r=10),
    ))
    return _fig_to_dict(fig)


def _funnel_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> dict:
    agg = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False).head(12)
    total = agg.sum()
    pcts  = (agg / total * 100).round(1)

    fig = go.Figure(go.Funnel(
        y=agg.index.astype(str).tolist(),
        x=agg.values.tolist(),
        textinfo="value+percent initial",
        marker=dict(color=_PALETTE[:len(agg)]),
        hovertemplate="%{y}<br>Value: %{x:,}<br>%{percentInitial:.1%} of top<extra></extra>",
    ))

    subtitle = f"Total: {total:,.0f} | {len(agg)} stages"
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{num_col}</b> Funnel by <b>{cat_col}</b><br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=40, l=160, r=40),
    ))
    return _fig_to_dict(fig)


def _waterfall_chart(df: pd.DataFrame, cat_col: str, num_col: str) -> dict:
    grouped = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False).head(12)
    labels  = grouped.index.astype(str).tolist()
    values  = grouped.values.tolist()
    total   = sum(values)

    measures = ["relative"] * len(labels) + ["total"]
    labels   = labels + ["Total"]
    values   = values + [total]

    colours = []
    for v in values[:-1]:
        colours.append(_PALETTE[3] if v >= 0 else _PALETTE[4])
    colours.append(_PALETTE[1])

    fig = go.Figure(go.Waterfall(
        name="",
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        connector=dict(line=dict(color="#e5e7eb", width=1, dash="dot")),
        increasing=dict(marker=dict(color=_PALETTE[3])),
        decreasing=dict(marker=dict(color=_PALETTE[4])),
        totals=dict(marker=dict(color=_PALETTE[1])),
        text=[f"{v:,.0f}" for v in values],
        textposition="outside",
        hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>",
    ))

    subtitle = f"Total: {total:,.0f} | {len(labels) - 1} categories"
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{num_col}</b> Waterfall by <b>{cat_col}</b><br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=80, l=65, r=40),
        xaxis=dict(**_LAYOUT_DEFAULTS["xaxis"], tickangle=-30),
        showlegend=False,
    ))
    return _fig_to_dict(fig)


def _bubble_chart(
    df: pd.DataFrame,
    col_a: str, col_b: str, col_c: str,
    col_d: str | None = None,
) -> dict:
    cols = [col_a, col_b, col_c] + ([col_d] if col_d and col_d in df.columns else [])
    subset = df[cols].dropna()
    if subset.empty:
        return {}

    sample = subset.sample(min(500, len(subset)), random_state=42)

    sizes_raw = sample[col_c].values
    size_min, size_max = sizes_raw.min(), sizes_raw.max()
    if size_max > size_min:
        sizes_norm = 8 + 44 * (sizes_raw - size_min) / (size_max - size_min)
    else:
        sizes_norm = np.full(len(sizes_raw), 20.0)

    use_color = col_d and col_d in sample.columns
    if use_color:
        fig = px.scatter(
            sample, x=col_a, y=col_b, size=col_c,
            color=col_d,
            color_discrete_sequence=_PALETTE,
            size_max=50, opacity=0.7,
        )
    else:
        fig = go.Figure(go.Scatter(
            x=sample[col_a], y=sample[col_b],
            mode="markers",
            marker=dict(
                size=sizes_norm.tolist(),
                color=_PALETTE[6], opacity=0.65,
                line=dict(color="white", width=0.5),
                sizemode="diameter",
            ),
            hovertemplate=(
                f"{col_a}: %{{x:,.2f}}<br>{col_b}: %{{y:,.2f}}<br>"
                f"{col_c}: %{{customdata:,.2f}}<extra></extra>"
            ),
            customdata=sample[col_c].values,
        ))

    subtitle = f"Bubble size = {col_c}" + (f" | Colour = {col_d}" if use_color else "")
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>{col_a}</b> vs <b>{col_b}</b> — Bubble<br>{_subtitle(subtitle)}", **_LAYOUT_DEFAULTS["title"]),
        height=_DEFAULT_HEIGHT,
        margin=dict(t=75, b=50, l=65, r=25),
        xaxis_title=col_a, yaxis_title=col_b,
    ))
    return _fig_to_dict(fig)


def _pairplot(df: pd.DataFrame, columns: list[str]) -> dict:
    cols = [c for c in columns if c in df.columns][:6]
    if len(cols) < 2:
        return {}

    n = len(cols)
    subset = df[cols].dropna().sample(min(1000, len(df)), random_state=42)
    fig = make_subplots(rows=n, cols=n, shared_xaxes=False, shared_yaxes=False,
                        horizontal_spacing=0.04, vertical_spacing=0.04)

    for i, ci in enumerate(cols):
        for j, cj in enumerate(cols):
            if i == j:
                # Diagonal: histogram + KDE
                series = subset[ci].dropna()
                n_bins = max(10, min(40, int(1 + 3.322 * np.log10(len(series)))))
                fig.add_trace(go.Histogram(
                    x=series, nbinsx=n_bins,
                    marker_color=_PALETTE[i % len(_PALETTE)], opacity=0.75,
                    showlegend=False,
                    hovertemplate=f"{ci}: %{{x}}<br>Count: %{{y}}<extra></extra>",
                ), row=i + 1, col=j + 1)
            elif i < j:
                # Upper triangle: scatter
                pair = subset[[cj, ci]].dropna()
                fig.add_trace(go.Scatter(
                    x=pair[cj], y=pair[ci],
                    mode="markers",
                    marker=dict(size=4, color=_PALETTE[(i + j) % len(_PALETTE)], opacity=0.5),
                    showlegend=False,
                    hovertemplate=f"{cj}: %{{x:.2f}}<br>{ci}: %{{y:.2f}}<extra></extra>",
                ), row=i + 1, col=j + 1)
            else:
                # Lower triangle: correlation annotation
                pair = subset[[cj, ci]].dropna()
                if len(pair) >= 3:
                    try:
                        r_v, _ = scipy_stats.pearsonr(pair[cj], pair[ci])
                        r_text = f"r = {r_v:+.2f}"
                        colour = _PALETTE[0] if r_v > 0 else _PALETTE[4]
                    except Exception:
                        r_text, colour = "", "#374151"
                else:
                    r_text, colour = "", "#374151"
                fig.add_annotation(
                    xref=f"x{i * n + j + 1}", yref=f"y{i * n + j + 1}",
                    x=0.5, y=0.5, xanchor="center", yanchor="middle",
                    text=f"<b>{r_text}</b>",
                    font=dict(size=13, color=colour),
                    showarrow=False,
                )

    # Axis labels on edges
    for i, col in enumerate(cols):
        fig.update_xaxes(title_text=col, row=n, col=i + 1,
                         tickfont=dict(size=9), title_font=dict(size=10))
        fig.update_yaxes(title_text=col, row=i + 1, col=1,
                         tickfont=dict(size=9), title_font=dict(size=10))

    cell_size = 160
    dim = n * cell_size
    _apply_defaults(fig, dict(
        title=dict(text=f"<b>Pair Plot</b> — {', '.join(cols)}<br>{_subtitle('Upper: scatter | Diagonal: histogram | Lower: r value')}",
                   **_LAYOUT_DEFAULTS["title"]),
        height=dim,
        width=dim,
        margin=dict(t=75, b=40, l=80, r=20),
        showlegend=False,
    ))
    return _fig_to_dict(fig)
