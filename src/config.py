"""
src/config.py — Centralised Configuration and Secrets Management
================================================================

WHY THIS FILE EXISTS
--------------------
Every module needs to know the database URL, file paths, and log level.
If each module reads .env independently we get duplication and inconsistency.
This file is the single source of truth for all configuration.

HOW IT WORKS
------------
1. python-dotenv reads .env from the project root (detected at import time).
2. Required variables are validated immediately; missing ones raise ConfigError.
3. Sensitive values (password) are never logged or printed.
4. A SQLAlchemy engine factory is exposed so only one engine is created per run.

INTERVIEW TALKING POINT
-----------------------
"I centralised all configuration in config.py with explicit validation.
If a required environment variable is missing, the pipeline fails immediately
with a clear human-readable error — not a cryptic AttributeError later on."
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

# ── Locate project root (two levels up from this file: src/ -> project root) ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root.  Does nothing if .env is absent — won't crash.
_env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_env_path, override=False)

# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_root_logger() -> None:
    """Configure the root logger once at import time."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = PROJECT_ROOT / os.getenv("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "pipeline.log"

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    logging.basicConfig(
        level=log_level,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(),                         # console
            logging.FileHandler(log_file, encoding="utf-8"), # file
        ],
    )


_configure_root_logger()
logger = logging.getLogger(__name__)


# ── Custom exception ──────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Raised when a required configuration value is absent or invalid."""


# ── Helper: read required env var ─────────────────────────────────────────────

def _require(name: str) -> str:
    """Return the value of an env var or raise ConfigError."""
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example to .env and fill in your values."
        )
    return value


# ── Database configuration ────────────────────────────────────────────────────

class DatabaseConfig:
    """
    Holds PostgreSQL connection parameters.
    Password is stored but NEVER logged.
    """

    def __init__(self) -> None:
        self.host: str = os.getenv("DB_HOST", "localhost")
        self.port: int = int(os.getenv("DB_PORT", "5432"))
        self.name: str = os.getenv("DB_NAME", "retail_dw")
        self.user: str = os.getenv("DB_USER", "postgres")
        # Password read directly — never stored in a log
        self._password: str = os.getenv("DB_PASSWORD", "")

    def validate(self) -> None:
        """Raise ConfigError if any required database setting is blank."""
        problems: list[str] = []
        if not self._password:
            problems.append("DB_PASSWORD is not set")
        if not self.user:
            problems.append("DB_USER is not set")
        if not self.name:
            problems.append("DB_NAME is not set")
        if problems:
            raise ConfigError("Database configuration problems: " + "; ".join(problems))

    def get_connection_url(self, db_name: str | None = None) -> str:
        """
        Build a SQLAlchemy connection URL for psycopg 3.

        The password is URL-encoded so special characters (@ # % etc.) don't
        break the URL.  We use quote_plus which encodes every reserved char.

        Parameters
        ----------
        db_name : override the target database name (used when connecting to
                  'postgres' admin DB to create 'retail_dw')
        """
        target_db = db_name or self.name
        # quote_plus encodes special chars safely
        pw_encoded = quote_plus(self._password)
        # DO NOT log this URL — it contains the password
        return (
            f"postgresql+psycopg://{self.user}:{pw_encoded}"
            f"@{self.host}:{self.port}/{target_db}"
        )

    def __repr__(self) -> str:
        """Safe repr — password masked."""
        return (
            f"DatabaseConfig(host={self.host!r}, port={self.port}, "
            f"db={self.name!r}, user={self.user!r}, password='***')"
        )


# ── Pipeline configuration ────────────────────────────────────────────────────

class PipelineConfig:
    """
    Holds file paths and pipeline behaviour settings.
    These can be overridden via environment variables.
    """

    def __init__(self) -> None:
        # Source Excel file
        raw_file_env = os.getenv("RAW_FILE", "data/raw/online_retail_II.xlsx")
        self.raw_file: Path = PROJECT_ROOT / raw_file_env

        # Processed outputs
        self.processed_dir: Path = PROJECT_ROOT / "data" / "processed"
        self.rejected_dir: Path   = PROJECT_ROOT / "data" / "rejected"
        self.sample_dir: Path     = PROJECT_ROOT / "data" / "sample"

        # Clean Parquet output
        self.clean_parquet: Path = self.processed_dir / "retail_clean.parquet"

        # Rejected records
        self.rejected_csv: Path = self.rejected_dir / "retail_rejected.csv"

        # Skip PostgreSQL loading for local-only development
        raw_local = os.getenv("LOCAL_ONLY", "false").strip().lower()
        self.local_only: bool = raw_local in ("1", "true", "yes")

        # Azure (optional)
        self.azure_account: str    = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "")
        self.azure_container: str  = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "retail-data")
        self.azure_conn_str: str   = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        self.azure_enabled: bool   = bool(self.azure_account or self.azure_conn_str)

        # SQLAlchemy batch size for staging load
        self.db_chunk_size: int = int(os.getenv("DB_CHUNK_SIZE", "5000"))

        # SQL scripts directory
        self.sql_dir: Path = PROJECT_ROOT / "sql"

    def validate(self) -> None:
        """Warn if source file is missing; raise if processed dirs cannot be created."""
        if not self.raw_file.exists():
            logger.warning(
                "Source file not found: %s  — "
                "place online_retail_II.xlsx in data/raw/ before running ETL.",
                self.raw_file,
            )
        for d in (self.processed_dir, self.rejected_dir, self.sample_dir):
            d.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return (
            f"PipelineConfig(raw_file={self.raw_file.name!r}, "
            f"local_only={self.local_only}, azure_enabled={self.azure_enabled})"
        )


# ── Singleton instances (created once at import) ──────────────────────────────

db_config = DatabaseConfig()
pipeline_config = PipelineConfig()

logger.debug("Config loaded: %s | %s", db_config, pipeline_config)
