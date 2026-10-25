-- =============================================================================
-- sql/01_create_schema.sql
-- Create database schemas for the retail data warehouse
-- =============================================================================
--
-- WHY TWO SCHEMAS?
-- staging  → holds raw-loaded data exactly as it came from the pipeline
-- analytics → holds cleaned facts, dimensions, and business-ready views
--
-- Separating schemas means:
--   - ETL team writes to staging, analysts query analytics
--   - Access control can be applied per schema
--   - Staging can be truncated/replaced without affecting analytics

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;
