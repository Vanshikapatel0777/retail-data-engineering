-- =============================================================================
-- sql/04_analytics_views.sql
-- Business analytics views over analytics.fact_sales
-- =============================================================================
--
-- Each view represents one business KPI or analytical question.
-- Views are cheap — they're just stored SQL, not materialized data.
-- If query performance becomes a concern, convert to MATERIALIZED VIEW.
--
-- METRICS DEFINED
-- ----------------
-- gross_revenue    = SUM(line_amount) for all sale-type transactions
-- net_revenue      = gross_revenue + returns (returns have negative line_amount)
-- return_amount    = ABS(SUM(line_amount)) for return-type transactions
-- cancellation_cnt = count of cancellation-type transactions
-- aov              = net_revenue / distinct_invoices (Average Order Value)

-- ---------------------------------------------------------------------------
-- 1. Daily net sales
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_daily_sales AS
SELECT
    sale_date,
    COUNT(DISTINCT invoice)                                         AS total_invoices,
    COUNT(*)                                                        AS total_line_items,
    SUM(CASE WHEN transaction_type = 'sale'    THEN line_amount ELSE 0 END)
                                                                    AS gross_revenue,
    SUM(CASE WHEN transaction_type = 'return'  THEN line_amount ELSE 0 END)
                                                                    AS return_amount,
    SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item')
             THEN line_amount ELSE 0 END)                           AS net_revenue,
    SUM(CASE WHEN transaction_type = 'cancellation' THEN 1 ELSE 0 END)
                                                                    AS cancellation_lines,
    COUNT(DISTINCT customerid)                                      AS distinct_customers
FROM analytics.fact_sales
GROUP BY sale_date
ORDER BY sale_date DESC;


-- ---------------------------------------------------------------------------
-- 2. Monthly sales trends
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_monthly_trends AS
SELECT
    year,
    month,
    year_month,
    COUNT(DISTINCT invoice)                                         AS total_invoices,
    COUNT(*)                                                        AS total_line_items,
    SUM(CASE WHEN transaction_type = 'sale'    THEN line_amount ELSE 0 END)
                                                                    AS gross_revenue,
    SUM(CASE WHEN transaction_type = 'return'  THEN line_amount ELSE 0 END)
                                                                    AS return_amount,
    SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item')
             THEN line_amount ELSE 0 END)                           AS net_revenue,
    COUNT(DISTINCT customerid)                                      AS distinct_customers,
    -- Average Order Value = net_revenue / distinct invoices
    CASE
        WHEN COUNT(DISTINCT invoice) > 0
        THEN ROUND(
            SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item')
                     THEN line_amount ELSE 0 END)
            / COUNT(DISTINCT invoice)::numeric, 2)
        ELSE 0
    END                                                             AS avg_order_value
FROM analytics.fact_sales
GROUP BY year, month, year_month
ORDER BY year DESC, month DESC;


-- ---------------------------------------------------------------------------
-- 3. Top products by revenue
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_top_products AS
SELECT
    stockcode,
    MAX(description)                                                AS description,
    SUM(CASE WHEN transaction_type = 'sale' THEN quantity   ELSE 0 END)
                                                                    AS total_quantity_sold,
    SUM(CASE WHEN transaction_type = 'return' THEN ABS(quantity) ELSE 0 END)
                                                                    AS total_quantity_returned,
    SUM(CASE WHEN transaction_type = 'sale' THEN line_amount ELSE 0 END)
                                                                    AS gross_revenue,
    SUM(CASE WHEN transaction_type IN ('sale', 'return')
             THEN line_amount ELSE 0 END)                           AS net_revenue,
    COUNT(DISTINCT invoice)                                         AS invoice_count,
    COUNT(DISTINCT customerid)                                      AS customer_count
FROM analytics.fact_sales
WHERE transaction_type IN ('sale', 'return', 'free_item')
GROUP BY stockcode
ORDER BY gross_revenue DESC;


-- ---------------------------------------------------------------------------
-- 4. Country-wise sales
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_country_sales AS
SELECT
    COALESCE(country, 'Unknown')                                    AS country,
    COUNT(DISTINCT invoice)                                         AS total_invoices,
    COUNT(DISTINCT customerid)                                      AS distinct_customers,
    SUM(CASE WHEN transaction_type = 'sale' THEN line_amount ELSE 0 END)
                                                                    AS gross_revenue,
    SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item')
             THEN line_amount ELSE 0 END)                           AS total_revenue,
    COUNT(*)                                                        AS total_transactions
FROM analytics.fact_sales
GROUP BY country
ORDER BY total_revenue DESC;


-- ---------------------------------------------------------------------------
-- 5. Return and cancellation analysis
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_return_analysis AS
SELECT
    -- Total rows
    COUNT(*)                                                        AS total_rows,

    -- Sales
    SUM(CASE WHEN transaction_type = 'sale'         THEN 1 ELSE 0 END)
                                                                    AS sale_rows,
    SUM(CASE WHEN transaction_type = 'sale'         THEN line_amount ELSE 0 END)
                                                                    AS gross_sales_value,

    -- Returns (negative quantity, not a cancellation)
    SUM(CASE WHEN transaction_type = 'return'       THEN 1 ELSE 0 END)
                                                                    AS return_rows,
    ABS(SUM(CASE WHEN transaction_type = 'return'   THEN line_amount ELSE 0 END))
                                                                    AS return_value,

    -- Cancellations (invoice starts with C)
    SUM(CASE WHEN transaction_type = 'cancellation' THEN 1 ELSE 0 END)
                                                                    AS cancellation_rows,

    -- Free items
    SUM(CASE WHEN transaction_type = 'free_item'    THEN 1 ELSE 0 END)
                                                                    AS free_item_rows,

    -- Net sales (gross - returns)
    SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item')
             THEN line_amount ELSE 0 END)                           AS net_sales_value,

    -- Return rate (by row count)
    CASE
        WHEN COUNT(*) > 0
        THEN ROUND(
            SUM(CASE WHEN transaction_type = 'return' THEN 1 ELSE 0 END)::numeric
            / COUNT(*) * 100, 2)
        ELSE 0
    END                                                             AS return_rate_pct

FROM analytics.fact_sales;


-- ---------------------------------------------------------------------------
-- 6. Overall pipeline summary view
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.v_pipeline_summary AS
SELECT
    COUNT(*)                                                        AS total_clean_rows,
    COUNT(DISTINCT invoice)                                         AS distinct_invoices,
    COUNT(DISTINCT customerid)                                      AS distinct_customers,
    COUNT(DISTINCT stockcode)                                       AS distinct_products,
    COUNT(DISTINCT country)                                         AS distinct_countries,
    MIN(invoicedate)                                                AS earliest_transaction,
    MAX(invoicedate)                                                AS latest_transaction,
    SUM(CASE WHEN is_cancellation      THEN 1 ELSE 0 END)          AS cancellation_count,
    SUM(CASE WHEN quantity < 0
              AND NOT is_cancellation  THEN 1 ELSE 0 END)          AS return_count,
    SUM(CASE WHEN customerid IS NULL   THEN 1 ELSE 0 END)          AS missing_customer_count,
    ROUND(SUM(CASE WHEN transaction_type = 'sale' THEN line_amount ELSE 0 END)::numeric, 2)
                                                                    AS gross_revenue,
    ROUND(SUM(CASE WHEN transaction_type IN ('sale','return','free_item')
                   THEN line_amount ELSE 0 END)::numeric, 2)       AS net_revenue
FROM analytics.fact_sales;
