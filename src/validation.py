"""
src/validation.py — Data Quality Validation Functions
=====================================================

WHY THIS FILE EXISTS
--------------------
Validation is separated from ETL so that:
  - Tests can call validation functions directly with synthetic DataFrames
  - The same rules can be applied at multiple pipeline stages
  - Business rules are documented alongside the code that enforces them

BUSINESS RULES (documented)
----------------------------
1.  Invoice      - required; must be a non-blank string
2.  StockCode    - required; must be non-blank
3.  Quantity     - required numeric; NEGATIVE is allowed (returns/credit notes)
4.  Price        - required numeric; must be >= 0 (zero is allowed: free items)
5.  InvoiceDate  - required; must parse as a valid datetime
6.  CustomerID   - OPTIONAL; rows without it are kept but flagged
7.  Description  - OPTIONAL; blank descriptions are flagged but not rejected
8.  Country      - OPTIONAL; blank is flagged

CANCELLED INVOICES
------------------
Invoices whose invoice number starts with 'C' are cancellations.
They are NOT automatically rejected — they represent real business events
(returned or cancelled orders).  They are separated into a dedicated column
`is_cancellation` so SQL analytics can handle them correctly.

RETURNS vs CANCELLATIONS
-------------------------
Negative quantity on a non-cancelled invoice = a return/credit note
Negative quantity on a cancelled invoice = a cancellation

Both are kept in the clean dataset.  The SQL layer decides what to exclude
from "net revenue" queries.

DUPLICATES
----------
A duplicate is defined as: same invoice + same stockcode + same invoicedate
+ same quantity + same price.  The first occurrence is kept; subsequent ones
are moved to the rejected dataset with reason "duplicate".

RECONCILIATION INVARIANT
------------------------
input_rows = clean_rows + rejected_rows

If duplicates are removed, they count as rejected (not silently dropped).
The pipeline run audit records this breakdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column name constants ─────────────────────────────────────────────────────

# These are the NORMALISED column names we expect after header normalisation.
# Source headers are mapped to these in etl.py.
COL_INVOICE     = "invoice"
COL_STOCKCODE   = "stockcode"
COL_DESC        = "description"
COL_QUANTITY    = "quantity"
COL_DATE        = "invoicedate"
COL_PRICE       = "price"
COL_CUSTOMER    = "customerid"
COL_COUNTRY     = "country"

# Derived columns added by the pipeline
COL_LINE_AMOUNT    = "line_amount"
COL_CANCEL         = "is_cancellation"
COL_REJECT_REASON  = "rejection_reason"

REQUIRED_COLUMNS = [
    COL_INVOICE, COL_STOCKCODE, COL_QUANTITY, COL_DATE, COL_PRICE,
]

OPTIONAL_COLUMNS = [COL_DESC, COL_CUSTOMER, COL_COUNTRY]

ALL_EXPECTED_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Duplicate detection key
DUPLICATE_KEY_COLS = [COL_INVOICE, COL_STOCKCODE, COL_DATE, COL_QUANTITY, COL_PRICE]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Returned by validate_dataframe()."""
    clean: pd.DataFrame          = field(default_factory=pd.DataFrame)
    rejected: pd.DataFrame       = field(default_factory=pd.DataFrame)
    duplicate_count: int         = 0
    issues: list[str]            = field(default_factory=list)

    @property
    def clean_count(self) -> int:
        return len(self.clean)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


# ── Individual check functions ────────────────────────────────────────────────

def check_schema(df: pd.DataFrame) -> list[str]:
    """
    Return a list of missing required columns.
    Raises ValueError if the DataFrame is empty.
    """
    if df.empty:
        raise ValueError("Input DataFrame is empty — nothing to validate.")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    return missing


def normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lowercase and strip column names.
    Maps known source header variants to normalised names.

    Source → Target mapping:
    ┌─────────────────────┬───────────────┐
    │ Source header       │ Target name   │
    ├─────────────────────┼───────────────┤
    │ InvoiceNo           │ invoice       │
    │ Invoice             │ invoice       │
    │ StockCode           │ stockcode     │
    │ Description         │ description   │
    │ Quantity            │ quantity      │
    │ InvoiceDate         │ invoicedate   │
    │ UnitPrice           │ price         │
    │ Price               │ price         │
    │ Customer ID         │ customerid    │
    │ CustomerID          │ customerid    │
    │ Country             │ country       │
    └─────────────────────┴───────────────┘
    """
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower().str.replace(r"\s+", "", regex=True)

    rename_map = {
        "invoiceno":   COL_INVOICE,
        "invoice":     COL_INVOICE,
        "stockcode":   COL_STOCKCODE,
        "description": COL_DESC,
        "quantity":    COL_QUANTITY,
        "invoicedate": COL_DATE,
        "unitprice":   COL_PRICE,
        "price":       COL_PRICE,
        "customerid":  COL_CUSTOMER,
        "customer id": COL_CUSTOMER,
        "country":     COL_COUNTRY,
    }
    df = df.rename(columns=rename_map)
    return df


def flag_missing_required(df: pd.DataFrame) -> pd.Series:
    """
    Return a boolean mask (True = should be rejected) based on missing required fields.
    Also populates a rejection_reason string.
    """
    reasons = pd.Series([""] * len(df), index=df.index)

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            # Column absent — all rows fail this check
            reasons = reasons + f"missing_column:{col}; "
            continue
        null_mask = df[col].isna()
        if col in (COL_INVOICE, COL_STOCKCODE):
            # Also reject blank strings
            blank_mask = df[col].astype(str).str.strip() == ""
            null_mask = null_mask | blank_mask
        reasons = reasons.where(~null_mask, reasons + f"null_{col}; ")

    reject_mask = reasons.str.strip() != ""
    return reject_mask, reasons


def flag_non_numeric(df: pd.DataFrame, col: str) -> Tuple[pd.Series, pd.Series]:
    """
    Attempt coercion to numeric.  Return (coerced_series, bad_mask).
    Rows where coercion produces NaN are flagged.
    """
    coerced = pd.to_numeric(df[col], errors="coerce")
    bad_mask = coerced.isna() & df[col].notna()  # was present but not numeric
    return coerced, bad_mask


def flag_negative_price(df: pd.DataFrame) -> pd.Series:
    """Return mask of rows with price < 0.  Zero is allowed (free items)."""
    if COL_PRICE not in df.columns:
        return pd.Series(False, index=df.index)
    return df[COL_PRICE] < 0


def flag_invalid_dates(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Attempt datetime coercion on the invoicedate column.
    Return (coerced_series, bad_mask).
    """
    coerced = pd.to_datetime(df[COL_DATE], errors="coerce", dayfirst=True)
    bad_mask = coerced.isna() & df[COL_DATE].notna()
    return coerced, bad_mask


def flag_duplicates(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, int]:
    """
    Identify exact duplicate rows using DUPLICATE_KEY_COLS.
    First occurrence is kept; subsequent occurrences are returned separately.

    Returns
    -------
    unique_df    : DataFrame with duplicates removed (first occurrence kept)
    dup_df       : DataFrame of duplicate rows (with rejection_reason set)
    dup_count    : number of duplicate rows removed
    """
    key_cols = [c for c in DUPLICATE_KEY_COLS if c in df.columns]
    dup_mask = df.duplicated(subset=key_cols, keep="first")
    dup_df = df[dup_mask].copy()
    unique_df = df[~dup_mask].copy()

    if not dup_df.empty:
        existing = dup_df.get(COL_REJECT_REASON, pd.Series("", index=dup_df.index))
        dup_df[COL_REJECT_REASON] = existing + "duplicate; "

    return unique_df, dup_df, int(dup_mask.sum())


def add_cancellation_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add boolean column `is_cancellation`.
    True when the invoice number begins with 'C' (Kaggle dataset convention).
    """
    df = df.copy()
    df[COL_CANCEL] = df[COL_INVOICE].astype(str).str.strip().str.upper().str.startswith("C")
    return df


def add_line_amount(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived column `line_amount = quantity * price`.
    Requires both columns to be numeric already.
    """
    df = df.copy()
    df[COL_LINE_AMOUNT] = df[COL_QUANTITY] * df[COL_PRICE]
    return df


# ── Main validation entry point ───────────────────────────────────────────────

def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """
    Run all validation checks on a normalised DataFrame.

    Steps
    -----
    1. Schema check — fail fast if required columns are absent
    2. Missing required field check
    3. Numeric coercion (quantity, price)
    4. Date coercion
    5. Negative price check
    6. Duplicate detection
    7. Add cancellation flag on the clean subset
    8. Add line_amount on the clean subset

    Returns
    -------
    ValidationResult with .clean and .rejected DataFrames.
    """
    result = ValidationResult()

    # ── 1. Schema ──────────────────────────────────────────────────────────────
    missing_cols = check_schema(df)
    if missing_cols:
        msg = f"Required columns missing from source: {missing_cols}"
        logger.error(msg)
        result.issues.append(msg)
        raise ValueError(msg)

    df = df.copy()

    # Ensure rejection_reason column exists
    if COL_REJECT_REASON not in df.columns:
        df[COL_REJECT_REASON] = ""

    reject_mask = pd.Series(False, index=df.index)

    # ── 2. Missing required fields ────────────────────────────────────────────
    missing_mask, missing_reasons = flag_missing_required(df)
    reject_mask = reject_mask | missing_mask
    df.loc[missing_mask, COL_REJECT_REASON] = (
        df.loc[missing_mask, COL_REJECT_REASON] + missing_reasons[missing_mask]
    )

    # ── 3a. Quantity numeric coercion ─────────────────────────────────────────
    qty_coerced, qty_bad = flag_non_numeric(df, COL_QUANTITY)
    df[COL_QUANTITY] = qty_coerced
    reject_mask = reject_mask | qty_bad
    df.loc[qty_bad, COL_REJECT_REASON] = df.loc[qty_bad, COL_REJECT_REASON] + "non_numeric_quantity; "

    # ── 3b. Price numeric coercion ────────────────────────────────────────────
    price_coerced, price_bad = flag_non_numeric(df, COL_PRICE)
    df[COL_PRICE] = price_coerced
    reject_mask = reject_mask | price_bad
    df.loc[price_bad, COL_REJECT_REASON] = df.loc[price_bad, COL_REJECT_REASON] + "non_numeric_price; "

    # ── 4. Date coercion ──────────────────────────────────────────────────────
    date_coerced, date_bad = flag_invalid_dates(df)
    df[COL_DATE] = date_coerced
    reject_mask = reject_mask | date_bad
    df.loc[date_bad, COL_REJECT_REASON] = df.loc[date_bad, COL_REJECT_REASON] + "invalid_date; "

    # ── 5. Negative price ─────────────────────────────────────────────────────
    price_neg = flag_negative_price(df)
    reject_mask = reject_mask | price_neg
    df.loc[price_neg, COL_REJECT_REASON] = df.loc[price_neg, COL_REJECT_REASON] + "negative_price; "

    # ── Split into passing/failing ─────────────────────────────────────────────
    rejected_basic = df[reject_mask].copy()
    passing = df[~reject_mask].copy()

    # ── 6. Duplicate detection (only on rows that passed basic checks) ────────
    passing_dedup, dup_df, dup_count = flag_duplicates(passing)
    result.duplicate_count = dup_count

    # Combine all rejected rows
    all_rejected = pd.concat([rejected_basic, dup_df], ignore_index=True)

    # ── 7. Cancellation flag ──────────────────────────────────────────────────
    passing_dedup = add_cancellation_flag(passing_dedup)

    # ── 8. Line amount ────────────────────────────────────────────────────────
    passing_dedup = add_line_amount(passing_dedup)

    # ── Normalise customerid ──────────────────────────────────────────────────
    # Keep as nullable float/Int64; replace "nan" strings with actual NaN
    if COL_CUSTOMER in passing_dedup.columns:
        passing_dedup[COL_CUSTOMER] = pd.to_numeric(
            passing_dedup[COL_CUSTOMER], errors="coerce"
        )

    result.clean    = passing_dedup.reset_index(drop=True)
    result.rejected = all_rejected.reset_index(drop=True)

    # ── Summary logging ───────────────────────────────────────────────────────
    n_input   = len(df)
    n_clean   = result.clean_count
    n_reject  = result.rejected_count

    logger.info(
        "Validation complete | input=%d | clean=%d | rejected=%d | "
        "duplicates=%d | reconciliation_ok=%s",
        n_input, n_clean, n_reject, dup_count,
        "YES" if n_input == n_clean + n_reject else "NO",
    )

    if n_input != n_clean + n_reject:
        result.issues.append(
            f"Reconciliation mismatch: {n_input} input != "
            f"{n_clean} clean + {n_reject} rejected"
        )

    return result
