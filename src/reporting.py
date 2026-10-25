"""
src/reporting.py — Analytical Query Runner
==========================================

WHY THIS FILE EXISTS
--------------------
After SQL scripts create analytics views, this module provides Python-level
access to run and display those views as DataFrames.

WHAT THIS FILE DOES
-------------------
1. Run pre-defined analytical queries against the PostgreSQL analytics schema
2. Print formatted results to console and log
3. Run data quality assertion checks
4. Provide a summary of pipeline data health

These functions are called:
  - By run_pipeline.py at the end of a successful pipeline run
  - Interactively for ad-hoc analysis
  - In integration tests to verify SQL logic
"""

from __future__ import annotations

import logging

import pandas as pd

from src.config import pipeline_config

logger = logging.getLogger(__name__)

# ── Analytics queries ──────────────────────────────────────────────────────────

QUERY_DAILY_SALES = """
    SELECT * FROM analytics.v_daily_sales
    ORDER BY sale_date DESC
    LIMIT 30;
"""

QUERY_MONTHLY_TRENDS = """
    SELECT * FROM analytics.v_monthly_trends
    ORDER BY year DESC, month DESC
    LIMIT 24;
"""

QUERY_TOP_PRODUCTS = """
    SELECT * FROM analytics.v_top_products
    LIMIT 20;
"""

QUERY_COUNTRY_SALES = """
    SELECT * FROM analytics.v_country_sales
    ORDER BY total_revenue DESC
    LIMIT 20;
"""

QUERY_RETURN_ANALYSIS = """
    SELECT * FROM analytics.v_return_analysis;
"""

QUERY_QUALITY_SUMMARY = """
    SELECT
        COUNT(*) AS total_rows,
        SUM(CASE WHEN customerid IS NULL THEN 1 ELSE 0 END) AS missing_customer,
        SUM(CASE WHEN description IS NULL OR TRIM(description) = '' THEN 1 ELSE 0 END) AS missing_desc,
        SUM(CASE WHEN is_cancellation THEN 1 ELSE 0 END) AS cancellations,
        SUM(CASE WHEN quantity < 0 AND NOT is_cancellation THEN 1 ELSE 0 END) AS returns,
        MIN(invoicedate) AS earliest_date,
        MAX(invoicedate) AS latest_date,
        COUNT(DISTINCT invoice) AS distinct_invoices,
        COUNT(DISTINCT customerid) AS distinct_customers,
        COUNT(DISTINCT country) AS distinct_countries
    FROM staging.stg_transactions;
"""


def _run_query(sql: str, label: str) -> pd.DataFrame:
    """Execute a SQL query and return a DataFrame."""
    if pipeline_config.local_only:
        logger.info("LOCAL_ONLY mode — skipping query: %s", label)
        return pd.DataFrame()

    from src.load_postgres import get_connection
    from sqlalchemy import text

    try:
        with get_connection() as conn:
            df = pd.read_sql(text(sql), conn)
        logger.info("Query '%s' returned %d rows", label, len(df))
        return df
    except Exception as exc:
        logger.error("Query '%s' failed: %s", label, exc)
        return pd.DataFrame()


def run_quality_report() -> dict:
    """
    Run the quality summary query against the staging table.
    Falls back to Parquet analysis if PostgreSQL is unavailable or in local_only mode.
    """
    if pipeline_config.local_only:
        logger.info("LOCAL_ONLY mode — running quality report from Parquet.")
        return _parquet_quality_report()

    df = _run_query(QUERY_QUALITY_SUMMARY, "quality_summary")
    if df.empty:
        logger.info("PostgreSQL unavailable — falling back to Parquet quality report.")
        return _parquet_quality_report()

    metrics = df.iloc[0].to_dict()
    logger.info("=== DATA QUALITY REPORT (PostgreSQL) ===")
    for key, value in metrics.items():
        logger.info("  %-28s: %s", key, value)
    logger.info("=========================================")
    return metrics


def _parquet_quality_report() -> dict:
    """Quality report from local Parquet (no DB needed)."""
    from src.transform import read_parquet

    if not pipeline_config.clean_parquet.exists():
        logger.warning("Parquet file not found — cannot run quality report.")
        return {}

    df = read_parquet(pipeline_config.clean_parquet)
    metrics = {
        "total_rows": len(df),
        "missing_customer": int(df["customerid"].isna().sum()) if "customerid" in df.columns else 0,
        "missing_desc": int((df["description"].isna() | (df["description"].astype(str).str.strip() == "")).sum()) if "description" in df.columns else 0,
        "cancellations": int(df["is_cancellation"].sum()) if "is_cancellation" in df.columns else 0,
        "returns": int(((df["quantity"] < 0) & ~df["is_cancellation"]).sum()) if ("quantity" in df.columns and "is_cancellation" in df.columns) else 0,
        "earliest_date": str(df["invoicedate"].min()) if "invoicedate" in df.columns else "N/A",
        "latest_date": str(df["invoicedate"].max()) if "invoicedate" in df.columns else "N/A",
        "distinct_invoices": int(df["invoice"].nunique()) if "invoice" in df.columns else 0,
        "distinct_customers": int(df["customerid"].dropna().nunique()) if "customerid" in df.columns else 0,
        "distinct_countries": int(df["country"].dropna().nunique()) if "country" in df.columns else 0,
    }

    logger.info("=== DATA QUALITY REPORT (from Parquet) ===")
    for key, value in metrics.items():
        logger.info("  %-28s: %s", key, value)
    logger.info("==========================================")
    return metrics


def print_analytics_summary() -> None:
    """
    Run all analytics queries and print a formatted summary.
    If PostgreSQL is unavailable, computes analytics directly from Parquet.
    """
    logger.info("Running analytics summary ...")

    queries = [
        (QUERY_DAILY_SALES,     "Daily Sales (last 30 days)"),
        (QUERY_MONTHLY_TRENDS,  "Monthly Trends (last 24 months)"),
        (QUERY_TOP_PRODUCTS,    "Top 20 Products by Revenue"),
        (QUERY_COUNTRY_SALES,   "Country-wise Sales (top 20)"),
        (QUERY_RETURN_ANALYSIS, "Return & Cancellation Analysis"),
    ]

    has_db_data = False
    for sql, label in queries:
        df = _run_query(sql, label)
        if not df.empty:
            has_db_data = True
            print(f"\n{'='*60}")
            print(f"  {label} (PostgreSQL)")
            print("=" * 60)
            with pd.option_context("display.max_columns", None, "display.width", 120):
                print(df.to_string(index=False))

    if not has_db_data:
        print("\n[INFO] PostgreSQL views unavailable. Computing analytics from Parquet...\n")
        _print_parquet_analytics()


def _print_parquet_analytics() -> None:
    """Compute and display business KPIs directly from Parquet."""
    from src.transform import read_parquet

    if not pipeline_config.clean_parquet.exists():
        print("No Parquet data found. Run pipeline first.")
        return

    df = read_parquet(pipeline_config.clean_parquet)
    df["sale_date"] = pd.to_datetime(df["invoicedate"]).dt.date
    df["year_month"] = pd.to_datetime(df["invoicedate"]).dt.to_period("M").astype(str)

    # Classify transaction type
    df["tx_type"] = "other"
    df.loc[df["is_cancellation"], "tx_type"] = "cancellation"
    df.loc[(~df["is_cancellation"]) & (df["quantity"] < 0), "tx_type"] = "return"
    df.loc[(~df["is_cancellation"]) & (df["quantity"] > 0) & (df["price"] > 0), "tx_type"] = "sale"
    df.loc[(~df["is_cancellation"]) & (df["price"] == 0), "tx_type"] = "free_item"

    # 1. Monthly trends
    print("=" * 60)
    print("  Monthly Sales Trends (from Parquet)")
    print("=" * 60)
    monthly = []
    for ym, g in df.groupby("year_month"):
        sales = g[g["tx_type"] == "sale"]["line_amount"].sum()
        returns = g[g["tx_type"] == "return"]["line_amount"].sum()
        net = sales + returns
        invoices = g["invoice"].nunique()
        aov = round(net / invoices, 2) if invoices > 0 else 0
        monthly.append({
            "year_month": ym,
            "invoices": invoices,
            "gross_revenue": round(sales, 2),
            "return_amount": round(abs(returns), 2),
            "net_revenue": round(net, 2),
            "avg_order_value": aov,
            "customers": g["customerid"].dropna().nunique(),
        })
    m_df = pd.DataFrame(monthly).sort_values("year_month", ascending=False)
    print(m_df.to_string(index=False))

    # 2. Top Products
    print("\n" + "=" * 60)
    print("  Top 10 Products by Revenue (from Parquet)")
    print("=" * 60)
    sales_df = df[df["tx_type"].isin(["sale", "return"])]
    top_prods = (
        sales_df.groupby(["stockcode", "description"])
        .agg(
            total_sold=("quantity", lambda q: q[q > 0].sum()),
            gross_revenue=("line_amount", lambda a: a[a > 0].sum()),
            net_revenue=("line_amount", "sum"),
        )
        .reset_index()
        .sort_values("gross_revenue", ascending=False)
        .head(10)
    )
    print(top_prods.to_string(index=False))

    # 3. Country Sales
    print("\n" + "=" * 60)
    print("  Country Sales (Top 10 from Parquet)")
    print("=" * 60)
    c_df = (
        df.groupby("country")
        .agg(
            invoices=("invoice", "nunique"),
            customers=("customerid", lambda c: c.dropna().nunique()),
            net_revenue=("line_amount", "sum"),
            total_lines=("invoice", "count"),
        )
        .reset_index()
        .sort_values("net_revenue", ascending=False)
        .head(10)
    )
    print(c_df.to_string(index=False))

    # 4. Return Analysis
    print("\n" + "=" * 60)
    print("  Return & Cancellation Summary (from Parquet)")
    print("=" * 60)
    total_lines = len(df)
    sale_count = (df["tx_type"] == "sale").sum()
    return_count = (df["tx_type"] == "return").sum()
    cancel_count = (df["tx_type"] == "cancellation").sum()
    gross_rev = df[df["tx_type"] == "sale"]["line_amount"].sum()
    return_val = abs(df[df["tx_type"] == "return"]["line_amount"].sum())
    net_rev = gross_rev - return_val
    ret_rate = round((return_count / total_lines) * 100, 2) if total_lines > 0 else 0

    ret_summary = pd.DataFrame([{
        "total_lines": total_lines,
        "sales_count": sale_count,
        "return_count": return_count,
        "cancel_count": cancel_count,
        "gross_sales": round(gross_rev, 2),
        "return_value": round(return_val, 2),
        "net_sales": round(net_rev, 2),
        "return_rate_pct": ret_rate,
    }])
    print(ret_summary.to_string(index=False))
