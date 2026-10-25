"""
tests/test_azure.py — Unit tests for src/azure_upload.py
=========================================================

Tests Azure upload module behavior when unconfigured and with missing files.
No live Azure subscription required.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.azure_upload import is_azure_configured, upload_to_adls, upload_pipeline_outputs


def test_is_azure_configured_false_by_default(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_NAME", raising=False)
    from src.config import pipeline_config
    pipeline_config.azure_conn_str = ""
    pipeline_config.azure_account = ""
    assert is_azure_configured() is False


def test_is_azure_configured_true_when_set(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https;...")
    assert is_azure_configured() is True


def test_upload_missing_file_raises(tmp_path: Path):
    fake_file = tmp_path / "does_not_exist.parquet"
    with pytest.raises(FileNotFoundError):
        upload_to_adls(fake_file, "processed/fake.parquet")


def test_upload_skips_when_unconfigured(tmp_path: Path, monkeypatch):
    test_file = tmp_path / "sample.parquet"
    test_file.write_text("dummy")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    from src.config import pipeline_config
    pipeline_config.azure_conn_str = ""
    status = upload_to_adls(test_file, "processed/sample.parquet")
    assert status is False


def test_upload_pipeline_outputs_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    from src.config import pipeline_config
    pipeline_config.azure_conn_str = ""
    pipeline_config.azure_account = ""
    res = upload_pipeline_outputs()
    assert res == {}
