-- =============================================================================
-- sql/03_transform_sales.sql
-- Create analytics.fact_sales — the clean, analytics-ready facts table
-- =============================================================================
--
-- PURPOSE
-- -------
-- The staging table is a raw landing zone — it holds every clean record from
-- the pipeline, including cancellations and returns.
--
-- This script creates analytics.fact_sales as a VIEW over staging data.
-- Using a VIEW (not a materialized table) means:
--   - No data duplication
--   - Always reflects the latest staging data
--   - No additional loading step required
--
-- BUSINESS RULES APPLIED HERE
-- ----------------------------
-- line_amount = quantity * price  (already computed in staging)
-- is_cancellation = invoice starts with 'C'
-- Returns = negative quantity on non-cancellation invoices
-- Gross sales = SUM(line_amount) where NOT is_cancellation
-- Net sales = SUM(line_amount) — includes returns (negative quantities)
-- Revenue (excluding returns) = SUM(line_amount) WHERE quantity > 0
--
-- SCHEMA CHOICE
-- -------------
-- analytics.fact_sales is placed in analytics schema to separate it from
-- the raw staging data. DBAs can grant read-only on analytics to BI tools.

CREATE OR REPLACE VIEW analytics.fact_sales AS
SELECT
    invoice,
    stockcode,
    description,
    quantity,
    invoicedate,
    price,
    customerid,
    country,
    line_amount,
    is_cancellation,
    -- Classify each transaction line
    CASE
        WHEN is_cancellation              THEN 'cancellation'
        WHEN quantity < 0                 THEN 'return'
        WHEN quantity > 0 AND price > 0  THEN 'sale'
        WHEN price = 0                   THEN 'free_item'
        ELSE 'other'
    END AS transaction_type,
    -- Date parts for partitioning in analytics
    DATE(invoicedate)::date                     AS sale_date,
    EXTRACT(YEAR  FROM invoicedate)::int        AS year,
    EXTRACT(MONTH FROM invoicedate)::int        AS month,
    EXTRACT(DOW   FROM invoicedate)::int        AS day_of_week,
    TO_CHAR(invoicedate, 'YYYY-MM')             AS year_month
FROM staging.stg_transactions;
