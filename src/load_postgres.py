"""
src/load_postgres.py — PostgreSQL Connection and Staging Load
=============================================================

WHY THIS FILE EXISTS
--------------------
Database concerns are separated from ETL logic so that:
  - The pipeline can run locally without a PostgreSQL server
  - Integration tests can skip this module
  - Connection lifecycle is managed in one place

KEY CONCEPTS
------------
SQLAlchemy
    A Python SQL toolkit that provides a high-level ORM and a lower-level
    "Core" API for executing SQL.  We use the Core API here because we are
    dealing with bulk data loads, not ORM objects.

    SQLAlchemy is the *abstraction layer*.  It translates Python calls into
    database-specific SQL.

Psycopg 3 (psycopg)
    The actual PostgreSQL *driver* — the library that speaks the PostgreSQL
    wire protocol over TCP.  SQLAlchemy calls psycopg; you normally never
    call psycopg directly.

Why not use pandas.to_sql alone?
    pandas.to_sql works for small datasets but calls INSERT one row at a time
    by default.  We use it with method='multi' and a chunksize to batch
    INSERT statements, which is much faster for 500K rows.

STAGING STRATEGY
----------------
The staging table (stg_transactions) is fully replaced on each run
(REPLACE / DROP + RECREATE).  This is a full-refresh strategy:
  - Simple and safe for datasets of this size
  - No partial-load inconsistency
  - Idempotent: running twice produces the same result

For production at scale, an incremental (MERGE/UPSERT) strategy would be
used instead, but that requires a reliable unique key per row.

INTERVIEW TALKING POINT
-----------------------
"I used SQLAlchemy's URL builder with quote_plus to handle special characters
in passwords safely.  The password is URL-encoded before building the URL,
so a password like p@ss#word! doesn't break the connection string."
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text

from src.config import db_config, pipeline_config, ConfigError

logger = logging.getLogger(__name__)


# ── Engine factory ────────────────────────────────────────────────────────────

_engine: sa.Engine | None = None


def get_engine(db_name: str | None = None) -> sa.Engine:
    """
    Return (or create) the SQLAlchemy engine for the target database.

    The engine is cached after the first call.  This is safe because
    SQLAlchemy engines are thread-safe and hold a connection pool.

    Parameters
    ----------
    db_name : override the database name (used to connect to 'postgres'
              admin DB when creating retail_dw)
    """
    global _engine

    if db_name is not None:
        # When a custom db_name is requested, always create a fresh engine
        url = db_config.get_connection_url(db_name=db_name)
        return sa.create_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            connect_args={"connect_timeout": 10},
        )

    if _engine is None:
        db_config.validate()
        url = db_config.get_connection_url()
        _engine = sa.create_engine(
            url,
            pool_pre_ping=True,   # test connection health before use
            pool_size=5,
            max_overflow=5,
            connect_args={"connect_timeout": 10},
        )
        logger.info(
            "SQLAlchemy engine created | host=%s | port=%s | db=%s | user=%s",
            db_config.host, db_config.port, db_config.name, db_config.user,
        )

    return _engine


@contextmanager
def get_connection(db_name: str | None = None) -> Generator[sa.Connection, None, None]:
    """
    Context manager that yields a connection and ensures cleanup.
    Always use this instead of engine.connect() directly.
    """
    engine = get_engine(db_name=db_name)
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Connection diagnostics ────────────────────────────────────────────────────

class PostgreSQLConnectionError(Exception):
    """Raised with a human-readable explanation of the connection failure."""


def test_connection() -> bool:
    """
    Test the PostgreSQL connection.

    Returns True on success.
    Raises PostgreSQLConnectionError with a diagnostic message on failure.
    """
    try:
        db_config.validate()
    except ConfigError as exc:
        raise PostgreSQLConnectionError(f"Configuration problem: {exc}") from exc

    try:
        with get_connection() as conn:
            result = conn.execute(text("SELECT version()")).scalar()
            logger.info("PostgreSQL connected: %s", result)
            return True

    except sa.exc.OperationalError as exc:
        err_str = str(exc.orig) if exc.orig else str(exc)

        if "password authentication failed" in err_str:
            raise PostgreSQLConnectionError(
                f"PostgreSQL rejected the password for user '{db_config.user}'.\n"
                f"  → Verify DB_PASSWORD in your .env file.\n"
                f"  → To reset: see docs/troubleshooting.md → 'PostgreSQL password reset'\n"
                f"  (Do NOT share your password in chat)"
            ) from exc

        if "could not connect to server" in err_str or "Connection refused" in err_str:
            raise PostgreSQLConnectionError(
                f"Cannot reach PostgreSQL at {db_config.host}:{db_config.port}.\n"
                f"  → Check that the PostgreSQL service is running:\n"
                f"      Get-Service -Name postgresql*\n"
                f"      Start-Service postgresql-x64-17   # adjust name if needed"
            ) from exc

        if 'database "' in err_str and "does not exist" in err_str:
            raise PostgreSQLConnectionError(
                f"Database '{db_config.name}' does not exist.\n"
                f"  → Run: python -m src.run_pipeline --create-db\n"
                f"  → Or manually: psql -U postgres -c \"CREATE DATABASE {db_config.name};\""
            ) from exc

        raise PostgreSQLConnectionError(
            f"Unexpected PostgreSQL error: {err_str}"
        ) from exc


# ── Database and schema creation ──────────────────────────────────────────────

def create_database_if_missing() -> bool:
    """
    Connect to the 'postgres' admin database and create retail_dw if absent.

    Returns True if the database was created, False if it already existed.
    """
    target = db_config.name

    # Connect to postgres admin DB (always exists)
    # autocommit is required for CREATE DATABASE (cannot run inside a transaction)
    admin_url = db_config.get_connection_url(db_name="postgres")
    engine_admin = sa.create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 10},
    )

    with engine_admin.connect() as conn:
        exists_sql = text(
            "SELECT 1 FROM pg_database WHERE datname = :name"
        )
        exists = conn.execute(exists_sql, {"name": target}).scalar()

        if exists:
            logger.info("Database '%s' already exists.", target)
            return False

        logger.info("Creating database '%s' ...", target)
        # Cannot use parameters for identifiers — safe here because we read
        # the name from config (not from user input)
        conn.execute(text(f'CREATE DATABASE "{target}"'))
        logger.info("Database '%s' created successfully.", target)
        return True

    engine_admin.dispose()


def run_sql_file(sql_path: Path, db_name: str | None = None) -> None:
    """
    Execute a SQL script file against the target database.
    Statements are split on semicolons after stripping comments.
    """
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL script not found: {sql_path}")

    logger.info("Running SQL script: %s", sql_path.name)
    raw_sql = sql_path.read_text(encoding="utf-8")

    # Remove -- line comments
    import re
    no_comments = re.sub(r"--[^\n]*", "", raw_sql)

    # Split on semicolons
    statements = [s.strip() for s in no_comments.split(";") if s.strip()]

    with get_connection(db_name=db_name) as conn:
        for stmt in statements:
            conn.execute(text(stmt))
        conn.commit()

    logger.info("SQL script '%s' executed (%d statements).", sql_path.name, len(statements))


# ── Staging load ──────────────────────────────────────────────────────────────

STAGING_TABLE = "stg_transactions"
STAGING_SCHEMA = "staging"


def load_staging(df: pd.DataFrame) -> int:
    """
    Load the clean DataFrame into the PostgreSQL staging table.

    Strategy: FULL REPLACE
    ----------------------
    The staging table is dropped and recreated on each run.
    This is idempotent — running the pipeline twice produces the same data.

    For large production datasets, consider UPSERT / MERGE instead,
    but that requires a stable unique key (composite: invoice + stockcode + date).

    Parameters
    ----------
    df : clean validated DataFrame from validation.py

    Returns
    -------
    int : number of rows loaded
    """
    if df.empty:
        logger.warning("Empty DataFrame — nothing to load into staging.")
        return 0

    logger.info(
        "Loading %d rows into %s.%s ...",
        len(df), STAGING_SCHEMA, STAGING_TABLE,
    )

    t_start = time.perf_counter()
    engine = get_engine()

    # Prepare DataFrame for SQL: convert pandas NA types to Python None
    df_sql = _prepare_for_sql(df)

    try:
        df_sql.to_sql(
            name=STAGING_TABLE,
            schema=STAGING_SCHEMA,
            con=engine,
            if_exists="replace",   # drop + recreate = idempotent full refresh
            index=False,
            chunksize=pipeline_config.db_chunk_size,
            method="multi",        # batches multiple rows per INSERT
        )
    except Exception as exc:
        logger.error("Staging load failed: %s", exc)
        raise

    elapsed = time.perf_counter() - t_start
    n_loaded = _count_rows_in_table(STAGING_SCHEMA, STAGING_TABLE)

    logger.info(
        "Staging load complete | rows_loaded=%d | elapsed=%.1fs | rate=%.0f rows/s",
        n_loaded, elapsed, n_loaded / max(elapsed, 0.001),
    )
    return n_loaded


def _prepare_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert pandas-specific types (Int64, boolean) to Python-native types
    so psycopg can handle them.
    """
    df = df.copy()

    # Convert nullable Int64 to object (Python int or None)
    for col in df.select_dtypes(include="Int64").columns:
        df[col] = df[col].astype(object).where(df[col].notna(), None)

    # Convert bool to Python bool (psycopg handles this natively)
    for col in df.select_dtypes(include="boolean").columns:
        df[col] = df[col].astype(object).where(df[col].notna(), None)

    return df


def _count_rows_in_table(schema: str, table: str) -> int:
    """Return the row count from a database table."""
    with get_connection() as conn:
        result = conn.execute(
            text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
        ).scalar()
    return int(result or 0)


def verify_load(expected_rows: int) -> bool:
    """
    Compare expected row count to what's in the staging table.
    Returns True if they match.
    """
    actual = _count_rows_in_table(STAGING_SCHEMA, STAGING_TABLE)
    match = actual == expected_rows
    logger.info(
        "Load verification: expected=%d | actual=%d | match=%s",
        expected_rows, actual, "YES" if match else "NO",
    )
    return match


def dispose_engine() -> None:
    """Close all connections in the pool. Call at pipeline end."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("SQLAlchemy engine disposed.")
