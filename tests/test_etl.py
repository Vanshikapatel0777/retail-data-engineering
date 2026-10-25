"""
tests/test_etl.py — Unit tests for src/etl.py
==============================================

Tests extraction logic with synthetic Excel files.
No full Kaggle dataset required.

Integration tests (marked @pytest.mark.slow) require the real dataset.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from src.validation import (
    COL_INVOICE, COL_STOCKCODE, COL_QUANTITY, COL_DATE, COL_PRICE,
    normalize_headers,
)


class TestNormalizeHeadersFromEtl:
    """normalize_headers is imported from validation but used by etl."""

    def test_columns_after_normalize_are_lowercase(self):
        df = pd.DataFrame({"Invoice": [1], "StockCode": [2], "Quantity": [3],
                           "InvoiceDate": ["2024-01-01"], "Price": [1.0]})
        result = normalize_headers(df)
        for col in result.columns:
            assert col == col.lower() or col.startswith("_")

    def test_invoiceno_to_invoice(self):
        df = pd.DataFrame({"InvoiceNo": ["A1"], "UnitPrice": [1.0]})
        result = normalize_headers(df)
        assert COL_INVOICE in result.columns
        assert COL_PRICE in result.columns


class TestExtractResult:
    """Test the ExtractResult dataclass."""

    def test_extract_result_defaults(self):
        from src.etl import ExtractResult
        r = ExtractResult()
        assert r.source_row_count == 0
        assert r.sheets_found == []
        assert r.sheets_loaded == []
        assert r.warnings == []

    def test_extract_result_with_df(self):
        from src.etl import ExtractResult
        df = pd.DataFrame({"a": [1, 2, 3]})
        r = ExtractResult(df=df, source_row_count=3)
        assert r.source_row_count == 3


class TestExtractMissingFile:
    """extract() must raise FileNotFoundError for missing source."""

    def test_missing_file_raises(self, tmp_path: Path):
        from src.etl import extract
        fake_path = tmp_path / "does_not_exist.xlsx"
        with pytest.raises(FileNotFoundError, match="not found"):
            extract(fake_path)


class TestSheetsCompatible:
    """_sheets_are_compatible detects schemas that can be combined."""

    def test_compatible_same_schema(self):
        from src.etl import _sheets_are_compatible
        df1 = pd.DataFrame({COL_INVOICE: [1], COL_STOCKCODE: [2],
                             COL_QUANTITY: [3], COL_DATE: ["x"], COL_PRICE: [1.0]})
        df2 = df1.copy()
        assert _sheets_are_compatible(df1, df2)

    def test_incompatible_different_schema(self):
        from src.etl import _sheets_are_compatible
        df1 = pd.DataFrame({COL_INVOICE: [1], COL_STOCKCODE: [2]})
        df2 = pd.DataFrame({"unrelated_col": [1]})
        # df2 has no required columns — at least one required col missing
        result = _sheets_are_compatible(df1, df2)
        # df2 doesn't have any required columns so intersection is empty
        assert not result


@pytest.mark.slow
class TestExtractIntegration:
    """Integration tests that require the actual Kaggle dataset.
    Run with: pytest -m slow
    Skipped unless the dataset file exists.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_dataset(self):
        from src.config import pipeline_config
        if not pipeline_config.raw_file.exists():
            pytest.skip(
                f"Dataset not found at {pipeline_config.raw_file}. "
                "Download from Kaggle to run these tests."
            )

    def test_extract_returns_rows(self):
        from src.etl import extract
        from src.config import pipeline_config
        result = extract(pipeline_config.raw_file)
        assert result.source_row_count > 0

    def test_extract_has_required_columns(self):
        from src.etl import extract
        from src.config import pipeline_config
        from src.validation import REQUIRED_COLUMNS
        result = extract(pipeline_config.raw_file)
        for col in REQUIRED_COLUMNS:
            assert col in result.df.columns, f"Missing required column: {col}"

    def test_extract_sheets_loaded(self):
        from src.etl import extract
        from src.config import pipeline_config
        result = extract(pipeline_config.raw_file)
        assert len(result.sheets_loaded) >= 1

    def test_extract_sample_has_rows(self):
        from src.etl import extract_sample
        from src.config import pipeline_config
        df = extract_sample(pipeline_config.raw_file, n_rows=100)
        assert len(df) == 100
