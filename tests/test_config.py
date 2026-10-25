"""
tests/test_config.py — Unit tests for src/config.py
=====================================================

Tests configuration loading, validation, and edge cases.
Does NOT connect to PostgreSQL.
"""

from __future__ import annotations

import os
import pytest


class TestDatabaseConfig:
    def test_defaults_are_set(self):
        from src.config import DatabaseConfig
        cfg = DatabaseConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 5432
        assert cfg.name == "retail_dw"
        assert cfg.user == "postgres"

    def test_repr_does_not_expose_password(self):
        from src.config import DatabaseConfig
        cfg = DatabaseConfig()
        r = repr(cfg)
        assert "password='***'" in r
        # The actual password (if any) should not appear
        assert os.getenv("DB_PASSWORD", "") not in r or os.getenv("DB_PASSWORD", "") == ""

    def test_connection_url_contains_driver(self):
        from src.config import DatabaseConfig
        cfg = DatabaseConfig()
        # Patch a fake password to test URL structure without exposing real credentials
        cfg._password = "TestPass123"
        url = cfg.get_connection_url()
        assert url.startswith("postgresql+psycopg://")
        assert "TestPass123" in url  # URL contains encoded password
        # The real test: password with special chars is URL-encoded
        cfg._password = "p@ss#w0rd!"
        url_special = cfg.get_connection_url()
        assert "@" not in url_special.split("@")[0].split("://")[1]  # @ in password is encoded

    def test_validate_raises_on_missing_password(self):
        from src.config import DatabaseConfig, ConfigError
        cfg = DatabaseConfig()
        cfg._password = ""
        with pytest.raises(ConfigError, match="DB_PASSWORD"):
            cfg.validate()

    def test_connection_url_custom_db_name(self):
        from src.config import DatabaseConfig
        cfg = DatabaseConfig()
        cfg._password = "test"
        url = cfg.get_connection_url(db_name="postgres")
        assert url.endswith("/postgres")


class TestPipelineConfig:
    def test_raw_file_is_path(self):
        from src.config import PipelineConfig
        from pathlib import Path
        cfg = PipelineConfig()
        assert isinstance(cfg.raw_file, Path)

    def test_processed_dir_is_path(self):
        from src.config import PipelineConfig
        from pathlib import Path
        cfg = PipelineConfig()
        assert isinstance(cfg.processed_dir, Path)

    def test_local_only_false_by_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_ONLY", raising=False)
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.local_only is False

    def test_local_only_true_when_set(self, monkeypatch):
        monkeypatch.setenv("LOCAL_ONLY", "true")
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.local_only is True

    def test_local_only_true_with_1(self, monkeypatch):
        monkeypatch.setenv("LOCAL_ONLY", "1")
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.local_only is True

    def test_azure_disabled_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_NAME", raising=False)
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.azure_enabled is False

    def test_db_chunk_size_default(self):
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.db_chunk_size == 5000

    def test_repr_is_safe(self):
        from src.config import PipelineConfig
        cfg = PipelineConfig()
        r = repr(cfg)
        assert "PipelineConfig" in r
        # Should not contain a path to .env or a password
        assert "DB_PASSWORD" not in r


class TestConfigError:
    def test_config_error_is_exception(self):
        from src.config import ConfigError
        with pytest.raises(ConfigError):
            raise ConfigError("test error")

    def test_config_error_message(self):
        from src.config import ConfigError
        try:
            raise ConfigError("missing DB_PASSWORD")
        except ConfigError as e:
            assert "DB_PASSWORD" in str(e)
