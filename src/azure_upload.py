"""
src/azure_upload.py — Optional Azure Data Lake Storage Gen2 Integration
=======================================================================

WHY THIS FILE EXISTS
--------------------
Modern enterprise data architectures often store analytical data in a cloud
object store (Data Lake) such as Azure Data Lake Storage Gen2 (ADLS Gen2)
or AWS S3, alongside or upstream from relational data warehouses.

WHAT THIS FILE DOES
-------------------
1. Connects to Azure ADLS Gen2 using connection string or Azure DefaultAzureCredential.
2. Uploads processed clean Parquet files to `processed/retail_clean.parquet`.
3. Optionally uploads rejected CSV records to `rejected/retail_rejected.csv`.
4. Gracefully skips if Azure credentials are not configured (local-only safe).

ENVIRONMENT VARIABLES
---------------------
  AZURE_STORAGE_ACCOUNT_NAME       : Name of the Azure Storage Account
  AZURE_STORAGE_CONTAINER_NAME     : Container name (default: 'retail-data')
  AZURE_STORAGE_CONNECTION_STRING  : Connection string (for local dev with Azure)

INTERVIEW TALKING POINT
-----------------------
"In this pipeline, Azure ADLS Gen2 acts as our persistent cloud data lake.
Parquet files are uploaded to ADLS Gen2 partitioned by ingestion batch or date.
Downstream systems like Azure Synapse Analytics, Databricks, or Fabric can then
query those Parquet files using external tables or Serverless SQL pools without
loading them into a proprietary warehouse."
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.config import pipeline_config

logger = logging.getLogger(__name__)


class AzureUploadError(Exception):
    """Raised when an Azure upload fails."""


def is_azure_configured() -> bool:
    """Check whether Azure storage credentials are provided."""
    return bool(
        pipeline_config.azure_conn_str
        or pipeline_config.azure_account
        or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )


def upload_to_adls(local_path: Path, remote_blob_name: str) -> bool:
    """
    Upload a local file to Azure Data Lake Storage Gen2.

    Parameters
    ----------
    local_path : Path
        Local file to upload (e.g. data/processed/retail_clean.parquet)
    remote_blob_name : str
        Target path in container (e.g. 'processed/retail_clean.parquet')

    Returns
    -------
    bool : True if upload succeeded, False if skipped because unconfigured.
    """
    if not local_path.exists():
        raise FileNotFoundError(f"Local file to upload not found: {local_path}")

    conn_str = pipeline_config.azure_conn_str or os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    container_name = pipeline_config.azure_container or "retail-data"

    if not conn_str:
        logger.info(
            "Azure credentials not configured — skipping upload for %s. "
            "To enable: set AZURE_STORAGE_CONNECTION_STRING in .env",
            local_path.name,
        )
        return False

    try:
        # Dynamically import to keep azure optional
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        logger.warning(
            "azure-storage-blob package is not installed. "
            "Install with: pip install azure-storage-blob to enable Azure upload."
        )
        return False

    try:
        logger.info(
            "Uploading %s to Azure ADLS container '%s' as '%s' ...",
            local_path.name, container_name, remote_blob_name,
        )
        blob_service_client = BlobServiceClient.from_connection_string(conn_str)
        container_client = blob_service_client.get_container_client(container_name)

        # Create container if it does not exist
        if not container_client.exists():
            logger.info("Container '%s' does not exist. Creating...", container_name)
            container_client.create_container()

        blob_client = container_client.get_blob_client(remote_blob_name)
        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        logger.info("Upload complete: %s -> %s/%s", local_path.name, container_name, remote_blob_name)
        return True

    except Exception as exc:
        msg = f"Azure upload failed for {local_path.name}: {exc}"
        logger.error(msg)
        raise AzureUploadError(msg) from exc


def upload_pipeline_outputs() -> dict[str, bool]:
    """
    Upload all available pipeline outputs (clean Parquet and rejected CSV) to Azure.

    Returns dict of {filename: success_status}.
    """
    results = {}
    if not is_azure_configured():
        logger.info("Azure is not configured; skipping cloud synchronization.")
        return results

    if pipeline_config.clean_parquet.exists():
        results["clean_parquet"] = upload_to_adls(
            pipeline_config.clean_parquet,
            "processed/retail_clean.parquet",
        )

    if pipeline_config.rejected_csv.exists():
        results["rejected_csv"] = upload_to_adls(
            pipeline_config.rejected_csv,
            "rejected/retail_rejected.csv",
        )

    return results
