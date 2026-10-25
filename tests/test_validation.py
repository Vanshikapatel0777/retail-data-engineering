"""
tests/test_validation.py — Unit tests for src/validation.py
============================================================

WHY UNIT TESTS?
---------------
Unit tests use small synthetic DataFrames — they don't need the 500K-row
Kaggle dataset or a live PostgreSQL server.  This means:
  - Tests run in under 1 second
  - Any developer can run them without special setup
  - CI/CD pipelines don't need data access

WHAT IS TESTED
--------------
- normalize_headers: various input capitalizations
- check_schema: required column detection
- flag_missing_required: invoice, stockcode, quantity, price, date
- flag_non_numeric: quantity and price coercion
- flag_invalid_dates: date coercion
- flag_negative_price: price < 0 detection
- flag_duplicates: composite key duplicate detection
- add_cancellation_flag: C-prefix detection
- add_line_amount: quantity × price calculation
- validate_dataframe: integration of all checks
- Reconciliation invariant: input = clean + rejected
- Empty DataFrame handling
- Returns (negative quantity): kept, not rejected
- Cancelled invoices: kept with is_cancellation=True
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.validation import (
    ALL_EXPECTED_COLUMNS,
    COL_CANCEL,
    COL_COUNTRY,
    COL_CUSTOMER,
    COL_DATE,
    COL_DESC,
    COL_INVOICE,
    COL_LINE_AMOUNT,
    COL_PRICE,
    COL_QUANTITY,
    COL_REJECT_REASON,
    COL_STOCKCODE,
    REQUIRED_COLUMNS,
    add_cancellation_flag,
    add_line_amount,
    check_schema,
    flag_duplicates,
    flag_invalid_dates,
    flag_missing_required,
    flag_negative_price,
    flag_non_numeric,
    normalize_headers,
    validate_dataframe,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_clean_df(n: int = 5) -> pd.DataFrame:
    """Create a minimal valid DataFrame with n rows."""
    return pd.DataFrame({
        COL_INVOICE:   [f"I{i:05d}" for i in range(n)],
        COL_STOCKCODE: [f"SC{i:04d}" for i in range(n)],
        COL_DESC:      [f"Product {i}" for i in range(n)],
        COL_QUANTITY:  [10 + i for i in range(n)],
        COL_DATE:      ["2024-01-01"] * n,
        COL_PRICE:     [2.50 + i * 0.10 for i in range(n)],
        COL_CUSTOMER:  [12345.0 + i for i in range(n)],
        COL_COUNTRY:   ["United Kingdom"] * n,
    })


# ── normalize_headers ─────────────────────────────────────────────────────────

class TestNormalizeHeaders:
    def test_lowercase_columns(self):
        df = pd.DataFrame({"Invoice": [1], "StockCode": [2], "Quantity": [3],
                           "InvoiceDate": [4], "Price": [5]})
        result = normalize_headers(df)
        assert "invoice" in result.columns
        assert "stockcode" in result.columns

    def test_invoiceno_mapped_to_invoice(self):
        df = pd.DataFrame({"InvoiceNo": ["A1"], "Quantity": [1]})
        result = normalize_headers(df)
        assert "invoice" in result.columns

    def test_unitprice_mapped_to_price(self):
        df = pd.DataFrame({"UnitPrice": [1.5]})
        result = normalize_headers(df)
        assert "price" in result.columns

    def test_customer_id_with_space(self):
        df = pd.DataFrame({"Customer ID": [123.0]})
        result = normalize_headers(df)
        assert "customerid" in result.columns

    def test_strip_leading_trailing_spaces(self):
        df = pd.DataFrame({"  Invoice  ": [1], " StockCode ": [2]})
        result = normalize_headers(df)
        assert "invoice" in result.columns
        assert "stockcode" in result.columns

    def test_existing_normalized_columns_unchanged(self):
        df = make_clean_df()
        result = normalize_headers(df)
        for col in REQUIRED_COLUMNS:
            assert col in result.columns

    def test_mixed_case_and_spaces(self):
        df = pd.DataFrame({"INVOICE": [1], "Stock Code": [2]})
        result = normalize_headers(df)
        assert "invoice" in result.columns


# ── check_schema ──────────────────────────────────────────────────────────────

class TestCheckSchema:
    def test_valid_df_returns_no_missing_cols(self):
        df = make_clean_df()
        missing = check_schema(df)
        assert missing == []

    def test_missing_invoice_detected(self):
        df = make_clean_df().drop(columns=[COL_INVOICE])
        missing = check_schema(df)
        assert COL_INVOICE in missing

    def test_missing_quantity_detected(self):
        df = make_clean_df().drop(columns=[COL_QUANTITY])
        missing = check_schema(df)
        assert COL_QUANTITY in missing

    def test_empty_dataframe_raises(self):
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="empty"):
            check_schema(df)

    def test_multiple_missing_columns_detected(self):
        df = make_clean_df().drop(columns=[COL_INVOICE, COL_PRICE])
        missing = check_schema(df)
        assert COL_INVOICE in missing
        assert COL_PRICE in missing


# ── flag_missing_required ─────────────────────────────────────────────────────

class TestFlagMissingRequired:
    def test_no_missing_returns_no_rejects(self):
        df = make_clean_df()
        mask, reasons = flag_missing_required(df)
        assert mask.sum() == 0

    def test_null_invoice_rejected(self):
        df = make_clean_df()
        df.loc[0, COL_INVOICE] = None
        mask, reasons = flag_missing_required(df)
        assert mask.iloc[0] is True or mask.iloc[0] == True  # noqa: E712
        assert "null_invoice" in reasons.iloc[0]

    def test_blank_invoice_rejected(self):
        df = make_clean_df()
        df.loc[0, COL_INVOICE] = "   "  # whitespace only
        mask, reasons = flag_missing_required(df)
        assert mask.iloc[0]

    def test_null_quantity_rejected(self):
        df = make_clean_df()
        df.loc[1, COL_QUANTITY] = None
        mask, reasons = flag_missing_required(df)
        assert mask.iloc[1]

    def test_null_price_rejected(self):
        df = make_clean_df()
        df.loc[2, COL_PRICE] = None
        mask, reasons = flag_missing_required(df)
        assert mask.iloc[2]

    def test_missing_customer_id_not_rejected(self):
        """CustomerID is optional — should NOT be rejected."""
        df = make_clean_df()
        df[COL_CUSTOMER] = None  # all missing
        mask, _ = flag_missing_required(df)
        assert mask.sum() == 0  # none rejected for missing customer


# ── flag_non_numeric ──────────────────────────────────────────────────────────

class TestFlagNonNumeric:
    def test_numeric_values_pass(self):
        df = make_clean_df()
        _, bad = flag_non_numeric(df, COL_QUANTITY)
        assert bad.sum() == 0

    def test_text_quantity_flagged(self):
        df = make_clean_df()
        df[COL_QUANTITY] = df[COL_QUANTITY].astype(object)
        df.loc[0, COL_QUANTITY] = "abc"
        _, bad = flag_non_numeric(df, COL_QUANTITY)
        assert bad.iloc[0]

    def test_text_price_flagged(self):
        df = make_clean_df()
        df[COL_PRICE] = df[COL_PRICE].astype(object)
        df.loc[1, COL_PRICE] = "N/A"
        _, bad = flag_non_numeric(df, COL_PRICE)
        assert bad.iloc[1]

    def test_null_quantity_not_flagged_as_non_numeric(self):
        """NaN was already null — not 'present but non-numeric'."""
        df = make_clean_df()
        df[COL_QUANTITY] = df[COL_QUANTITY].astype(object)
        df.loc[0, COL_QUANTITY] = None
        _, bad = flag_non_numeric(df, COL_QUANTITY)
        assert not bad.iloc[0]  # null is not "non-numeric", it's "missing"

    def test_negative_quantity_is_numeric(self):
        """Negative quantity is a valid return — must NOT be flagged as non-numeric."""
        df = make_clean_df()
        df.loc[0, COL_QUANTITY] = -5
        _, bad = flag_non_numeric(df, COL_QUANTITY)
        assert not bad.iloc[0]


# ── flag_invalid_dates ────────────────────────────────────────────────────────

class TestFlagInvalidDates:
    def test_valid_dates_pass(self):
        df = make_clean_df()
        _, bad = flag_invalid_dates(df)
        assert bad.sum() == 0

    def test_garbage_date_flagged(self):
        df = make_clean_df()
        df[COL_DATE] = df[COL_DATE].astype(object)
        df.loc[0, COL_DATE] = "not-a-date"
        _, bad = flag_invalid_dates(df)
        assert bad.iloc[0]

    def test_null_date_not_flagged_as_invalid(self):
        """Null date is 'missing', not 'invalid'. Both result in rejection, but via separate rules."""
        df = make_clean_df()
        df[COL_DATE] = df[COL_DATE].astype(object)
        df.loc[0, COL_DATE] = None
        _, bad = flag_invalid_dates(df)
        assert not bad.iloc[0]  # null, not invalid


# ── flag_negative_price ───────────────────────────────────────────────────────

class TestFlagNegativePrice:
    def test_positive_price_not_flagged(self):
        df = make_clean_df()
        df[COL_PRICE] = pd.to_numeric(df[COL_PRICE])
        bad = flag_negative_price(df)
        assert bad.sum() == 0

    def test_zero_price_not_flagged(self):
        """Zero price = free item; should NOT be rejected."""
        df = make_clean_df()
        df[COL_PRICE] = pd.to_numeric(df[COL_PRICE])
        df.loc[0, COL_PRICE] = 0.0
        bad = flag_negative_price(df)
        assert not bad.iloc[0]

    def test_negative_price_flagged(self):
        df = make_clean_df()
        df[COL_PRICE] = pd.to_numeric(df[COL_PRICE])
        df.loc[0, COL_PRICE] = -1.0
        bad = flag_negative_price(df)
        assert bad.iloc[0]


# ── flag_duplicates ───────────────────────────────────────────────────────────

class TestFlagDuplicates:
    def test_no_duplicates_in_clean_data(self):
        df = make_clean_df()
        df[COL_QUANTITY] = pd.to_numeric(df[COL_QUANTITY])
        df[COL_PRICE]    = pd.to_numeric(df[COL_PRICE])
        df[COL_DATE]     = pd.to_datetime(df[COL_DATE])
        unique, dups, count = flag_duplicates(df)
        assert count == 0
        assert len(unique) == len(df)
        assert len(dups) == 0

    def test_exact_duplicate_detected(self):
        df = make_clean_df(3)
        df[COL_QUANTITY] = pd.to_numeric(df[COL_QUANTITY])
        df[COL_PRICE]    = pd.to_numeric(df[COL_PRICE])
        df[COL_DATE]     = pd.to_datetime(df[COL_DATE])
        # Add a duplicate of row 0
        dup = df.iloc[[0]].copy()
        df = pd.concat([df, dup], ignore_index=True)
        unique, dups, count = flag_duplicates(df)
        assert count == 1
        assert len(unique) == 3  # first occurrence kept
        assert COL_REJECT_REASON in dups.columns
        assert "duplicate" in dups.iloc[0][COL_REJECT_REASON]

    def test_first_occurrence_kept(self):
        df = make_clean_df(2)
        df[COL_QUANTITY] = pd.to_numeric(df[COL_QUANTITY])
        df[COL_PRICE]    = pd.to_numeric(df[COL_PRICE])
        df[COL_DATE]     = pd.to_datetime(df[COL_DATE])
        # Duplicate row 0 twice
        dup = df.iloc[[0]].copy()
        df = pd.concat([df, dup, dup], ignore_index=True)
        unique, dups, count = flag_duplicates(df)
        assert count == 2
        assert len(unique) == 2


# ── add_cancellation_flag ─────────────────────────────────────────────────────

class TestAddCancellationFlag:
    def test_normal_invoice_not_cancellation(self):
        df = make_clean_df()
        result = add_cancellation_flag(df)
        assert not result[COL_CANCEL].any()

    def test_c_prefix_invoice_is_cancellation(self):
        df = make_clean_df(3)
        df.loc[1, COL_INVOICE] = "C12345"
        result = add_cancellation_flag(df)
        assert result.loc[1, COL_CANCEL] is True or result.loc[1, COL_CANCEL] == True  # noqa: E712

    def test_lowercase_c_prefix_is_cancellation(self):
        df = make_clean_df(1)
        df.loc[0, COL_INVOICE] = "c99999"
        result = add_cancellation_flag(df)
        assert result.loc[0, COL_CANCEL]


# ── add_line_amount ───────────────────────────────────────────────────────────

class TestAddLineAmount:
    def test_line_amount_is_quantity_times_price(self):
        df = make_clean_df(3)
        df[COL_QUANTITY] = [10, 5, -3]
        df[COL_PRICE]    = [2.50, 10.00, 5.00]
        df[COL_QUANTITY] = pd.to_numeric(df[COL_QUANTITY])
        df[COL_PRICE]    = pd.to_numeric(df[COL_PRICE])
        result = add_line_amount(df)
        assert result.loc[0, COL_LINE_AMOUNT] == pytest.approx(25.0)
        assert result.loc[1, COL_LINE_AMOUNT] == pytest.approx(50.0)
        assert result.loc[2, COL_LINE_AMOUNT] == pytest.approx(-15.0)


# ── validate_dataframe (integration) ─────────────────────────────────────────

class TestValidateDataframe:
    def test_clean_data_passes_fully(self):
        df = make_clean_df(10)
        result = validate_dataframe(df)
        assert result.clean_count == 10
        assert result.rejected_count == 0
        assert COL_CANCEL in result.clean.columns
        assert COL_LINE_AMOUNT in result.clean.columns

    def test_reconciliation_invariant(self):
        """clean + rejected must equal input rows."""
        df = make_clean_df(20)
        df[COL_QUANTITY] = df[COL_QUANTITY].astype(object)
        # Introduce some bad rows
        df.loc[0, COL_PRICE] = -1.0       # rejected: negative price
        df.loc[1, COL_INVOICE] = None     # rejected: null invoice
        df.loc[2, COL_QUANTITY] = "bad"   # rejected: non-numeric quantity
        result = validate_dataframe(df)
        assert result.clean_count + result.rejected_count == 20

    def test_negative_quantity_kept_in_clean(self):
        """Returns (negative qty) must NOT be rejected."""
        df = make_clean_df(5)
        df.loc[0, COL_QUANTITY] = -10  # return row
        result = validate_dataframe(df)
        # Row 0 should be in clean, not rejected
        assert result.clean_count == 5
        assert result.rejected_count == 0

    def test_cancellation_invoice_kept_in_clean(self):
        """Cancellations are valid records — not rejected."""
        df = make_clean_df(5)
        df.loc[0, COL_INVOICE] = "C12345"
        result = validate_dataframe(df)
        assert result.clean_count == 5
        # Cancellation row should have is_cancellation = True
        cancel_rows = result.clean[result.clean[COL_CANCEL] == True]  # noqa: E712
        assert len(cancel_rows) == 1

    def test_missing_schema_raises(self):
        """Missing required columns → ValueError."""
        df = pd.DataFrame({COL_INVOICE: ["A1"]})  # missing quantity, price, date, stockcode
        with pytest.raises(ValueError, match="Required columns missing"):
            validate_dataframe(df)

    def test_empty_dataframe_raises(self):
        """Empty DataFrame → ValueError from check_schema."""
        df = pd.DataFrame()
        with pytest.raises(ValueError):
            validate_dataframe(df)

    def test_duplicate_rows_rejected(self):
        df = make_clean_df(5)
        dup = df.iloc[[0]].copy()
        df = pd.concat([df, dup], ignore_index=True)  # 6 rows, 1 duplicate
        result = validate_dataframe(df)
        assert result.duplicate_count == 1
        assert result.clean_count + result.rejected_count == 6

    def test_zero_price_not_rejected(self):
        """Free items (price=0) are valid."""
        df = make_clean_df(5)
        df.loc[0, COL_PRICE] = 0.0
        result = validate_dataframe(df)
        assert result.clean_count == 5

    def test_rejection_reason_populated(self):
        """Rejected rows must have a non-empty rejection_reason."""
        df = make_clean_df(3)
        df.loc[0, COL_INVOICE] = None
        result = validate_dataframe(df)
        assert result.rejected_count >= 1
        reasons = result.rejected[COL_REJECT_REASON]
        assert all(r.strip() != "" for r in reasons)

    def test_missing_optional_customer_does_not_reject(self):
        df = make_clean_df(5)
        df[COL_CUSTOMER] = None
        result = validate_dataframe(df)
        assert result.clean_count == 5

    def test_single_row_clean(self):
        df = make_clean_df(1)
        result = validate_dataframe(df)
        assert result.clean_count == 1

    def test_all_rows_rejected(self):
        """When all rows are invalid, clean is empty."""
        df = make_clean_df(3)
        df[COL_INVOICE] = None
        result = validate_dataframe(df)
        assert result.clean_count == 0
        assert result.rejected_count == 3
