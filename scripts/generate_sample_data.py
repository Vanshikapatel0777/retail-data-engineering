"""
scripts/generate_sample_data.py — Generate Realistic Sample Kaggle Excel Dataset
==================================================================================

Generates a realistic multi-sheet sample Excel file matching the exact Kaggle
Online Retail II format.

Features included in sample:
  - Two sheets: 'Year 2009-2010' and 'Year 2010-2011'
  - Standard sales (positive quantity and price)
  - Returns (negative quantity, positive price)
  - Cancellations (invoice starting with 'C', negative quantity)
  - Missing Customer IDs (~25% of rows, realistic for retail guest checkout)
  - Free items (price = 0)
  - Exact duplicate rows (to verify duplicate rejection logic)
  - Edge cases to verify rejection:
      * Row with missing invoice
      * Row with negative price
      * Row with non-numeric quantity
      * Row with invalid date

Usage:
  python scripts/generate_sample_data.py
"""

from __future__ import annotations

import datetime
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_sample_dataset(target_path: Path, n_rows_per_sheet: int = 500) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    products = [
        ("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 2.55),
        ("71053", "WHITE METAL LANTERN", 3.39),
        ("84406B", "CREAM CUPID HEARTS COAT HANGER", 2.75),
        ("84029G", "KNITTED UNION FLAG HOT WATER BOTTLE", 3.39),
        ("84029E", "RED WOOLLY HOTTIE WHITE HEART.", 3.39),
        ("22752", "SET 7 BABUSHKA NESTING BOXES", 7.65),
        ("21730", "GLASS STAR FROSTED T-LIGHT HOLDER", 4.25),
        ("22633", "HAND WARMER UNION JACK", 1.85),
        ("22632", "HAND WARMER RED POLKADOT", 1.85),
        ("POST", "POSTAGE", 18.00),
    ]

    countries = ["United Kingdom", "Germany", "France", "EIRE", "Spain", "Netherlands"]

    def build_sheet_data(year_start: int, count: int) -> pd.DataFrame:
        rows = []
        base_date = datetime.datetime(year_start, 1, 15, 9, 30)

        for i in range(count):
            prod = products[i % len(products)]
            country = countries[i % len(countries)]
            cust_id = float(13000 + (i % 30)) if (i % 4 != 0) else None  # 25% missing
            dt = base_date + datetime.timedelta(days=(i // 10), hours=(i % 8))

            # Normal sale
            inv = f"{489434 + (i // 5)}"
            qty = (i % 24) + 1
            price = prod[2]

            # 1. Add some returns (every 25th row)
            if i % 25 == 20:
                qty = -((i % 5) + 1)

            # 2. Add some cancellations (every 30th row)
            if i % 30 == 15:
                inv = f"C{489434 + (i // 5)}"
                qty = -((i % 4) + 1)

            # 3. Free item sample (every 50th row)
            if i % 50 == 0:
                price = 0.0

            rows.append({
                "Invoice": inv,
                "StockCode": prod[0],
                "Description": prod[1],
                "Quantity": qty,
                "InvoiceDate": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "Price": price,
                "Customer ID": cust_id,
                "Country": country,
            })

        # Add intentional test edge cases at the end of the sheet
        # Case A: duplicate of first row
        rows.append(dict(rows[0]))

        # Case B: missing invoice (should be rejected)
        rows.append({
            "Invoice": None,
            "StockCode": "85123A",
            "Description": "MISSING INVOICE TEST",
            "Quantity": 5,
            "InvoiceDate": "2010-06-01 12:00:00",
            "Price": 2.55,
            "Customer ID": 13000.0,
            "Country": "United Kingdom",
        })

        # Case C: negative price (should be rejected)
        rows.append({
            "Invoice": "499991",
            "StockCode": "85123A",
            "Description": "NEGATIVE PRICE TEST",
            "Quantity": 5,
            "InvoiceDate": "2010-06-01 12:00:00",
            "Price": -5.00,
            "Customer ID": 13000.0,
            "Country": "United Kingdom",
        })

        # Case D: non-numeric quantity (should be rejected)
        rows.append({
            "Invoice": "499992",
            "StockCode": "85123A",
            "Description": "NON-NUMERIC QTY TEST",
            "Quantity": "INVALID_QTY",
            "InvoiceDate": "2010-06-01 12:00:00",
            "Price": 2.55,
            "Customer ID": 13000.0,
            "Country": "United Kingdom",
        })

        # Case E: invalid date (should be rejected)
        rows.append({
            "Invoice": "499993",
            "StockCode": "85123A",
            "Description": "INVALID DATE TEST",
            "Quantity": 2,
            "InvoiceDate": "not-a-real-date",
            "Price": 2.55,
            "Customer ID": 13000.0,
            "Country": "United Kingdom",
        })

        return pd.DataFrame(rows)

    df_2009 = build_sheet_data(2009, n_rows_per_sheet)
    df_2010 = build_sheet_data(2010, n_rows_per_sheet)

    with pd.ExcelWriter(str(target_path), engine="openpyxl") as writer:
        df_2009.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        df_2010.to_excel(writer, sheet_name="Year 2010-2011", index=False)

    print(f"Generated sample Excel: {target_path}")
    print(f"  Sheet 'Year 2009-2010': {len(df_2009)} rows")
    print(f"  Sheet 'Year 2010-2011': {len(df_2010)} rows")


if __name__ == "__main__":
    out = PROJECT_ROOT / "data" / "raw" / "online_retail_II.xlsx"
    create_sample_dataset(out, n_rows_per_sheet=500)
    # Also save a sample copy in data/sample/
    sample_out = PROJECT_ROOT / "data" / "sample" / "sample_retail.xlsx"
    create_sample_dataset(sample_out, n_rows_per_sheet=100)
