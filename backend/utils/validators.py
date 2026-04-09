"""
Validators
----------
Input validation for file uploads and API request payloads.
All validators raise ValueError with a clear message on failure
so FastAPI can return a clean 422 response to the client.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# File validators
# ---------------------------------------------------------------------------

def validate_upload(filename: str, file_size_bytes: int) -> None:
    """Validate a file upload by name and size.

    Parameters
    ----------
    filename:
        Original filename from the upload.
    file_size_bytes:
        File size in bytes.

    Raises
    ------
    ValueError
        If the extension is not allowed or the file exceeds the size limit.
    """
    validate_extension(filename)
    validate_file_size(file_size_bytes)


def validate_extension(filename: str) -> None:
    """Raise ValueError if the file extension is not allowed."""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '.{ext}' is not supported. "
            f"Please upload one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )


def validate_file_size(size_bytes: int) -> None:
    """Raise ValueError if the file exceeds the maximum allowed size."""
    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = round(size_bytes / (1024 * 1024), 2)
        raise ValueError(
            f"File size {size_mb} MB exceeds the {MAX_FILE_SIZE_MB} MB limit."
        )


# ---------------------------------------------------------------------------
# EDA / analysis validators
# ---------------------------------------------------------------------------

def validate_column_exists(column: str, df_columns: list[str]) -> None:
    """Raise ValueError if a column name is not present in the DataFrame."""
    if column not in df_columns:
        raise ValueError(
            f"Column '{column}' not found. "
            f"Available columns: {', '.join(df_columns)}."
        )


def validate_numeric_column(column: str, col_types: dict[str, list[str]]) -> None:
    """Raise ValueError if the column is not classified as numeric."""
    if column not in col_types.get("numeric", []):
        raise ValueError(
            f"Column '{column}' is not a numeric column. "
            f"Numeric columns: {col_types.get('numeric', [])}."
        )


def validate_chart_type(chart_type: str) -> None:
    """Raise ValueError if the chart type is not supported."""
    allowed = {"histogram", "bar", "line", "scatter", "box", "heatmap"}
    if chart_type not in allowed:
        raise ValueError(
            f"Chart type '{chart_type}' is not supported. "
            f"Choose from: {', '.join(sorted(allowed))}."
        )


def validate_cleaning_strategy(strategy: str) -> None:
    """Raise ValueError if the numeric fill strategy is not recognised."""
    allowed = {"median", "mean", "zero", "none"}
    if strategy not in allowed:
        raise ValueError(
            f"Fill strategy '{strategy}' is not valid. "
            f"Choose from: {', '.join(sorted(allowed))}."
        )


# ---------------------------------------------------------------------------
# Request payload validators
# ---------------------------------------------------------------------------

def validate_filter_payload(payload: dict[str, Any], col_types: dict) -> None:
    """Validate a dashboard filter request payload.

    Expected payload shape::

        {
            "numeric_filters": {"col": {"min": 0, "max": 100}},
            "category_filters": {"col": ["A", "B"]},
            "date_filters": {"col": {"start": "2020-01-01", "end": "2024-12-31"}}
        }

    Raises
    ------
    ValueError
        If any filter references a column that does not exist or is the
        wrong type for that filter kind.
    """
    numeric_cols = set(col_types.get("numeric", []))
    cat_cols = set(col_types.get("categorical", []))
    dt_cols = set(col_types.get("datetime", []))

    for col, bounds in payload.get("numeric_filters", {}).items():
        if col not in numeric_cols:
            raise ValueError(f"Numeric filter on non-numeric column '{col}'.")
        if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
            raise ValueError(
                f"Numeric filter for '{col}': min ({bounds['min']}) > max ({bounds['max']})."
            )

    for col in payload.get("category_filters", {}):
        if col not in cat_cols:
            raise ValueError(f"Category filter on non-categorical column '{col}'.")

    for col in payload.get("date_filters", {}):
        if col not in dt_cols:
            raise ValueError(f"Date filter on non-datetime column '{col}'.")
