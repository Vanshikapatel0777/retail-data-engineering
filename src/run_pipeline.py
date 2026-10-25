"""
src/run_pipeline.py — Main Pipeline Entry Point
================================================

WHY THIS FILE EXISTS
--------------------
A single entry point that orchestrates all pipeline stages in the correct order.
Running `python -m src.run_pipeline` executes the full pipeline.

WHAT THIS FILE DOES
-------------------
1. Parse command-line arguments
2. Validate configuration
3. Run each stage in order: Extract → Validate → Transform → Load → Analytics
4. Record a pipeline audit entry
5. Report final status

STAGES
------
  extract   : Read Excel → normalize headers
  transform : Validate + write Parquet + write rejected CSV
  load      : Load staging to PostgreSQL
  analytics : Execute SQL transformation scripts
  all       : Run all stages (default)

USAGE
-----
  python -m src.run_pipeline                    # full pipeline
  python -m src.run_pipeline --stage etl        # extract + transform only
  python -m src.run_pipeline --stage load       # load PostgreSQL only
  python -m src.run_pipeline --create-db        # create retail_dw database

ENVIRONMENT
-----------
  LOCAL_ONLY=true  → skip PostgreSQL and cloud; only produce local files
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Import pipeline modules ────────────────────────────────────────────────────
# config.py configures logging at import time — import first
from src.config import db_config, pipeline_config, ConfigError, PROJECT_ROOT

logger = logging.getLogger(__name__)


# ── Audit record ──────────────────────────────────────────────────────────────

def _make_audit(run_id: str) -> dict:
    """Create an empty audit skeleton."""
    return {
        "run_id": run_id,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "source_file": str(pipeline_config.raw_file),
        "source_row_count": 0,
        "clean_row_count": 0,
        "rejected_row_count": 0,
        "duplicate_count": 0,
        "loaded_row_count": 0,
        "status": "RUNNING",
        "error_summary": None,
        "local_only": pipeline_config.local_only,
        "stages_completed": [],
    }


def _save_audit(audit: dict) -> None:
    """Write the audit record to logs/audit_runs.jsonl (appended)."""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_file = log_dir / "audit_runs.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit) + "\n")
    logger.info("Audit record saved → %s", audit_file.name)


# ── Stage functions ────────────────────────────────────────────────────────────

def stage_extract(audit: dict) -> "pd.DataFrame":  # noqa: F821
    """Extract: Read Excel → return normalized DataFrame."""
    import pandas as pd
    from src.etl import extract

    logger.info("=" * 60)
    logger.info("STAGE: EXTRACT")
    logger.info("=" * 60)

    result = extract(pipeline_config.raw_file)
    audit["source_file"] = result.source_file
    audit["source_row_count"] = result.source_row_count
    audit["sheets_loaded"] = result.sheets_loaded

    if result.warnings:
        logger.warning("Extract warnings: %s", result.warnings)

    logger.info(
        "Extract complete: %d rows from sheets %s",
        result.source_row_count, result.sheets_loaded,
    )
    audit["stages_completed"].append("extract")
    return result.df


def stage_validate_transform(df: "pd.DataFrame", audit: dict) -> tuple:  # noqa: F821
    """Validate DataFrame and write Parquet + rejected CSV."""
    from src.validation import validate_dataframe
    from src.transform import write_parquet, write_rejected_csv, verify_parquet_roundtrip

    logger.info("=" * 60)
    logger.info("STAGE: VALIDATE + TRANSFORM")
    logger.info("=" * 60)

    pipeline_config.validate()  # ensure output dirs exist

    val_result = validate_dataframe(df)

    audit["clean_row_count"] = val_result.clean_count
    audit["rejected_row_count"] = val_result.rejected_count
    audit["duplicate_count"] = val_result.duplicate_count

    # Reconciliation check
    total = audit["source_row_count"]
    expected = val_result.clean_count + val_result.rejected_count
    if total != expected:
        logger.warning(
            "Reconciliation mismatch: source=%d, clean+rejected=%d",
            total, expected,
        )

    # Write Parquet
    write_parquet(val_result.clean, pipeline_config.clean_parquet)

    # Verify roundtrip
    roundtrip_ok = verify_parquet_roundtrip(val_result.clean, pipeline_config.clean_parquet)
    if not roundtrip_ok:
        logger.error("Parquet roundtrip verification FAILED")

    # Write rejected CSV
    write_rejected_csv(val_result.rejected, pipeline_config.rejected_csv)

    logger.info(
        "Transform complete: clean=%d | rejected=%d | duplicates=%d",
        val_result.clean_count, val_result.rejected_count, val_result.duplicate_count,
    )
    audit["stages_completed"].append("validate_transform")
    return val_result.clean, val_result.rejected


def stage_load_postgres(clean_df: "pd.DataFrame", audit: dict) -> None:  # noqa: F821
    """Load clean DataFrame into PostgreSQL staging table."""
    from src.load_postgres import (
        create_database_if_missing,
        test_connection,
        load_staging,
        run_sql_file,
        PostgreSQLConnectionError,
    )

    logger.info("=" * 60)
    logger.info("STAGE: LOAD POSTGRESQL")
    logger.info("=" * 60)

    try:
        db_config.validate()
    except ConfigError as exc:
        logger.error("DB config invalid: %s", exc)
        raise

    # Ensure database exists
    try:
        create_database_if_missing()
    except Exception as exc:
        logger.error("Failed to ensure database exists: %s", exc)
        raise

    # Run schema creation scripts
    sql_dir = pipeline_config.sql_dir
    for script_name in ["01_create_schema.sql", "02_create_staging.sql"]:
        script_path = sql_dir / script_name
        if script_path.exists():
            run_sql_file(script_path)
        else:
            logger.warning("SQL script not found: %s — skipping", script_name)

    # Test connection
    try:
        test_connection()
    except PostgreSQLConnectionError as exc:
        logger.error("PostgreSQL connection test failed: %s", exc)
        raise

    # Load staging
    n_loaded = load_staging(clean_df)
    audit["loaded_row_count"] = n_loaded

    logger.info("PostgreSQL load complete: %d rows loaded.", n_loaded)
    audit["stages_completed"].append("load_postgres")


def stage_sql_analytics(audit: dict) -> None:
    """Execute SQL transformation and analytics scripts."""
    from src.load_postgres import run_sql_file

    logger.info("=" * 60)
    logger.info("STAGE: SQL ANALYTICS")
    logger.info("=" * 60)

    sql_dir = pipeline_config.sql_dir
    analytics_scripts = [
        "03_transform_sales.sql",
        "04_analytics_views.sql",
        "05_quality_checks.sql",
    ]

    for script_name in analytics_scripts:
        script_path = sql_dir / script_name
        if script_path.exists():
            try:
                run_sql_file(script_path)
                logger.info("SQL script executed: %s", script_name)
            except Exception as exc:
                logger.error("SQL script failed: %s — %s", script_name, exc)
                raise
        else:
            logger.warning("SQL script not found: %s — skipping", script_name)

    audit["stages_completed"].append("sql_analytics")


def stage_quality_checks(audit: dict) -> None:
    """Run post-load data quality checks."""
    from src.reporting import run_quality_report

    logger.info("=" * 60)
    logger.info("STAGE: QUALITY CHECKS")
    logger.info("=" * 60)

    try:
        run_quality_report()
        audit["stages_completed"].append("quality_checks")
    except Exception as exc:
        logger.error("Quality check stage failed: %s", exc)
        raise


# ── Create database helper ─────────────────────────────────────────────────────

def create_database() -> None:
    """Create the retail_dw database using admin connection."""
    from src.load_postgres import create_database_if_missing

    try:
        db_config.validate()
    except ConfigError as exc:
        logger.error("Cannot create database — config problem: %s", exc)
        sys.exit(1)

    logger.info("Checking / creating database '%s' ...", db_config.name)
    created = create_database_if_missing()
    if created:
        print(f"✅ Database '{db_config.name}' created successfully.")
    else:
        print(f"ℹ️  Database '{db_config.name}' already exists.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """
    Main pipeline entry point.

    Returns exit code: 0 = success, 1 = failure.
    """
    parser = argparse.ArgumentParser(
        description="Retail Data Engineering Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--stage",
        choices=["all", "extract", "etl", "load", "analytics"],
        default="all",
        help=(
            "Which stage to run: "
            "'all' (default) runs the full pipeline; "
            "'etl' runs extract+validate+transform only; "
            "'load' runs PostgreSQL load only (reads Parquet); "
            "'analytics' runs SQL scripts only."
        ),
    )
    parser.add_argument(
        "--create-db",
        action="store_true",
        help="Create the retail_dw database (connects to postgres admin DB first).",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Override LOCAL_ONLY=true even if not set in .env.",
    )
    parser.add_argument(
        "--upload-azure",
        action="store_true",
        help="Upload processed Parquet files to Azure ADLS Gen2 (requires Azure credentials).",
    )
    args = parser.parse_args(argv)

    # Override local_only from CLI flag
    if args.local_only:
        pipeline_config.local_only = True

    # Special action: create database
    if args.create_db:
        create_database()
        return 0

    run_id = str(uuid.uuid4())[:8]
    audit = _make_audit(run_id)
    t_pipeline_start = time.perf_counter()

    logger.info("=" * 60)
    logger.info("PIPELINE START | run_id=%s | stage=%s | local_only=%s",
                run_id, args.stage, pipeline_config.local_only)
    logger.info("=" * 60)

    clean_df = None

    try:
        # ── EXTRACT ───────────────────────────────────────────────────────────
        if args.stage in ("all", "extract", "etl"):
            raw_df = stage_extract(audit)

            # ── VALIDATE + TRANSFORM ──────────────────────────────────────────
            clean_df, rejected_df = stage_validate_transform(raw_df, audit)

        elif args.stage in ("load", "analytics"):
            # Read Parquet if skipping extract
            if not pipeline_config.clean_parquet.exists():
                logger.error(
                    "Parquet not found: %s\n"
                    "Run 'python -m src.run_pipeline --stage etl' first.",
                    pipeline_config.clean_parquet,
                )
                raise FileNotFoundError(
                    f"Parquet not found: {pipeline_config.clean_parquet}"
                )
            from src.transform import read_parquet
            clean_df = read_parquet(pipeline_config.clean_parquet)
            audit["clean_row_count"] = len(clean_df)
            logger.info("Loaded %d rows from existing Parquet.", len(clean_df))

        # ── LOAD POSTGRESQL ───────────────────────────────────────────────────
        if args.stage in ("all", "load") and not pipeline_config.local_only:
            stage_load_postgres(clean_df, audit)

            # ── SQL ANALYTICS ─────────────────────────────────────────────────
            stage_sql_analytics(audit)

            # ── QUALITY CHECKS ────────────────────────────────────────────────
            try:
                stage_quality_checks(audit)
            except Exception as exc:
                logger.warning("Quality checks failed (non-fatal): %s", exc)

        elif pipeline_config.local_only and args.stage == "all":
            logger.info(
                "LOCAL_ONLY mode — skipping PostgreSQL load and SQL analytics."
            )
            logger.info(
                "Clean Parquet written to: %s", pipeline_config.clean_parquet
            )
            logger.info(
                "Rejected CSV written to: %s", pipeline_config.rejected_csv
            )

        elif args.stage == "analytics":
            stage_sql_analytics(audit)

        # ── OPTIONAL AZURE CLOUD UPLOAD ─────────────────────────────────────────
        if args.upload_azure or pipeline_config.azure_enabled:
            logger.info("=" * 60)
            logger.info("STAGE: AZURE CLOUD UPLOAD")
            logger.info("=" * 60)
            from src.azure_upload import upload_pipeline_outputs
            upload_results = upload_pipeline_outputs()
            audit["azure_uploads"] = upload_results
            audit["stages_completed"].append("azure_upload")

        # ── SUCCESS ────────────────────────────────────────────────────────────
        elapsed = time.perf_counter() - t_pipeline_start
        audit["status"] = "SUCCESS"
        audit["end_time"] = datetime.now(timezone.utc).isoformat()

        logger.info("=" * 60)
        logger.info(
            "PIPELINE COMPLETE | run_id=%s | elapsed=%.1fs | status=SUCCESS",
            run_id, elapsed,
        )
        logger.info("  source_rows  : %d", audit["source_row_count"])
        logger.info("  clean_rows   : %d", audit["clean_row_count"])
        logger.info("  rejected_rows: %d", audit["rejected_row_count"])
        logger.info("  duplicates   : %d", audit["duplicate_count"])
        logger.info("  loaded_rows  : %d", audit["loaded_row_count"])
        logger.info("=" * 60)

        _save_audit(audit)
        return 0

    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        audit["status"] = "FAILED"
        audit["error_summary"] = str(exc)
        audit["end_time"] = datetime.now(timezone.utc).isoformat()
        _save_audit(audit)
        return 1

    except Exception as exc:
        logger.exception("Pipeline FAILED: %s", exc)
        audit["status"] = "FAILED"
        audit["error_summary"] = f"{type(exc).__name__}: {exc}"
        audit["end_time"] = datetime.now(timezone.utc).isoformat()
        _save_audit(audit)
        return 1

    finally:
        # Always close DB connections
        try:
            from src.load_postgres import dispose_engine
            dispose_engine()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
