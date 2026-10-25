"""
tests/test_transform.py — Unit tests for src/transform.py
==========================================================

Tests Parquet write/read round trips and type casting.
No PostgreSQL or full dataset required.
"""

from __future__ import annotations

import pandas as pd
import pytest
from pathlib import Path

from src.validation import (
    COL_INVOICE, COL_STOCKCODE, COL_DESC, COL_QUANTITY,
    COL_DATE, COL_PRICE, COL_CUSTOMER, COL_COUNTRY,
    COL_LINE_AMOUNT, COL_CANCEL,
)
from src.transform import write_parquet, read_parquet, write_rejected_csv, verify_parquet_roundtrip


def make_clean_df(n: int = 5) -> pd.DataFrame:
    """Create a validated-style DataFrame ready for Parquet write."""
    return pd.DataFrame({
        COL_INVOICE:     [f"I{i:05d}" for i in range(n)],
        COL_STOCKCODE:   [f"SC{i:04d}" for i in range(n)],
        COL_DESC:        [f"Product {i}" for i in range(n)],
        COL_QUANTITY:    [10 + i for i in range(n)],
        COL_DATE:        pd.to_datetime(["2024-01-01"] * n),
        COL_PRICE:       [2.50 + i * 0.10 for i in range(n)],
        COL_CUSTOMER:    [12345.0 + i for i in range(n)],
        COL_COUNTRY:     ["United Kingdom"] * n,
        COL_LINE_AMOUNT: [(2.50 + i * 0.10) * (10 + i) for i in range(n)],
        COL_CANCEL:      [False] * n,
    })


class TestWriteReadParquet:
    def test_write_and_read_roundtrip(self, tmp_path: Path):
        df = make_clean_df(10)
        out = tmp_path / "test.parquet"
        write_parquet(df, out)
        df_read = read_parquet(out)
        assert len(df_read) == 10
        assert COL_INVOICE in df_read.columns

    def test_write_creates_file(self, tmp_path: Path):
        df = make_clean_df(3)
        out = tmp_path / "sub" / "test.parquet"
        write_parquet(df, out)
        assert out.exists()

    def test_overwrite_is_idempotent(self, tmp_path: Path):
        df = make_clean_df(5)
        out = tmp_path / "idempotent.parquet"
        write_parquet(df, out)
        write_parquet(df, out)  # second write should overwrite, not append
        df_read = read_parquet(out)
        assert len(df_read) == 5  # not 10

    def test_all_expected_columns_preserved(self, tmp_path: Path):
        df = make_clean_df(3)
        out = tmp_path / "cols.parquet"
        write_parquet(df, out)
        df_read = read_parquet(out)
        expected_cols = {COL_INVOICE, COL_STOCKCODE, COL_QUANTITY, COL_PRICE, COL_DATE}
        assert expected_cols.issubset(set(df_read.columns))

    def test_file_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_parquet(tmp_path / "nonexistent.parquet")

    def test_verify_roundtrip_pass(self, tmp_path: Path):
        df = make_clean_df(5)
        out = tmp_path / "verify.parquet"
        write_parquet(df, out)
        assert verify_parquet_roundtrip(df, out) is True

    def test_verify_roundtrip_row_mismatch(self, tmp_path: Path):
        df = make_clean_df(5)
        out = tmp_path / "verify_mismatch.parquet"
        write_parquet(df, out)
        df_small = make_clean_df(3)  # different row count
        assert verify_parquet_roundtrip(df_small, out) is False


class TestWriteRejectedCsv:
    def test_write_rejected_csv(self, tmp_path: Path):
        from src.validation import COL_REJECT_REASON
        df = pd.DataFrame({
            COL_INVOICE: [None],
            COL_REJECT_REASON: ["null_invoice; "],
        })
        out = tmp_path / "rejected.csv"
        write_rejected_csv(df, out)
        assert out.exists()
        df_read = pd.read_csv(out)
        assert len(df_read) == 1

    def test_empty_rejected_csv_written_with_headers(self, tmp_path: Path):
        from src.validation import COL_REJECT_REASON
        df = pd.DataFrame()
        out = tmp_path / "empty_rejected.csv"
        write_rejected_csv(df, out)
        assert out.exists()
        # File should exist with at least a header
        content = out.read_text(encoding="utf-8-sig")
        assert len(content) > 0

    def test_creates_parent_directories(self, tmp_path: Path):
        from src.validation import COL_REJECT_REASON
        df = pd.DataFrame({COL_REJECT_REASON: ["test"]})
        out = tmp_path / "deep" / "nested" / "rejected.csv"
        write_rejected_csv(df, out)
        assert out.exists()
