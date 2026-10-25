# 🎓 Data Engineering Interview Preparation Guide

This guide is designed to help you explain every technical decision, architecture detail, failure mode, and SQL query in this project during a technical interview.

---

## ⏱️ Elevator Pitches

### 1. 30-Second Introduction (Quick Screen)
> "I built an end-to-end retail data engineering pipeline that ingests over 500,000 raw e-commerce transaction records from Kaggle, cleans and validates them using automated data quality rules, and stores the clean output in a snappy-compressed Parquet lakehouse format. The clean data is then loaded into PostgreSQL staging and transformed using modular SQL views to power daily sales, customer metrics, return rates, and product performance analytics. The pipeline is fully idempotent, thoroughly tested with 85+ automated unit and integration tests, and features an optional Azure ADLS Gen2 cloud synchronization."

---

### 2. 90-Second Overview (Technical Round)
> "In e-commerce datasets, raw transaction logs are often messy—plagued by missing customer IDs, negative prices, duplicate lines, and cancelled orders mixed with genuine sales.
>
> To solve this, I designed a hybrid ETL/ELT architecture:
> 1. In the **Extract & Transform (ETL) layer**, Python and Pandas inspect the multi-sheet Excel workbook, normalize schema headers, and enforce 8 business validation rules. We separate clean from invalid records, routing rejected records to an audited CSV with explicit rejection reasons, guaranteeing the reconciliation invariant: `input = clean + rejected`.
> 2. For the **Data Lake layer**, clean records are cast to explicit PyArrow types and written to columnar Parquet with Snappy compression, enabling high-efficiency analytical queries.
> 3. For the **Warehouse / Staging (ELT) layer**, data is loaded into PostgreSQL using SQLAlchemy and Psycopg 3 with chunked batch inserts. Downstream SQL views classify lines into sales, returns, and cancellations, computing key metrics like Net Sales and Average Order Value (AOV).
>
> The pipeline is governed by centralized configuration, comprehensive logging, pipeline run audit tracking, and optional Azure ADLS Gen2 upload."

---

### 3. 3-Minute Deep Dive (Architecture & Deep Dive)
> "Let me walk you through the end-to-end design and the specific trade-offs I made.
>
> **The Problem:** The Kaggle Online Retail II dataset contains over 525,000 records across two years. Real retail transaction logs have edge cases that can silently corrupt downstream revenue metrics:
> - Returns have negative quantities, but they are valid business events, not data errors.
> - Cancellations (invoices prefixed with 'C') must be tracked separately from returns so revenue isn't distorted.
> - About 25% of records have missing customer IDs due to guest checkout.
> - There are exact duplicate rows and invalid records (e.g., negative prices or text quantities).
>
> **The Pipeline Architecture:**
> - **Extraction:** We use `openpyxl` in read-only mode to inspect workbook sheet names without loading full memory, finding both yearly sheets (`Year 2009-2010` and `Year 2010-2011`). We normalize headers to lowercase snake_case and tag the sheet source for lineage.
> - **Validation & Deduplication:** Before touching the database, we run deterministic validation checks. Non-numeric fields and negative prices are routed to a rejected CSV file with specific rejection codes. We identify duplicate lines based on a composite key: `(invoice, stockcode, invoicedate, quantity, price)`. The first line is kept; subsequent duplicates are logged to rejected data. We verify reconciliation: total input rows must equal clean rows plus rejected rows.
> - **Storage:** Clean data is converted to PyArrow tables and written to Parquet using Snappy compression with 100K-row groups. Parquet's columnar layout reduces storage by ~80% compared to CSV and enables projection pushdown. We automatically run a read-back roundtrip test to verify file integrity.
> - **PostgreSQL Staging & ELT:** The clean dataset is loaded into PostgreSQL `staging.stg_transactions` using chunked multi-row inserts (`chunksize=5000`). We apply B-tree indexes on `invoicedate`, `customerid`, `country`, and `is_cancellation`. Then, SQL views in the `analytics` schema (`analytics.fact_sales`) classify records and compute daily/monthly aggregations, top products, country sales, and return rates.
> - **Resilience & Testing:** I wrote 85+ automated pytest tests covering unit validations, roundtrip I/O, configuration parsing, and database integration. The pipeline is idempotent: rerunning it produces identical results without duplicating rows. If PostgreSQL is offline, the pipeline gracefully runs in local mode and computes analytics directly from Parquet."

---

## 📄 Resume Project Section

**Retail Sales Data Engineering Pipeline (Python, PostgreSQL, Parquet, Azure)**
- Designed and built an end-to-end data pipeline processing 525K+ transaction records, transforming raw multi-sheet Excel data into an analytics-ready PostgreSQL warehouse and Parquet data lake.
- Implemented a robust data validation engine in Python enforcing 8 business rules, segregating rejected records with explicit error tags and maintaining a 100% row reconciliation invariant (`input = clean + rejected`).
- Optimized storage and query efficiency by writing columnar, Snappy-compressed Parquet files, achieving an ~80% file size reduction compared to raw CSV.
- Developed modular SQL transformations and analytical views in PostgreSQL to track Daily Net Revenue, Average Order Value (AOV), and return/cancellation rates with indexed staging tables.
- Achieved high software reliability with 85+ automated unit and integration tests using pytest, zero-secret environment management, and automated audit logging.

---

## 🎯 30+ Project-Specific Interview Questions & Answers

### Architecture & System Design
#### 1. Why did you choose a hybrid ETL + ELT architecture instead of pure ETL or pure ELT?
> "Pure ELT loads raw, unvalidated data directly into the database. But with 525K rows containing malformed data types (text prices, negative prices, null invoices), dumping corrupt data into relational staging requires permissive column types (e.g. all `TEXT`), shifting complex type-casting logic into SQL.
>
> On the other hand, pure ETL performs all aggregations in Python before loading, which fails to take advantage of PostgreSQL's optimized SQL relational engine, indexing, and window functions.
>
> My hybrid design uses ETL to clean, validate, and type-cast records in Python, storing clean data in Parquet, and then ELT to compute analytical views and business aggregations inside PostgreSQL."

#### 2. What makes your pipeline idempotent?
> "Idempotency means running the pipeline multiple times with the same input yields the exact same state without unintended side effects or duplicate data.
> In my pipeline:
> 1. Local Parquet and CSV outputs are written with overwrite semantics (`write_table(..., overwrite=True)`).
> 2. PostgreSQL staging uses a transactional full-refresh strategy (`if_exists='replace'` in chunked batches).
> 3. Downstream SQL analytics are implemented as database VIEWs (`CREATE OR REPLACE VIEW`), so they always reflect the underlying staging state without storing duplicate rows."

#### 3. How would you transition this full-refresh pipeline to an incremental pipeline for streaming or daily batches?
> "For incremental loading, I would:
> 1. Define a unique surrogate key or composite primary key, such as `hash(invoice, stockcode, invoicedate, quantity, price)`.
> 2. Add an ingestion timestamp column (`loaded_at`).
> 3. In PostgreSQL, load daily delta files into a temporary staging table, and use a SQL `MERGE` or `INSERT ... ON CONFLICT (...) DO UPDATE` statement (UPSERT) to merge new or modified transaction lines.
> 4. In Parquet, partition the data lake directory by date: `data/processed/year=YYYY/month=MM/day=DD/` so each day's run only writes its partition."

---

### Data Quality & Business Rules
#### 4. How did you handle negative quantities? Are they errors?
> "No, negative quantities in this dataset are legitimate business transactions:
> - If the invoice starts with 'C' (e.g. `C536379`), it represents a **cancellation**.
> - If the invoice is a normal number but has a negative quantity, it represents a **customer return / credit note**.
>
> Rejecting negative quantities would falsely inflate company revenue. In my pipeline, both are kept in the clean dataset, and a derived column `is_cancellation` is added. In the SQL layer, gross sales are calculated where `quantity > 0`, return values where `quantity < 0`, and net revenue accounts for returns."

#### 5. Why do ~25% of rows have a missing `CustomerID`? Did you reject them?
> "In e-commerce, customers often purchase as guests without creating or logging into an account. Rejecting transactions with missing customer IDs would discard 25% of total sales volume.
>
> My business rule treats `customerid` as an **optional field**. Rows with missing customer IDs are retained in the clean data as `NULL` (never converted to strings like `'nan'`). When reporting customer metrics (e.g., distinct customers, customer lifetime value), queries explicitly filter `WHERE customerid IS NOT NULL`, while total sales queries include all transactions."

#### 6. What is the row reconciliation invariant?
> "The invariant is:
> $$\text{Total Input Rows} = \text{Clean Rows} + \text{Rejected Rows}$$
> Every row that enters the pipeline must be accounted for. If a record is rejected (for bad dates, non-numeric prices, or duplicates), it is written to `retail_rejected.csv` with an explicit reason tag (`duplicate;`, `negative_price;`, etc.).
> At the end of validation, the pipeline asserts that clean count plus rejected count equals input count, alerting if any data was dropped silently."

#### 7. How did you identify and handle duplicate rows?
> "A single invoice contains multiple distinct products, so `invoice` alone cannot be a unique key. I defined a composite key: `(invoice, stockcode, invoicedate, quantity, price)`.
> Using Pandas' `.duplicated(subset=..., keep='first')`, the first occurrence is kept in the clean dataset, and subsequent identical lines are routed to the rejected dataset tagged with reason `'duplicate;'`."

---

### Python & Pandas
#### 8. Why did you use `dtype=object` when reading Excel with Pandas?
> "When Pandas reads Excel files, it tries to infer column data types per column. If an Excel column contains mixed data (e.g., numbers mixed with text errors or invalid dates), automatic inference can either crash or coerce unexpected values to NaN silently.
> Setting `dtype=object` preserves raw cell values as Python strings or objects, allowing our validation layer to inspect values, identify why a record failed, and log the original raw value in the rejected CSV."

#### 9. Why use PyArrow and Parquet instead of storing everything in CSV?
> "1. **Storage Efficiency:** Parquet uses dictionary encoding, run-length encoding, and Snappy compression. A 500K-row dataset in Parquet is ~15-20 MB compared to ~80-100 MB in CSV.
> 2. **Columnar Projection:** Analytical queries like `SELECT SUM(line_amount) FROM sales` only read the `line_amount` column from disk, skipping all other columns.
> 3. **Type Preservation:** CSV stores everything as plain text, leading to type ambiguity upon reload. Parquet stores strict, binary schema metadata."

#### 10. How did you avoid memory bottlenecks when loading data into PostgreSQL?
> "Using `df.to_sql()` with a large DataFrame without chunking attempts to construct a single massive SQL statement or load all records into memory at once, which can trigger an Out-Of-Memory (OOM) error or database timeout.
> I configured `chunksize=5000` with `method='multi'`, which batches insert statements into 5,000-row chunks. This keeps memory usage flat and significantly improves insertion throughput."

---

### Database & PostgreSQL
#### 11. What is the difference between `psycopg` and `SQLAlchemy`?
> "SQLAlchemy is an **Object-Relational Mapping (ORM) and SQL Toolkit** that acts as an abstraction layer. It generates database-agnostic SQL and manages connection pooling.
> `psycopg` (specifically Psycopg 3) is the **database driver**—the low-level Python library that communicates with PostgreSQL over TCP using the PostgreSQL wire protocol. SQLAlchemy sits on top of Psycopg."

#### 12. Why did you use SQL views instead of physical tables for the analytics layer?
> "In this pipeline, staging data is replaced on each run. By creating views (`analytics.fact_sales` and `analytics.v_daily_sales`), the analytical metrics are calculated dynamically on top of staging data without redundant storage or manual synchronization steps.
> If the dataset grew to hundreds of millions of rows, I would upgrade these to **Materialized Views** with scheduled refreshes or use a physical star schema (fact and dimension tables) indexed on date keys."

#### 13. How did you handle special characters in database passwords?
> "Database passwords often contain special characters like `@`, `#`, `%`, or `/`. If concatenated directly into a connection URL (e.g., `postgresql://user:p@ss@host/db`), the parser treats the `@` as the host separator, breaking authentication.
> I used Python's `urllib.parse.quote_plus` to URL-encode the password safely before formatting the SQLAlchemy URL."

---

### Cloud & Azure
#### 14. How does the Azure ADLS Gen2 integration work in this project?
> "I built an optional cloud module (`src/azure_upload.py`) using the official Azure SDK (`azure-storage-blob`). When Azure credentials (`AZURE_STORAGE_CONNECTION_STRING` or account credentials) are configured in `.env`, the pipeline uploads the processed Parquet file to the `processed/` container directory and the rejected CSV to `rejected/`.
> Crucially, if Azure credentials are not present, the pipeline logs a clean informational message and continues local execution without failing."

#### 15. What are the advantages of ADLS Gen2 over standard Azure Blob Storage?
> "ADLS Gen2 adds a **hierarchical namespace** to Blob Storage. In standard Blob Storage, directories are virtual string prefixes; renaming a folder requires copying every blob inside it. In ADLS Gen2, directories are first-class filesystem objects, making directory renames and atomic file moves fast and scalable. It is optimized for big data analytics engines like Synapse, Databricks, and Fabric."

---

## 📊 15 SQL Interview Questions on this Retail Dataset

### Q1: What is the difference between Gross Revenue and Net Revenue in this dataset?
```sql
SELECT
    SUM(CASE WHEN transaction_type = 'sale' THEN line_amount ELSE 0 END) AS gross_revenue,
    SUM(CASE WHEN transaction_type = 'return' THEN ABS(line_amount) ELSE 0 END) AS return_amount,
    SUM(CASE WHEN transaction_type IN ('sale', 'return', 'free_item') THEN line_amount ELSE 0 END) AS net_revenue
FROM analytics.fact_sales;
```

### Q2: Write a query to find the Top 5 products by Net Revenue in the UK.
```sql
SELECT
    stockcode,
    MAX(description) AS product_name,
    SUM(quantity) AS net_quantity_sold,
    ROUND(SUM(line_amount)::numeric, 2) AS net_revenue
FROM analytics.fact_sales
WHERE country = 'United Kingdom'
  AND transaction_type IN ('sale', 'return')
GROUP BY stockcode
ORDER BY net_revenue DESC
LIMIT 5;
```

### Q3: How do you compute Average Order Value (AOV) per month?
```sql
SELECT
    year_month,
    COUNT(DISTINCT invoice) AS total_orders,
    ROUND(SUM(line_amount)::numeric, 2) AS net_revenue,
    ROUND(SUM(line_amount)::numeric / COUNT(DISTINCT invoice), 2) AS average_order_value
FROM analytics.fact_sales
WHERE transaction_type IN ('sale', 'return', 'free_item')
GROUP BY year_month
ORDER BY year_month DESC;
```

### Q4: Write a query to calculate the overall Return Rate by transaction lines.
```sql
SELECT
    COUNT(*) AS total_transactions,
    SUM(CASE WHEN quantity < 0 AND NOT is_cancellation THEN 1 ELSE 0 END) AS return_transactions,
    ROUND(
        SUM(CASE WHEN quantity < 0 AND NOT is_cancellation THEN 1 ELSE 0 END)::numeric
        / COUNT(*) * 100, 2
    ) AS return_rate_percentage
FROM analytics.fact_sales;
```

### Q5: Find customers who purchased in 2009 and also returned to purchase in 2010 (Customer Retention).
```sql
SELECT
    customerid,
    COUNT(DISTINCT CASE WHEN year = 2009 THEN invoice END) AS orders_2009,
    COUNT(DISTINCT CASE WHEN year = 2010 THEN invoice END) AS orders_2010
FROM analytics.fact_sales
WHERE customerid IS NOT NULL
GROUP BY customerid
HAVING COUNT(DISTINCT CASE WHEN year = 2009 THEN invoice END) > 0
   AND COUNT(DISTINCT CASE WHEN year = 2010 THEN invoice END) > 0;
```

### Q6: Write a query to calculate Month-over-Month (MoM) revenue growth using a window function.
```sql
WITH monthly_sales AS (
    SELECT
        year_month,
        SUM(line_amount) AS revenue
    FROM analytics.fact_sales
    WHERE transaction_type IN ('sale', 'return')
    GROUP BY year_month
)
SELECT
    year_month,
    ROUND(revenue::numeric, 2) AS current_month_revenue,
    ROUND(LAG(revenue) OVER (ORDER BY year_month)::numeric, 2) AS prior_month_revenue,
    ROUND(
        ((revenue - LAG(revenue) OVER (ORDER BY year_month))
        / LAG(revenue) OVER (ORDER BY year_month) * 100)::numeric, 2
    ) AS mom_growth_pct
FROM monthly_sales
ORDER BY year_month;
```

### Q7: Find the top 3 selling products for each country using `DENSE_RANK()`.
```sql
WITH product_ranks AS (
    SELECT
        country,
        stockcode,
        MAX(description) AS description,
        SUM(line_amount) AS revenue,
        DENSE_RANK() OVER (PARTITION BY country ORDER BY SUM(line_amount) DESC) AS rank
    FROM analytics.fact_sales
    WHERE transaction_type = 'sale'
      AND country IS NOT NULL
    GROUP BY country, stockcode
)
SELECT country, rank, stockcode, description, ROUND(revenue::numeric, 2) AS revenue
FROM product_ranks
WHERE rank <= 3
ORDER BY country, rank;
```

### Q8: Identify duplicate transaction lines in staging that share invoice, stockcode, date, and price.
```sql
SELECT
    invoice,
    stockcode,
    invoicedate,
    price,
    COUNT(*) AS occurrence_count
FROM staging.stg_transactions
GROUP BY invoice, stockcode, invoicedate, price
HAVING COUNT(*) > 1;
```

### Q9: Calculate the distribution of guest transactions vs. registered customer transactions.
```sql
SELECT
    CASE WHEN customerid IS NULL THEN 'Guest Checkout' ELSE 'Registered Customer' END AS checkout_type,
    COUNT(DISTINCT invoice) AS invoice_count,
    ROUND(SUM(line_amount)::numeric, 2) AS total_revenue,
    ROUND(SUM(line_amount)::numeric / SUM(SUM(line_amount)) OVER () * 100, 2) AS revenue_share_pct
FROM analytics.fact_sales
WHERE transaction_type IN ('sale', 'return')
GROUP BY CASE WHEN customerid IS NULL THEN 'Guest Checkout' ELSE 'Registered Customer' END;
```

### Q10: Find invoices that contain both a sale and a return item within the same order.
```sql
SELECT
    invoice,
    COUNT(CASE WHEN quantity > 0 THEN 1 END) AS sales_items,
    COUNT(CASE WHEN quantity < 0 THEN 1 END) AS return_items
FROM analytics.fact_sales
GROUP BY invoice
HAVING COUNT(CASE WHEN quantity > 0 THEN 1 END) > 0
   AND COUNT(CASE WHEN quantity < 0 THEN 1 END) > 0;
```

### Q11: Find the day of the week with the highest average revenue.
```sql
SELECT
    TO_CHAR(invoicedate, 'Day') AS day_name,
    day_of_week,
    ROUND(AVG(daily_revenue)::numeric, 2) AS avg_revenue
FROM (
    SELECT
        sale_date,
        day_of_week,
        invoicedate,
        SUM(line_amount) AS daily_revenue
    FROM analytics.fact_sales
    WHERE transaction_type IN ('sale', 'return')
    GROUP BY sale_date, day_of_week, invoicedate
) daily
GROUP BY day_name, day_of_week
ORDER BY avg_revenue DESC;
```

### Q12: Calculate cumulative running revenue across all time.
```sql
SELECT
    sale_date,
    ROUND(SUM(line_amount)::numeric, 2) AS daily_revenue,
    ROUND(SUM(SUM(line_amount)) OVER (ORDER BY sale_date)::numeric, 2) AS cumulative_revenue
FROM analytics.fact_sales
WHERE transaction_type IN ('sale', 'return')
GROUP BY sale_date
ORDER BY sale_date;
```

### Q13: Identify all cancellation invoices and find their total cancelled value.
```sql
SELECT
    COUNT(DISTINCT invoice) AS cancelled_invoices,
    COUNT(*) AS cancelled_line_items,
    ROUND(ABS(SUM(line_amount))::numeric, 2) AS total_cancelled_value
FROM analytics.fact_sales
WHERE is_cancellation = TRUE;
```

### Q14: Find products that have a high return rate (>10% of sold units returned).
```sql
SELECT
    stockcode,
    MAX(description) AS description,
    SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) AS units_sold,
    SUM(CASE WHEN quantity < 0 THEN ABS(quantity) ELSE 0 END) AS units_returned,
    ROUND(
        SUM(CASE WHEN quantity < 0 THEN ABS(quantity) ELSE 0 END)::numeric
        / NULLIF(SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END), 0) * 100, 2
    ) AS return_pct
FROM analytics.fact_sales
GROUP BY stockcode
HAVING SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) >= 50
   AND (SUM(CASE WHEN quantity < 0 THEN ABS(quantity) ELSE 0 END)::numeric
        / NULLIF(SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END), 0)) > 0.10
ORDER BY return_pct DESC;
```

### Q15: Validate that no negative prices survived into the fact table.
```sql
SELECT COUNT(*) AS invalid_negative_price_rows
FROM analytics.fact_sales
WHERE price < 0;
-- Expected output: 0 rows
```

---

## 💻 Live Interview Demo Guide

Follow these exact steps if an interviewer asks you to demonstrate your project live:

### Step 1: Run the automated test suite (5 seconds)
Show that the code is well-tested and robust:
```powershell
.venv\Scripts\Activate.ps1
pytest -v
```
*Talking point: "All 89 unit and integration tests run in under 3 seconds using synthetic DataFrames and temporary directories."*

### Step 2: Run the end-to-end pipeline (10 seconds)
```powershell
python -m src.run_pipeline --local-only
```
*Talking point: "Notice the logs show multi-sheet extraction, row reconciliation (`1010 input = 1000 clean + 10 rejected`), Parquet write with snappy compression, and Parquet roundtrip verification."*

### Step 3: Display business KPIs from the analytics layer (5 seconds)
```powershell
python -c "from src.reporting import print_analytics_summary; print_analytics_summary()"
```
*Talking point: "Here we can see our monthly trends, top 10 products by gross/net revenue, geographic sales, and return/cancellation rates."*

### Step 4: Show the rejected record audit log (5 seconds)
```powershell
Get-Content data\rejected\retail_rejected.csv -TotalCount 6
```
*Talking point: "Every rejected record includes an audit trail with explicit rejection reasons, such as `negative_price`, `null_invoice`, or `duplicate`."*
