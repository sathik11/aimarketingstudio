"""
Sync SQLite DB and generated_audio to Azure Blob Storage.
On startup: download DB + audio from blob if they exist.
After writes: upload DB back to blob.
"""

import os
import logging
import threading
import time

from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError

from config import (
    AZURE_STORAGE_ACCOUNT_URL,
    AZURE_STORAGE_CONTAINER_NAME,
    DB_PATH,
    AUDIO_OUTPUT_DIR,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

BLOB_DB_NAME = "appdata/tts.db"
BLOB_AUDIO_PREFIX = "appdata/audio/"
BLOB_VIDEO_PREFIX = "appdata/video/"

_credential = None
_lock = threading.Lock()
_last_sync = 0
_SYNC_DEBOUNCE_SECS = 5  # Don't sync more than once every 5 seconds


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _get_container_client():
    if not AZURE_STORAGE_ACCOUNT_URL or not AZURE_STORAGE_CONTAINER_NAME:
        return None
    client = BlobServiceClient(
        account_url=AZURE_STORAGE_ACCOUNT_URL,
        credential=_get_credential(),
    )
    return client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)


def download_db_from_blob():
    """Download DB from blob storage on startup. Returns True if downloaded."""
    container = _get_container_client()
    if not container:
        logger.info("Blob sync disabled: no storage config")
        return False

    try:
        blob_client = container.get_blob_client(BLOB_DB_NAME)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DB_PATH, "wb") as f:
            stream = blob_client.download_blob()
            stream.readinto(f)
        logger.info(f"Downloaded DB from blob ({BLOB_DB_NAME})")
        return True
    except ResourceNotFoundError:
        logger.info("No DB found in blob storage, starting fresh")
        return False
    except Exception as e:
        logger.warning(f"Failed to download DB from blob: {e}")
        return False


def upload_db_to_blob():
    """Upload current DB to blob storage. Debounced to avoid excessive writes."""
    global _last_sync
    now = time.time()
    if now - _last_sync < _SYNC_DEBOUNCE_SECS:
        return

    container = _get_container_client()
    if not container:
        return

    def _do_upload():
        global _last_sync
        with _lock:
            try:
                if not os.path.exists(DB_PATH):
                    return
                blob_client = container.get_blob_client(BLOB_DB_NAME)
                with open(DB_PATH, "rb") as f:
                    blob_client.upload_blob(f, overwrite=True)
                _last_sync = time.time()
                logger.debug("Synced DB to blob")
            except Exception as e:
                logger.warning(f"Failed to sync DB to blob: {e}")

    # Run upload in background thread to not block API responses
    threading.Thread(target=_do_upload, daemon=True).start()


def download_audio_from_blob():
    """Download all audio files from blob on startup."""
    container = _get_container_client()
    if not container:
        return

    try:
        os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
        count = 0
        for blob in container.list_blobs(name_starts_with=BLOB_AUDIO_PREFIX):
            filename = blob.name[len(BLOB_AUDIO_PREFIX):]
            if not filename:
                continue
            local_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
            if os.path.exists(local_path):
                continue
            blob_client = container.get_blob_client(blob.name)
            with open(local_path, "wb") as f:
                stream = blob_client.download_blob()
                stream.readinto(f)
            count += 1
        if count:
            logger.info(f"Downloaded {count} audio files from blob")
    except Exception as e:
        logger.warning(f"Failed to download audio from blob: {e}")


def upload_audio_file_to_blob(filename: str):
    """Upload a single audio file to blob storage."""
    container = _get_container_client()
    if not container:
        return

    def _do_upload():
        try:
            local_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
            if not os.path.exists(local_path):
                return
            blob_name = BLOB_AUDIO_PREFIX + filename
            blob_client = container.get_blob_client(blob_name)
            with open(local_path, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            logger.debug(f"Uploaded audio {filename} to blob")
        except Exception as e:
            logger.warning(f"Failed to upload audio {filename}: {e}")

    threading.Thread(target=_do_upload, daemon=True).start()


def restore_from_blob():
    """Full restore on startup: DB first, then audio."""
    download_db_from_blob()
    download_audio_from_blob()
