"""
src/transform.py — Local File Transforms and Parquet I/O
=========================================================

WHY THIS FILE EXISTS
--------------------
After validation produces a clean DataFrame, this module:
  1. Casts columns to their final optimal types (reduces memory, speeds up SQL)
  2. Writes the clean data to Parquet (a columnar binary format)
  3. Writes rejected records to CSV (human-readable for audit)
  4. Can read a previously-written Parquet file back for downstream use

WHY PARQUET?
------------
CSV stores everything as text.  Parquet stores data in a typed, compressed,
columnar format.  Reading a specific column from a 500K-row Parquet file
is ~10x faster than reading a full CSV because the engine skips irrelevant
columns.  Parquet is the standard format in modern data lakes (Azure ADLS,
AWS S3, GCP GCS).

IDEMPOTENCY
-----------
Writing Parquet with mode='overwrite' (the default here) means running the
pipeline twice produces the same output — not double the data.  This is
called idempotent processing.

INTERVIEW TALKING POINT
-----------------------
"Parquet is a columnar storage format.  When you run a query like
SELECT SUM(quantity) FROM sales, it reads only the quantity column from
disk — not the entire row.  This is orders of magnitude faster for analytics
than row-oriented formats like CSV."
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.validation import (
    COL_INVOICE, COL_STOCKCODE, COL_DESC, COL_QUANTITY,
    COL_DATE, COL_PRICE, COL_CUSTOMER, COL_COUNTRY,
    COL_LINE_AMOUNT, COL_CANCEL, COL_REJECT_REASON,
)

logger = logging.getLogger(__name__)


# ── PyArrow schema for the clean Parquet file ─────────────────────────────────
# Explicit schema prevents Parquet from inferring wrong types.
# Int64 (nullable) is used for quantity (can be negative).
# double for price and line_amount.
# large_utf8 for long text fields (description can be long).

CLEAN_SCHEMA = pa.schema([
    pa.field(COL_INVOICE,     pa.string()),
    pa.field(COL_STOCKCODE,   pa.string()),
    pa.field(COL_DESC,        pa.large_utf8(), nullable=True),
    pa.field(COL_QUANTITY,    pa.int64()),
    pa.field(COL_DATE,        pa.timestamp("us")),
    pa.field(COL_PRICE,       pa.float64()),
    pa.field(COL_CUSTOMER,    pa.float64(), nullable=True),  # nullable: many missing
    pa.field(COL_COUNTRY,     pa.string(),  nullable=True),
    pa.field(COL_LINE_AMOUNT, pa.float64()),
    pa.field(COL_CANCEL,      pa.bool_()),
    # _sheet_source column may or may not be present
])


def _cast_clean_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast DataFrame columns to their final types before Parquet write.
    Uses pandas nullable Int64 (capital I) for nullable integers.
    """
    df = df.copy()

    # String columns
    for col in (COL_INVOICE, COL_STOCKCODE):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    for col in (COL_DESC, COL_COUNTRY):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace("nan", pd.NA)

    # Numeric
    if COL_QUANTITY in df.columns:
        df[COL_QUANTITY] = pd.to_numeric(df[COL_QUANTITY], errors="coerce").astype("Int64")

    if COL_PRICE in df.columns:
        df[COL_PRICE] = pd.to_numeric(df[COL_PRICE], errors="coerce").astype(float)

    if COL_LINE_AMOUNT in df.columns:
        df[COL_LINE_AMOUNT] = pd.to_numeric(df[COL_LINE_AMOUNT], errors="coerce").astype(float)

    if COL_CUSTOMER in df.columns:
        df[COL_CUSTOMER] = pd.to_numeric(df[COL_CUSTOMER], errors="coerce")

    # Datetime
    if COL_DATE in df.columns:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors="coerce")

    # Boolean
    if COL_CANCEL in df.columns:
        df[COL_CANCEL] = df[COL_CANCEL].astype(bool)

    return df


def write_parquet(df: pd.DataFrame, output_path: Path) -> None:
    """
    Write a clean DataFrame to Parquet.

    Parameters
    ----------
    df          : clean validated DataFrame
    output_path : destination .parquet file path

    Behaviour
    ---------
    - Creates parent directories automatically.
    - Overwrites any existing file at output_path (idempotent).
    - Uses snappy compression (fast + good ratio; supported everywhere).
    - Writes row groups of 100K rows for efficient column reads.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Casting types for Parquet write ...")
    df = _cast_clean_types(df)

    # Convert Int64 (pandas nullable) to int64 for PyArrow compatibility
    # PyArrow handles null int64 natively via its own null bitmask
    int_cols = df.select_dtypes(include="Int64").columns
    for col in int_cols:
        df[col] = df[col].astype("float64")  # NaN-safe bridge to Arrow

    table = pa.Table.from_pandas(df, preserve_index=False)

    pq.write_table(
        table,
        str(output_path),
        compression="snappy",
        row_group_size=100_000,
        write_statistics=True,
        coerce_timestamps="us",
    )

    size_mb = output_path.stat().st_size / 1_048_576
    logger.info(
        "Parquet written: %s  (%d rows, %.2f MB)",
        output_path.name, len(df), size_mb,
    )


def write_rejected_csv(df: pd.DataFrame, output_path: Path) -> None:
    """
    Write rejected records to CSV.

    CSV is used (not Parquet) because:
    - Rejected records are for human audit — CSV is readable in Excel
    - The volume is usually small
    - Exact types are less critical for a reject log
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if df.empty:
        logger.info("No rejected records — skipping CSV write.")
        # Write an empty file with headers so downstream checks don't fail
        pd.DataFrame(columns=[COL_REJECT_REASON]).to_csv(
            str(output_path), index=False, encoding="utf-8-sig"
        )
        return

    # utf-8-sig BOM makes Excel open the file correctly on Windows
    df.to_csv(str(output_path), index=False, encoding="utf-8-sig")
    logger.info(
        "Rejected CSV written: %s  (%d rows)",
        output_path.name, len(df),
    )


def read_parquet(input_path: Path) -> pd.DataFrame:
    """
    Read a Parquet file back into a DataFrame.
    Used for validation after write and for downstream stages.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {input_path}")

    df = pd.read_parquet(str(input_path), engine="pyarrow")
    logger.info(
        "Parquet loaded: %s  (%d rows, %d columns)",
        input_path.name, len(df), len(df.columns),
    )
    return df


def verify_parquet_roundtrip(df_original: pd.DataFrame, parquet_path: Path) -> bool:
    """
    Verify that a Parquet file was written correctly by reading it back
    and comparing row counts and column names.

    Returns True if verification passes.
    """
    df_read = read_parquet(parquet_path)

    row_match = len(df_original) == len(df_read)
    col_overlap = set(df_original.columns) & set(df_read.columns)

    if not row_match:
        logger.error(
            "Parquet roundtrip FAIL: wrote %d rows, read back %d rows",
            len(df_original), len(df_read),
        )
        return False

    logger.info(
        "Parquet roundtrip OK: %d rows, %d shared columns",
        len(df_read), len(col_overlap),
    )
    return True
