"""
Data Ingestion Module
---------------------
Handles loading CSV and Excel files from file paths or Streamlit UploadedFile objects.
Returns a standardised dict with the raw DataFrame and file metadata.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_file(source: Union[str, Path, "UploadedFile"]) -> dict:
    """Load a CSV or Excel file and return a result dict.

    Parameters
    ----------
    source:
        A file path (str / Path) or a Streamlit ``UploadedFile`` object.

    Returns
    -------
    dict with keys:
        - ``df``        : raw ``pd.DataFrame``
        - ``filename``  : original file name
        - ``extension`` : lowercase extension without dot (``"csv"`` / ``"xlsx"`` / ``"xls"``)
        - ``row_count`` : number of rows
        - ``col_count`` : number of columns
        - ``size_kb``   : approximate file size in KB (None when unavailable)
    """
    if _is_uploaded_file(source):
        return _load_uploaded_file(source)
    return _load_path(Path(source))


def get_sheet_names(source: Union[str, Path, "UploadedFile"]) -> list[str]:
    """Return sheet names for Excel files; empty list for CSV.

    Parameters
    ----------
    source:
        File path or Streamlit ``UploadedFile``.
    """
    ext = _get_extension(source)
    if ext == "csv":
        return []

    if _is_uploaded_file(source):
        source.seek(0)
        data = source.read()
        source.seek(0)
        xf = pd.ExcelFile(io.BytesIO(data))
    else:
        xf = pd.ExcelFile(source)

    return xf.sheet_names


def load_excel_sheet(
    source: Union[str, Path, "UploadedFile"],
    sheet_name: str,
) -> dict:
    """Load a specific sheet from an Excel file.

    Parameters
    ----------
    source:
        File path or Streamlit ``UploadedFile``.
    sheet_name:
        Name of the sheet to load.

    Returns
    -------
    Same dict structure as :func:`load_file`.
    """
    if _is_uploaded_file(source):
        source.seek(0)
        data = source.read()
        source.seek(0)
        df = pd.read_excel(io.BytesIO(data), sheet_name=sheet_name)
        filename = source.name
        size_kb = round(len(data) / 1024, 2)
    else:
        path = Path(source)
        df = pd.read_excel(path, sheet_name=sheet_name)
        filename = path.name
        size_kb = round(path.stat().st_size / 1024, 2)

    return _build_result(df, filename, _get_extension(source), size_kb)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_uploaded_file(source) -> bool:
    """Return True if *source* looks like a Streamlit UploadedFile."""
    return hasattr(source, "read") and hasattr(source, "name")


def _get_extension(source) -> str:
    if _is_uploaded_file(source):
        name = source.name
    else:
        name = str(source)
    return Path(name).suffix.lstrip(".").lower()


def _load_path(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lstrip(".").lower()
    _validate_extension(ext, path.name)

    if ext == "csv":
        df = _read_csv(path)
    else:
        df = pd.read_excel(path)

    size_kb = round(path.stat().st_size / 1024, 2)
    return _build_result(df, path.name, ext, size_kb)


def _load_uploaded_file(source) -> dict:
    source.seek(0)
    data = source.read()
    source.seek(0)

    ext = _get_extension(source)
    _validate_extension(ext, source.name)

    if ext == "csv":
        df = _read_csv(io.BytesIO(data))
    else:
        df = pd.read_excel(io.BytesIO(data))

    size_kb = round(len(data) / 1024, 2)
    return _build_result(df, source.name, ext, size_kb)


def _read_csv(source) -> pd.DataFrame:
    """Try common encodings so mis-encoded CSVs don't blow up."""
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            if isinstance(source, (str, Path)):
                return pd.read_csv(source, encoding=enc)
            # BytesIO — need to seek back each attempt
            source.seek(0)
            return pd.read_csv(source, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV with utf-8, latin-1, or cp1252 encodings.")


def _validate_extension(ext: str, name: str) -> None:
    allowed = {"csv", "xlsx", "xls"}
    if ext not in allowed:
        raise ValueError(
            f"Unsupported file type '.{ext}' for '{name}'. "
            f"Allowed types: {', '.join(sorted(allowed))}."
        )


def _build_result(
    df: pd.DataFrame,
    filename: str,
    extension: str,
    size_kb: float | None,
) -> dict:
    return {
        "df": df,
        "filename": filename,
        "extension": extension,
        "row_count": len(df),
        "col_count": len(df.columns),
        "size_kb": size_kb,
    }
