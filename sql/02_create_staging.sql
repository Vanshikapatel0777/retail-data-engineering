-- =============================================================================
-- sql/02_create_staging.sql
-- Create the staging transaction table
-- =============================================================================
--
-- This table is the landing zone for data loaded by load_postgres.py.
-- It is FULLY REPLACED on each pipeline run (full-refresh strategy).
--
-- COLUMN NOTES
-- invoice       : varchar — invoice ID; starts with 'C' for cancellations
-- stockcode     : varchar — product code (not always numeric)
-- description   : text    — product description (nullable: ~10% missing)
-- quantity      : integer — units; NEGATIVE = return or cancellation
-- invoicedate   : timestamp — transaction datetime
-- price         : numeric(10,4) — unit price in GBP; must be >= 0
-- customerid    : numeric(10,0) — customer ID (nullable: ~25% missing)
-- country       : varchar — customer country
-- line_amount   : numeric(12,4) — derived: quantity * price
-- is_cancellation : boolean — True if invoice starts with 'C'
--
-- NOTE: pandas to_sql with if_exists='replace' creates this table automatically.
-- This script is for explicit schema control and documentation.
-- Running it after to_sql adds proper constraints and indexes.

-- The table is created by pandas to_sql on first run.
-- We only need to add indexes and constraints afterward.
-- This script is safe to run multiple times (idempotent).

-- Create indexes if the table exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'staging'
        AND table_name = 'stg_transactions'
    ) THEN
        -- Invoice date index (used by date-range queries)
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'staging'
            AND tablename = 'stg_transactions'
            AND indexname = 'idx_stg_invoicedate'
        ) THEN
            CREATE INDEX idx_stg_invoicedate
                ON staging.stg_transactions (invoicedate);
        END IF;

        -- Country index (used by country_sales view)
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'staging'
            AND tablename = 'stg_transactions'
            AND indexname = 'idx_stg_country'
        ) THEN
            CREATE INDEX idx_stg_country
                ON staging.stg_transactions (country);
        END IF;

        -- Customer ID index (used by customer queries)
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'staging'
            AND tablename = 'stg_transactions'
            AND indexname = 'idx_stg_customerid'
        ) THEN
            CREATE INDEX idx_stg_customerid
                ON staging.stg_transactions (customerid);
        END IF;

        -- Cancellation flag index
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'staging'
            AND tablename = 'stg_transactions'
            AND indexname = 'idx_stg_is_cancellation'
        ) THEN
            CREATE INDEX idx_stg_is_cancellation
                ON staging.stg_transactions (is_cancellation);
        END IF;

        RAISE NOTICE 'Indexes created/verified on staging.stg_transactions.';
    ELSE
        RAISE NOTICE 'staging.stg_transactions does not exist yet — run ETL first.';
    END IF;
END $$;
