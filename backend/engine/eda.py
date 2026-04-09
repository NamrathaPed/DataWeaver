"""
Exploratory Data Analysis (EDA) Module
---------------------------------------
Computes summary statistics, correlations, distribution shapes,
time series detection, and categorical hierarchies.

All outputs are plain dicts / JSON-serialisable so they can be
returned directly from FastAPI endpoints and consumed by the
React frontend or the insight engine.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from engine.data_cleaning import classify_columns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_eda(df: pd.DataFrame) -> dict[str, Any]:
    """Run full EDA on a cleaned DataFrame.

    Parameters
    ----------
    df:
        A cleaned DataFrame (output of ``data_cleaning.clean``).

    Returns
    -------
    dict with keys:
        - ``column_types``    : output of classify_columns()
        - ``summary``         : per-column summary statistics
        - ``correlations``    : numeric correlation matrix + strong pairs
        - ``distributions``   : skewness, kurtosis, outlier flags per numeric col
        - ``categorical``     : value counts + entropy per categorical col
        - ``time_series``     : detected time series columns and their range
        - ``dataset_overview``: row/col counts, null summary, memory usage
    """
    col_types = classify_columns(df)

    return {
        "column_types": col_types,
        "summary": _summary_statistics(df, col_types),
        "correlations": _correlations(df, col_types),
        "distributions": _distributions(df, col_types),
        "categorical": _categorical_analysis(df, col_types),
        "time_series": _time_series_analysis(df, col_types),
        "dataset_overview": _dataset_overview(df),
    }


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _summary_statistics(df: pd.DataFrame, col_types: dict) -> dict[str, Any]:
    """Per-column descriptive statistics."""
    result = {}

    for col in col_types["numeric"] + col_types["boolean"]:
        s = df[col].dropna()
        is_numeric = pd.api.types.is_numeric_dtype(s)

        if is_numeric:
            result[col] = {
                "type": "numeric",
                "count": int(s.count()),
                "null_count": int(df[col].isnull().sum()),
                "null_pct": round(df[col].isnull().mean() * 100, 2),
                "mean": _safe_float(s.mean()),
                "median": _safe_float(s.median()),
                "std": _safe_float(s.std()),
                "min": _safe_float(s.min()),
                "max": _safe_float(s.max()),
                "q25": _safe_float(s.quantile(0.25)),
                "q75": _safe_float(s.quantile(0.75)),
                "unique": int(s.nunique()),
            }
        else:
            # Boolean-like column with string values (e.g. "YES"/"NO")
            top = s.value_counts().head(5).to_dict()
            result[col] = {
                "type": "categorical",
                "count": int(s.count()),
                "null_count": int(df[col].isnull().sum()),
                "null_pct": round(df[col].isnull().mean() * 100, 2),
                "unique": int(s.nunique()),
                "top_values": {str(k): int(v) for k, v in top.items()},
                "mode": str(s.mode().iloc[0]) if not s.empty else None,
            }

    for col in col_types["categorical"]:
        s = df[col].dropna()
        top = s.value_counts().head(5).to_dict()
        result[col] = {
            "type": "categorical",
            "count": int(s.count()),
            "null_count": int(df[col].isnull().sum()),
            "null_pct": round(df[col].isnull().mean() * 100, 2),
            "unique": int(s.nunique()),
            "top_values": {str(k): int(v) for k, v in top.items()},
            "mode": str(s.mode().iloc[0]) if not s.empty else None,
        }

    for col in col_types["datetime"]:
        s = df[col].dropna()
        result[col] = {
            "type": "datetime",
            "count": int(s.count()),
            "null_count": int(df[col].isnull().sum()),
            "null_pct": round(df[col].isnull().mean() * 100, 2),
            "min": str(s.min()),
            "max": str(s.max()),
            "range_days": int((s.max() - s.min()).days) if not s.empty else None,
            "unique": int(s.nunique()),
        }

    for col in col_types["high_cardinality"]:
        s = df[col].dropna()
        result[col] = {
            "type": "high_cardinality",
            "count": int(s.count()),
            "null_count": int(df[col].isnull().sum()),
            "null_pct": round(df[col].isnull().mean() * 100, 2),
            "unique": int(s.nunique()),
            "sample": s.dropna().head(3).tolist(),
        }

    return result


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------

def _correlations(
    df: pd.DataFrame,
    col_types: dict,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Pearson correlation matrix + list of strong pairs above threshold."""
    numeric_cols = col_types["numeric"]

    if len(numeric_cols) < 2:
        return {"matrix": {}, "strong_pairs": [], "threshold": threshold}

    corr_matrix = df[numeric_cols].corr(method="pearson")

    # Flatten to list of strong pairs (upper triangle only, exclude self)
    strong_pairs = []
    cols = corr_matrix.columns.tolist()
    for i, col_a in enumerate(cols):
        for col_b in cols[i + 1:]:
            r = corr_matrix.loc[col_a, col_b]
            if pd.notna(r) and abs(r) >= threshold:
                strong_pairs.append({
                    "col_a": col_a,
                    "col_b": col_b,
                    "r": round(float(r), 4),
                    "strength": _correlation_label(r),
                    "direction": "positive" if r > 0 else "negative",
                })

    # Sort by absolute correlation descending
    strong_pairs.sort(key=lambda x: abs(x["r"]), reverse=True)

    return {
        "matrix": _df_to_nested_dict(corr_matrix.round(4)),
        "strong_pairs": strong_pairs,
        "threshold": threshold,
    }


def _correlation_label(r: float) -> str:
    abs_r = abs(r)
    if abs_r >= 0.9:
        return "very strong"
    if abs_r >= 0.7:
        return "strong"
    if abs_r >= 0.5:
        return "moderate"
    return "weak"


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------

def _distributions(df: pd.DataFrame, col_types: dict) -> dict[str, Any]:
    """Skewness, kurtosis, normality test, and outlier detection per numeric column."""
    result = {}

    for col in col_types["numeric"]:
        s = df[col].dropna()
        if len(s) < 4:
            continue

        skewness = float(s.skew())
        kurt = float(s.kurtosis())
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        outlier_mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
        outlier_count = int(outlier_mask.sum())

        # Shapiro-Wilk for small samples, skipped for large (>5000)
        normality_p = None
        is_normal = None
        if len(s) <= 5000:
            try:
                _, normality_p = stats.shapiro(s.sample(min(len(s), 500), random_state=42))
                is_normal = bool(normality_p > 0.05)
                normality_p = round(float(normality_p), 6)
            except Exception:
                pass

        result[col] = {
            "skewness": round(skewness, 4),
            "skew_label": _skew_label(skewness),
            "kurtosis": round(kurt, 4),
            "outlier_count": outlier_count,
            "outlier_pct": round(outlier_count / len(s) * 100, 2),
            "iqr": round(float(iqr), 6),
            "is_normal": is_normal,
            "normality_p": normality_p,
            # Histogram bin data (20 bins)
            "histogram": _histogram_data(s, bins=20),
        }

    return result


def _skew_label(skew: float) -> str:
    if abs(skew) < 0.5:
        return "approximately symmetric"
    if abs(skew) < 1.0:
        return "moderately skewed"
    direction = "right" if skew > 0 else "left"
    return f"highly skewed ({direction})"


def _histogram_data(s: pd.Series, bins: int = 20) -> dict:
    counts, edges = np.histogram(s.dropna(), bins=bins)
    return {
        "counts": counts.tolist(),
        "bin_edges": [round(float(e), 6) for e in edges.tolist()],
    }


# ---------------------------------------------------------------------------
# Categorical analysis
# ---------------------------------------------------------------------------

def _categorical_analysis(df: pd.DataFrame, col_types: dict) -> dict[str, Any]:
    """Value counts, entropy, and potential hierarchy detection."""
    result = {}

    for col in col_types["categorical"]:
        s = df[col].dropna()
        counts = s.value_counts()
        total = len(s)

        # Shannon entropy — higher means more evenly distributed
        probs = counts / total
        entropy = float(-np.sum(probs * np.log2(probs + 1e-10)))

        result[col] = {
            "unique_count": int(s.nunique()),
            "value_counts": {str(k): int(v) for k, v in counts.items()},
            "entropy": round(entropy, 4),
            "distribution": "uniform" if entropy > np.log2(max(s.nunique(), 1)) * 0.8 else "skewed",
        }

    # Detect potential categorical hierarchies (e.g. Country → City)
    result["_hierarchies"] = _detect_hierarchies(df, col_types["categorical"])

    return result


def _detect_hierarchies(df: pd.DataFrame, cat_cols: list[str]) -> list[dict]:
    """Detect parent→child column relationships based on conditional uniqueness."""
    hierarchies = []
    for i, parent in enumerate(cat_cols):
        for child in cat_cols[i + 1:]:
            # child is a hierarchy under parent if each parent value
            # maps to significantly fewer child values than total
            try:
                avg_child_per_parent = df.groupby(parent)[child].nunique().mean()
                total_child = df[child].nunique()
                if total_child > 1 and avg_child_per_parent < total_child * 0.5:
                    hierarchies.append({
                        "parent": parent,
                        "child": child,
                        "avg_children_per_parent": round(float(avg_child_per_parent), 2),
                    })
            except Exception:
                continue
    return hierarchies


# ---------------------------------------------------------------------------
# Time series analysis
# ---------------------------------------------------------------------------

def _time_series_analysis(df: pd.DataFrame, col_types: dict) -> dict[str, Any]:
    """Detect time series columns and compute basic temporal stats."""
    result = {}

    for col in col_types["datetime"]:
        s = df[col].dropna().sort_values()
        if len(s) < 2:
            continue

        diffs = s.diff().dropna()
        median_diff = diffs.median()

        result[col] = {
            "min": str(s.min()),
            "max": str(s.max()),
            "range_days": int((s.max() - s.min()).days),
            "record_count": int(len(s)),
            "median_interval_seconds": int(median_diff.total_seconds()),
            "inferred_frequency": _infer_frequency(median_diff),
            "is_monotonic": bool(s.is_monotonic_increasing),
            "has_gaps": _has_gaps(s, median_diff),
        }

    return result


def _infer_frequency(median_diff: pd.Timedelta) -> str:
    seconds = median_diff.total_seconds()
    if seconds < 120:
        return "minute"
    if seconds < 7200:
        return "hourly"
    if seconds < 172800:
        return "daily"
    if seconds < 864000:
        return "weekly"
    if seconds < 2678400:
        return "monthly"
    return "yearly"


def _has_gaps(s: pd.Series, median_diff: pd.Timedelta) -> bool:
    diffs = s.diff().dropna()
    return bool((diffs > median_diff * 2).any())


# ---------------------------------------------------------------------------
# Dataset overview
# ---------------------------------------------------------------------------

def _dataset_overview(df: pd.DataFrame) -> dict[str, Any]:
    """High-level dataset metadata."""
    null_counts = df.isnull().sum()
    return {
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "total_cells": int(df.size),
        "total_nulls": int(null_counts.sum()),
        "null_pct": round(null_counts.sum() / df.size * 100, 2),
        "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "columns": df.columns.tolist(),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_per_column": {col: int(v) for col, v in null_counts.items()},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any) -> float | None:
    try:
        f = float(val)
        return None if np.isnan(f) or np.isinf(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _df_to_nested_dict(df: pd.DataFrame) -> dict:
    """Convert a correlation DataFrame to a JSON-serialisable nested dict."""
    return {
        col: {
            row: (None if pd.isna(val) else round(float(val), 4))
            for row, val in df[col].items()
        }
        for col in df.columns
    }
