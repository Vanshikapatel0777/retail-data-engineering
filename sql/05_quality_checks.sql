-- =============================================================================
-- sql/05_quality_checks.sql
-- Data quality assertions run after every pipeline load
-- =============================================================================
--
-- PURPOSE
-- -------
-- These checks verify that the data in the staging table is internally
-- consistent and meets expectations.  Each check raises a NOTICE if it
-- passes or a WARNING if it fails.
--
-- INTERVIEW TALKING POINT
-- -----------------------
-- "I run SQL quality checks after each load to catch issues that Python-level
-- validation might miss — like duplicate rows surviving to the database, or
-- unexpected NULL values that appeared during SQL transformation."

DO $$
DECLARE
    v_total         bigint;
    v_null_invoice  bigint;
    v_null_stock    bigint;
    v_neg_price     bigint;
    v_null_date     bigint;
    v_bad_amount    bigint;
    v_check_passed  int := 0;
    v_check_failed  int := 0;
BEGIN
    -- Check 1: Table must not be empty
    SELECT COUNT(*) INTO v_total FROM staging.stg_transactions;
    IF v_total = 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: staging.stg_transactions is empty!';
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: Row count = %', v_total;
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Check 2: No NULL invoice numbers
    SELECT COUNT(*) INTO v_null_invoice
    FROM staging.stg_transactions
    WHERE invoice IS NULL OR TRIM(invoice::text) = '';

    IF v_null_invoice > 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: % rows with NULL/blank invoice', v_null_invoice;
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: No NULL invoice numbers';
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Check 3: No NULL stock codes
    SELECT COUNT(*) INTO v_null_stock
    FROM staging.stg_transactions
    WHERE stockcode IS NULL OR TRIM(stockcode::text) = '';

    IF v_null_stock > 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: % rows with NULL/blank stockcode', v_null_stock;
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: No NULL stock codes';
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Check 4: No negative prices (zero is allowed)
    SELECT COUNT(*) INTO v_neg_price
    FROM staging.stg_transactions
    WHERE price < 0;

    IF v_neg_price > 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: % rows with negative price (should have been rejected)', v_neg_price;
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: No negative prices';
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Check 5: No NULL invoice dates
    SELECT COUNT(*) INTO v_null_date
    FROM staging.stg_transactions
    WHERE invoicedate IS NULL;

    IF v_null_date > 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: % rows with NULL invoicedate', v_null_date;
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: No NULL invoice dates';
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Check 6: line_amount = quantity * price for non-NULL amounts
    SELECT COUNT(*) INTO v_bad_amount
    FROM staging.stg_transactions
    WHERE ABS(line_amount - (quantity * price)) > 0.001;

    IF v_bad_amount > 0 THEN
        RAISE WARNING 'QUALITY CHECK FAIL: % rows where line_amount != quantity*price', v_bad_amount;
        v_check_failed := v_check_failed + 1;
    ELSE
        RAISE NOTICE 'QUALITY CHECK PASS: line_amount = quantity * price for all rows';
        v_check_passed := v_check_passed + 1;
    END IF;

    -- Summary
    RAISE NOTICE '=== QUALITY CHECK SUMMARY: % passed, % failed ===',
        v_check_passed, v_check_failed;

    IF v_check_failed > 0 THEN
        RAISE WARNING 'DATA QUALITY ISSUES DETECTED — review staging table!';
    END IF;
END $$;
