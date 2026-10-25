"""
src/etl.py — Extract and Transform (Extract Layer)
===================================================

WHY THIS FILE EXISTS
--------------------
The Extract phase reads the raw Kaggle Excel workbook and returns a
normalised pandas DataFrame.  Keeping this separate from validation and
loading means we can:
  - Swap the source format (e.g., CSV, API) without touching other modules
  - Unit-test extraction logic with small synthetic inputs
  - Rerun extraction cheaply without touching the database

WHAT THIS FILE DOES
-------------------
1. Locate the source Excel file
2. Inspect workbook sheets — do not silently pick an arbitrary sheet
3. Combine multiple sheets if they share the same schema
4. Normalise column headers
5. Record audit metadata (source file, sheet names, row counts, time)
6. Return a DataFrame ready for validation

INTERVIEW TALKING POINT
-----------------------
"The extract phase is deliberately thin — it only reads data and normalises
column names.  Business rules live in validation.py, so the two concerns
don't bleed into each other.  This makes testing much easier."
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pandas as pd

from src.validation import normalize_headers, ALL_EXPECTED_COLUMNS

logger = logging.getLogger(__name__)


# ── Extraction result dataclass ───────────────────────────────────────────────

@dataclass
class ExtractResult:
    """Metadata and data returned by extract()."""
    df: pd.DataFrame                 = field(default_factory=pd.DataFrame)
    source_file: str                 = ""
    sheets_found: List[str]          = field(default_factory=list)
    sheets_loaded: List[str]         = field(default_factory=list)
    source_row_count: int            = 0
    elapsed_seconds: float           = 0.0
    warnings: List[str]              = field(default_factory=list)


# ── Helper: inspect workbook ──────────────────────────────────────────────────

def inspect_workbook(path: Path) -> List[str]:
    """
    Return the list of sheet names in the workbook without reading data.
    Uses openpyxl directly for speed.
    """
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    sheet_names = wb.sheetnames
    wb.close()
    logger.info("Workbook sheets found: %s", sheet_names)
    return sheet_names


def _read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """
    Read one Excel sheet and return a raw DataFrame.
    Pandas reads all values; dtype=object avoids premature type coercion.
    """
    logger.info("Reading sheet: %r from %s ...", sheet_name, path.name)
    df = pd.read_excel(
        str(path),
        sheet_name=sheet_name,
        dtype=object,         # preserve everything as string/object for now
        engine="openpyxl",
    )
    logger.info("  → %d rows, %d columns", len(df), len(df.columns))
    return df


def _sheets_are_compatible(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """
    Return True if two sheets share all required source header names after
    normalisation.  Used to decide whether to combine sheets.
    """
    cols1 = set(normalize_headers(df1).columns)
    cols2 = set(normalize_headers(df2).columns)
    required_norm = set(ALL_EXPECTED_COLUMNS)
    return bool(required_norm & cols1) and bool(required_norm & cols2)


# ── Main extract function ──────────────────────────────────────────────────────

def extract(source_path: Path) -> ExtractResult:
    """
    Read the Kaggle Online Retail II Excel workbook.

    Strategy
    --------
    - If the workbook has one sheet, read it.
    - If it has multiple sheets, normalise each, check schema compatibility,
      and concatenate compatible sheets.
    - Sheets named 'Year 2009-2010' and 'Year 2010-2011' (the actual Kaggle
      sheet names) are both loaded and combined.

    Parameters
    ----------
    source_path : absolute or relative Path to the .xlsx file

    Returns
    -------
    ExtractResult

    Raises
    ------
    FileNotFoundError : source file does not exist
    ValueError        : workbook is completely unreadable or has no usable data
    """
    result = ExtractResult()
    t_start = time.perf_counter()

    # ── 1. File existence check ───────────────────────────────────────────────
    if not source_path.exists():
        raise FileNotFoundError(
            f"Source file not found: {source_path}\n"
            f"  → Download 'Online Retail II' from Kaggle and place it at "
            f"data/raw/online_retail_II.xlsx"
        )

    result.source_file = str(source_path)
    logger.info("=" * 60)
    logger.info("EXTRACT PHASE")
    logger.info("Source: %s  (%.1f MB)", source_path.name, source_path.stat().st_size / 1_048_576)

    # ── 2. Inspect sheets ─────────────────────────────────────────────────────
    try:
        sheet_names = inspect_workbook(source_path)
    except Exception as exc:
        raise ValueError(f"Cannot read workbook {source_path.name}: {exc}") from exc

    result.sheets_found = sheet_names

    # ── 3. Load sheets ────────────────────────────────────────────────────────
    raw_frames: list[pd.DataFrame] = []

    for sheet in sheet_names:
        try:
            df_raw = _read_sheet(source_path, sheet)
            if df_raw.empty:
                result.warnings.append(f"Sheet '{sheet}' is empty — skipped")
                logger.warning("Sheet '%s' is empty — skipped", sheet)
                continue
            df_norm = normalize_headers(df_raw)
            raw_frames.append(df_norm)
            result.sheets_loaded.append(sheet)
        except Exception as exc:
            msg = f"Could not read sheet '{sheet}': {exc}"
            result.warnings.append(msg)
            logger.warning(msg)

    if not raw_frames:
        raise ValueError(
            f"No readable sheets found in {source_path.name}. "
            f"Sheets found: {sheet_names}"
        )

    # ── 4. Combine sheets ─────────────────────────────────────────────────────
    if len(raw_frames) == 1:
        combined = raw_frames[0]
    else:
        logger.info(
            "Combining %d sheets: %s", len(raw_frames), result.sheets_loaded
        )
        # Add sheet_source column before combining for traceability
        tagged: list[pd.DataFrame] = []
        for sheet_name, df in zip(result.sheets_loaded, raw_frames):
            df = df.copy()
            df["_sheet_source"] = sheet_name
            tagged.append(df)
        combined = pd.concat(tagged, ignore_index=True, sort=False)
        logger.info("Combined DataFrame: %d rows", len(combined))

    result.df = combined
    result.source_row_count = len(combined)
    result.elapsed_seconds = time.perf_counter() - t_start

    logger.info(
        "Extract complete | sheets_loaded=%s | rows=%d | elapsed=%.1fs",
        result.sheets_loaded, result.source_row_count, result.elapsed_seconds,
    )
    logger.info("Columns in extracted data: %s", list(combined.columns))
    logger.info("=" * 60)

    return result


# ── Quick sample helper (for tests and debugging) ─────────────────────────────

def extract_sample(source_path: Path, n_rows: int = 1000) -> pd.DataFrame:
    """
    Read a small sample from the first available sheet.
    Useful for schema inspection without loading the full 500K-row file.
    """
    sheet_names = inspect_workbook(source_path)
    if not sheet_names:
        raise ValueError("No sheets found")

    first_sheet = sheet_names[0]
    logger.info("Reading %d-row sample from sheet %r", n_rows, first_sheet)

    df = pd.read_excel(
        str(source_path),
        sheet_name=first_sheet,
        dtype=object,
        engine="openpyxl",
        nrows=n_rows,
    )
    return normalize_headers(df)
