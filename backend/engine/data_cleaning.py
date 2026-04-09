"""
Data Cleaning Module
--------------------
Handles deduplication, missing value imputation, data type detection,
and column classification. Returns a cleaned DataFrame and a cleaning report
so the frontend can show users exactly what changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CleaningReport:
    """Summary of every transformation applied during cleaning."""

    original_shape: tuple[int, int]
    final_shape: tuple[int, int]
    duplicates_removed: int
    columns_filled: dict[str, dict[str, Any]] = field(default_factory=dict)
    columns_type_cast: dict[str, str] = field(default_factory=dict)
    columns_dropped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict:
        return {
            "original_shape": {"rows": self.original_shape[0], "cols": self.original_shape[1]},
            "final_shape": {"rows": self.final_shape[0], "cols": self.final_shape[1]},
            "duplicates_removed": self.duplicates_removed,
            "columns_filled": self.columns_filled,
            "columns_type_cast": self.columns_type_cast,
            "columns_dropped": self.columns_dropped,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean(
    df: pd.DataFrame,
    *,
    drop_duplicate_rows: bool = True,
    numeric_fill_strategy: str = "median",   # "median" | "mean" | "zero" | "none"
    categorical_fill_value: str = "Unknown",
    drop_high_null_cols: bool = True,
    null_col_threshold: float = 0.9,         # drop col if >90 % null
    parse_dates: bool = True,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean a DataFrame and return (cleaned_df, CleaningReport).

    Parameters
    ----------
    df:
        Raw DataFrame from the ingestion module.
    drop_duplicate_rows:
        Remove fully duplicate rows.
    numeric_fill_strategy:
        How to impute missing numeric values.
        ``"median"`` (default) is robust to outliers.
        ``"mean"`` is appropriate for normally distributed data.
        ``"zero"`` fills with 0.
        ``"none"`` leaves NaNs as-is.
    categorical_fill_value:
        String used to fill missing values in categorical/object columns.
    drop_high_null_cols:
        Drop columns where the fraction of nulls exceeds *null_col_threshold*.
    null_col_threshold:
        Fraction of nulls above which a column is dropped (default 0.9).
    parse_dates:
        Attempt to detect and convert date-like object columns to datetime.

    Returns
    -------
    (cleaned DataFrame, CleaningReport)
    """
    df = df.copy()
    report = CleaningReport(
        original_shape=df.shape,
        final_shape=df.shape,  # updated at the end
        duplicates_removed=0,
    )

    df = _strip_whitespace(df)
    df = _drop_high_null_columns(df, drop_high_null_cols, null_col_threshold, report)
    df = _remove_duplicates(df, drop_duplicate_rows, report)
    df = _cast_types(df, parse_dates, report)
    df = _fill_missing(df, numeric_fill_strategy, categorical_fill_value, report)

    report.final_shape = df.shape
    return df, report


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def _strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading/trailing whitespace from string columns and column names."""
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df


def _drop_high_null_columns(
    df: pd.DataFrame,
    enabled: bool,
    threshold: float,
    report: CleaningReport,
) -> pd.DataFrame:
    """Drop columns where null fraction exceeds threshold."""
    if not enabled:
        return df

    null_fractions = df.isnull().mean()
    to_drop = null_fractions[null_fractions > threshold].index.tolist()

    if to_drop:
        df = df.drop(columns=to_drop)
        report.columns_dropped.extend(to_drop)
        report.warnings.append(
            f"Dropped {len(to_drop)} column(s) with >{int(threshold * 100)}% missing values: "
            + ", ".join(to_drop)
        )

    return df


def _remove_duplicates(
    df: pd.DataFrame,
    enabled: bool,
    report: CleaningReport,
) -> pd.DataFrame:
    """Remove fully duplicate rows."""
    if not enabled:
        report.duplicates_removed = 0
        return df

    before = len(df)
    df = df.drop_duplicates()
    report.duplicates_removed = before - len(df)
    return df


def _cast_types(
    df: pd.DataFrame,
    parse_dates: bool,
    report: CleaningReport,
) -> pd.DataFrame:
    """Detect and cast column types: numeric strings → numeric, date strings → datetime."""
    for col in df.columns:
        original_dtype = str(df[col].dtype)

        # --- Try numeric coercion on object columns -----------------------
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            non_null_original = df[col].notna().sum()
            non_null_converted = converted.notna().sum()

            # Accept conversion if we don't lose more than 5% of non-null values
            if non_null_original > 0:
                loss = (non_null_original - non_null_converted) / non_null_original
                if loss <= 0.05:
                    df[col] = converted
                    report.columns_type_cast[col] = f"{original_dtype} → numeric"
                    continue  # skip date check for this column

        # --- Try datetime coercion on object columns ----------------------
        if parse_dates and df[col].dtype == object:
            converted = pd.to_datetime(df[col], errors="coerce")
            non_null_original = df[col].notna().sum()
            non_null_converted = converted.notna().sum()

            if non_null_original > 0:
                loss = (non_null_original - non_null_converted) / non_null_original
                if loss <= 0.05:
                    df[col] = converted
                    report.columns_type_cast[col] = f"{original_dtype} → datetime"

    return df


def _fill_missing(
    df: pd.DataFrame,
    numeric_strategy: str,
    categorical_fill: str,
    report: CleaningReport,
) -> pd.DataFrame:
    """Impute missing values column by column."""
    for col in df.columns:
        n_missing = df[col].isnull().sum()
        if n_missing == 0:
            continue

        # Numeric columns
        if pd.api.types.is_numeric_dtype(df[col]):
            if numeric_strategy == "median":
                fill_val = df[col].median()
            elif numeric_strategy == "mean":
                fill_val = df[col].mean()
            elif numeric_strategy == "zero":
                fill_val = 0
            else:  # "none"
                continue

            df[col] = df[col].fillna(fill_val)
            report.columns_filled[col] = {
                "strategy": numeric_strategy,
                "fill_value": round(float(fill_val), 6) if not np.isnan(float(fill_val)) else None,
                "rows_filled": int(n_missing),
            }

        # Datetime columns — forward fill, then backward fill
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].ffill().bfill()
            report.columns_filled[col] = {
                "strategy": "ffill+bfill",
                "fill_value": None,
                "rows_filled": int(n_missing),
            }

        # Categorical / object columns
        else:
            df[col] = df[col].fillna(categorical_fill)
            report.columns_filled[col] = {
                "strategy": "constant",
                "fill_value": categorical_fill,
                "rows_filled": int(n_missing),
            }

    return df


# ---------------------------------------------------------------------------
# Column type classifier (used by EDA + chart engine)
# ---------------------------------------------------------------------------

def classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Classify DataFrame columns by semantic type.

    Returns
    -------
    dict with keys:
        - ``numeric``         : continuous numeric columns
        - ``categorical``     : low-cardinality string columns
        - ``ordinal``         : categorical columns with a natural order (e.g. Low/Med/High)
        - ``datetime``        : datetime columns
        - ``boolean``         : binary columns (exactly 2 unique values)
        - ``id``              : identifier columns — high uniqueness, useless for analysis
        - ``geospatial``      : lat/lon column pairs
        - ``currency``        : numeric columns that appear to represent monetary values
        - ``percentage``      : numeric columns whose values fall in [0, 1] or [0, 100]
        - ``high_cardinality``: free-text string columns (not useful for grouping)
    """
    numeric, categorical, ordinal, datetime_cols = [], [], [], []
    high_card, boolean, id_cols, currency, percentage = [], [], [], [], []

    # Known ordinal value sets (order matters)
    _ORDINAL_SETS = [
        {"low", "medium", "high"},
        {"low", "med", "high"},
        {"small", "medium", "large"},
        {"none", "minor", "moderate", "severe"},
        {"never", "rarely", "sometimes", "often", "always"},
        {"very low", "low", "medium", "high", "very high"},
        {"poor", "fair", "good", "very good", "excellent"},
        {"1", "2", "3", "4", "5"},
        {"disagree", "neutral", "agree"},
        {"strongly disagree", "disagree", "neutral", "agree", "strongly agree"},
    ]

    # ID-like name patterns
    _ID_PATTERNS = {
        "id", "uuid", "guid", "key", "code", "ref", "reference",
        "number", "num", "no", "nr", "hash", "token", "serial",
    }

    # Currency name patterns
    _CURRENCY_PATTERNS = {
        "price", "cost", "revenue", "sales", "amount", "total",
        "fee", "salary", "wage", "income", "spend", "budget",
        "payment", "charge", "profit", "loss", "margin",
    }

    n_rows = max(len(df), 1)

    # Detect geospatial pairs first
    geo_cols = _detect_geo_pairs(df)

    for col in df.columns:
        series = df[col]
        n_unique = series.nunique()
        col_lower = col.lower().replace(" ", "_").replace("-", "_")

        # Already classified as geo
        if col in geo_cols:
            continue

        # Datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime_cols.append(col)

        # Bool dtype
        elif pd.api.types.is_bool_dtype(series):
            boolean.append(col)

        # Numeric types
        elif pd.api.types.is_numeric_dtype(series):
            if n_unique == 2:
                boolean.append(col)
                continue

            # ID detection: nearly all unique integers with an ID-like name
            is_id_name = any(p in col_lower for p in _ID_PATTERNS)
            if is_id_name and n_unique / n_rows > 0.9:
                id_cols.append(col)
                continue

            # Currency detection
            if any(p in col_lower for p in _CURRENCY_PATTERNS):
                currency.append(col)
                continue

            # Percentage detection: values between 0–1 or 0–100 with "pct/rate/ratio/%" in name
            s_clean = series.dropna()
            is_pct_name = any(p in col_lower for p in {"pct", "percent", "rate", "ratio", "score", "share"})
            if is_pct_name or (s_clean.between(0, 1).all() and s_clean.std() < 0.5):
                percentage.append(col)
                continue

            numeric.append(col)

        # String / object types
        elif pd.api.types.is_object_dtype(series):
            if n_unique == 2:
                boolean.append(col)
                continue

            # ID detection: nearly all unique strings with ID-like name
            is_id_name = any(p in col_lower for p in _ID_PATTERNS)
            if is_id_name and n_unique / n_rows > 0.9:
                id_cols.append(col)
                continue

            # PII / skip patterns: email, url, phone
            sample = series.dropna().astype(str).head(50)
            if _looks_like_email(sample) or _looks_like_url(sample):
                id_cols.append(col)  # treat as identifier — skip analysis
                continue

            # Ordinal detection
            unique_lower = set(series.dropna().str.lower().str.strip().unique())
            if any(unique_lower == s or unique_lower.issubset(s) for s in _ORDINAL_SETS):
                ordinal.append(col)
                continue

            # Categorical vs high cardinality
            cat_threshold = min(50, max(10, int(n_rows * 0.05)))
            if n_unique <= cat_threshold:
                categorical.append(col)
            else:
                high_card.append(col)

    return {
        "numeric": numeric,
        "categorical": categorical,
        "ordinal": ordinal,
        "datetime": datetime_cols,
        "boolean": boolean,
        "id": id_cols,
        "geospatial": geo_cols,
        "currency": currency,
        "percentage": percentage,
        "high_cardinality": high_card,
    }


def _detect_geo_pairs(df: pd.DataFrame) -> list[str]:
    """Detect latitude / longitude column pairs.

    Returns a flat list of geo column names if a valid lat/lon pair is found.
    """
    lat_patterns = {"lat", "latitude", "y", "lat_deg"}
    lon_patterns = {"lon", "lng", "longitude", "x", "lon_deg", "long"}

    lat_col = lon_col = None
    for col in df.columns:
        cl = col.lower().replace(" ", "_")
        if pd.api.types.is_numeric_dtype(df[col]):
            if any(p == cl or cl.endswith(p) for p in lat_patterns):
                s = df[col].dropna()
                if s.between(-90, 90).mean() > 0.95:
                    lat_col = col
            elif any(p == cl or cl.endswith(p) for p in lon_patterns):
                s = df[col].dropna()
                if s.between(-180, 180).mean() > 0.95:
                    lon_col = col

    if lat_col and lon_col:
        return [lat_col, lon_col]
    return []


def _looks_like_email(sample: pd.Series) -> bool:
    return sample.str.contains(r"^[\w.+-]+@[\w-]+\.[a-z]{2,}$", regex=True, na=False).mean() > 0.5


def _looks_like_url(sample: pd.Series) -> bool:
    return sample.str.contains(r"^https?://", regex=True, na=False).mean() > 0.5
