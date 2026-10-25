"""
Retail Data Engineering Pipeline — Source Package

This package contains all ETL logic, configuration, validation,
database loading, and reporting modules.

Import hierarchy (no circular imports):
    config  <- base (no internal deps)
    validation <- pandas only
    etl     <- config, validation
    transform <- config
    load_postgres <- config
    transform_sql <- config, load_postgres
    reporting <- config, load_postgres
    run_pipeline <- etl, transform, load_postgres, transform_sql, reporting
"""
