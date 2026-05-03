"""
Blob sync for persistent storage across container restarts.

Strategy:
- DB: Download on startup, upload after every mutating request (debounced).
- Audio (TTS generations): Upload after generation, download on-demand when served.
  Cleanup: keep only last N per script (default 20). SSML playground audio is NOT synced.
- Video: Upload after generation (background). Download on-demand when user views project.
  NOT downloaded on startup to keep app start fast.
- Avatars: Upload after generation. Download on-demand when served.
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
    VIDEO_OUTPUT_DIR,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

BLOB_DB_NAME = "appdata/tts.db"
BLOB_AUDIO_PREFIX = "appdata/audio/"
BLOB_VIDEO_PREFIX = "appdata/video/"
BLOB_AVATAR_PREFIX = "appdata/avatars/"

AUDIO_MAX_PER_SCRIPT = 20  # Keep last N audio files per script in blob

_credential = None
_lock = threading.Lock()
_last_sync = 0
_SYNC_DEBOUNCE_SECS = 5
_blob_auth_failed = False


def _is_blob_auth_error(err: Exception) -> bool:
    msg = str(err)
    markers = [
        "AuthorizationFailure",
        "AuthorizationPermissionMismatch",
        "AuthenticationFailed",
        "This request is not authorized to perform this operation",
    ]
    return any(m in msg for m in markers)


def _handle_blob_error(action: str, err: Exception) -> bool:
    """Return True if the error was handled and should not be re-logged."""
    global _blob_auth_failed
    if _is_blob_auth_error(err):
        if not _blob_auth_failed:
            logger.warning(
                "Blob sync disabled for this process after auth failure during %s. "
                "Grant 'Storage Blob Data Contributor' to the runtime identity on the storage account/container.",
                action,
            )
        _blob_auth_failed = True
        return True
    return False


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _get_container_client():
    if _blob_auth_failed:
        return None
    if not AZURE_STORAGE_ACCOUNT_URL or not AZURE_STORAGE_CONTAINER_NAME:
        return None
    client = BlobServiceClient(
        account_url=AZURE_STORAGE_ACCOUNT_URL,
        credential=_get_credential(),
    )
    return client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)


# ── DB sync ──────────────────────────────────────────────────────────

def download_db_from_blob():
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
        if _handle_blob_error("download DB", e):
            return False
        logger.warning(f"Failed to download DB from blob: {e}")
        return False


def upload_db_to_blob():
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
                if _handle_blob_error("upload DB", e):
                    return
                logger.warning(f"Failed to sync DB to blob: {e}")

    threading.Thread(target=_do_upload, daemon=True).start()


def force_upload_db_to_blob():
    """Synchronous, non-debounced DB upload — called on shutdown."""
    container = _get_container_client()
    if not container:
        return
    with _lock:
        try:
            if not os.path.exists(DB_PATH):
                return
            blob_client = container.get_blob_client(BLOB_DB_NAME)
            with open(DB_PATH, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            logger.info("Force-synced DB to blob on shutdown")
        except Exception as e:
            if _handle_blob_error("force upload DB", e):
                return
            logger.warning(f"Failed to force-sync DB to blob: {e}")


# ── Audio sync ───────────────────────────────────────────────────────

def upload_audio_file_to_blob(filename: str):
    """Upload a single audio file to blob (background thread)."""
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
            if _handle_blob_error("upload audio", e):
                return
            logger.warning(f"Failed to upload audio {filename}: {e}")

    threading.Thread(target=_do_upload, daemon=True).start()


def download_audio_file_on_demand(filename: str) -> bool:
    """Download a single audio file from blob if not available locally. Returns True if file exists after call."""
    local_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
    if os.path.exists(local_path):
        return True

    container = _get_container_client()
    if not container:
        return False

    try:
        os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
        blob_name = BLOB_AUDIO_PREFIX + filename
        blob_client = container.get_blob_client(blob_name)
        with open(local_path, "wb") as f:
            stream = blob_client.download_blob()
            stream.readinto(f)
        logger.debug(f"On-demand downloaded audio {filename}")
        return True
    except ResourceNotFoundError:
        return False
    except Exception as e:
        if _handle_blob_error("download audio", e):
            return False
        logger.warning(f"Failed to download audio {filename}: {e}")
        return False


def cleanup_old_audio_blobs(script_id: int):
    """Delete audio blobs exceeding AUDIO_MAX_PER_SCRIPT for a given script.
    Called after recording a new generation."""
    container = _get_container_client()
    if not container:
        return

    def _do_cleanup():
        try:
            from db import _get_conn
            conn = _get_conn()
            rows = conn.execute(
                "SELECT audio_file FROM generations WHERE script_id = ? AND audio_file IS NOT NULL "
                "ORDER BY created_at DESC",
                (script_id,),
            ).fetchall()
            conn.close()

            if len(rows) <= AUDIO_MAX_PER_SCRIPT:
                return

            old_files = [r["audio_file"] for r in rows[AUDIO_MAX_PER_SCRIPT:]]
            for filename in old_files:
                try:
                    blob_name = BLOB_AUDIO_PREFIX + filename
                    container.get_blob_client(blob_name).delete_blob()
                    # Also remove local copy
                    local_path = os.path.join(AUDIO_OUTPUT_DIR, filename)
                    if os.path.exists(local_path):
                        os.unlink(local_path)
                    logger.debug(f"Cleaned up old audio: {filename}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Audio cleanup failed for script {script_id}: {e}")

    threading.Thread(target=_do_cleanup, daemon=True).start()


# ── Video sync ───────────────────────────────────────────────────────

def upload_video_file_to_blob(filename: str):
    """Upload a video file to blob (background thread)."""
    container = _get_container_client()
    if not container:
        return

    def _do_upload():
        try:
            local_path = os.path.join(VIDEO_OUTPUT_DIR, filename)
            if not os.path.exists(local_path):
                return
            blob_name = BLOB_VIDEO_PREFIX + filename
            blob_client = container.get_blob_client(blob_name)
            with open(local_path, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            logger.debug(f"Uploaded video {filename} to blob")
        except Exception as e:
            if _handle_blob_error("upload video", e):
                return
            logger.warning(f"Failed to upload video {filename}: {e}")

    threading.Thread(target=_do_upload, daemon=True).start()


def download_video_file_on_demand(filename: str) -> bool:
    """Download a single video file from blob if not locally available."""
    local_path = os.path.join(VIDEO_OUTPUT_DIR, filename)
    if os.path.exists(local_path):
        return True

    container = _get_container_client()
    if not container:
        return False

    try:
        os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
        blob_name = BLOB_VIDEO_PREFIX + filename
        blob_client = container.get_blob_client(blob_name)
        with open(local_path, "wb") as f:
            stream = blob_client.download_blob()
            stream.readinto(f)
        logger.debug(f"On-demand downloaded video {filename}")
        return True
    except ResourceNotFoundError:
        return False
    except Exception as e:
        if _handle_blob_error("download video", e):
            return False
        logger.warning(f"Failed to download video {filename}: {e}")
        return False


# ── Avatar sync ──────────────────────────────────────────────────────

def upload_avatar_file_to_blob(filename: str):
    """Upload an avatar image to blob (background thread)."""
    from services.image_gen import AVATAR_DIR

    container = _get_container_client()
    if not container:
        return

    def _do_upload():
        try:
            local_path = os.path.join(AVATAR_DIR, filename)
            if not os.path.exists(local_path):
                return
            blob_name = BLOB_AVATAR_PREFIX + filename
            blob_client = container.get_blob_client(blob_name)
            with open(local_path, "rb") as f:
                blob_client.upload_blob(f, overwrite=True)
            logger.debug(f"Uploaded avatar {filename} to blob")
        except Exception as e:
            if _handle_blob_error("upload avatar", e):
                return
            logger.warning(f"Failed to upload avatar {filename}: {e}")

    threading.Thread(target=_do_upload, daemon=True).start()


def download_avatar_file_on_demand(filename: str) -> bool:
    """Download a single avatar image from blob if not locally available."""
    from services.image_gen import AVATAR_DIR

    local_path = os.path.join(AVATAR_DIR, filename)
    if os.path.exists(local_path):
        return True

    container = _get_container_client()
    if not container:
        return False

    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        blob_name = BLOB_AVATAR_PREFIX + filename
        blob_client = container.get_blob_client(blob_name)
        with open(local_path, "wb") as f:
            stream = blob_client.download_blob()
            stream.readinto(f)
        logger.debug(f"On-demand downloaded avatar {filename}")
        return True
    except ResourceNotFoundError:
        return False
    except Exception as e:
        if _handle_blob_error("download avatar", e):
            return False
        logger.warning(f"Failed to download avatar {filename}: {e}")
        return False


# ── Startup ──────────────────────────────────────────────────────────

def _download_all_avatars_from_blob():
    """Download all avatar images from blob on startup. Avatars are small so this is fast."""
    from services.image_gen import AVATAR_DIR

    container = _get_container_client()
    if not container:
        return

    try:
        os.makedirs(AVATAR_DIR, exist_ok=True)
        count = 0
        for blob in container.list_blobs(name_starts_with=BLOB_AVATAR_PREFIX):
            filename = blob.name[len(BLOB_AVATAR_PREFIX):]
            if not filename:
                continue
            local_path = os.path.join(AVATAR_DIR, filename)
            if os.path.exists(local_path):
                continue
            blob_client = container.get_blob_client(blob.name)
            with open(local_path, "wb") as f:
                stream = blob_client.download_blob()
                stream.readinto(f)
            count += 1
        if count:
            logger.info(f"Downloaded {count} avatar files from blob")
    except Exception as e:
        if _handle_blob_error("startup avatar restore", e):
            return
        logger.warning(f"Failed to download avatars from blob: {e}")


def restore_from_blob():
    """Startup restore: DB + avatars. Audio and video are on-demand."""
    download_db_from_blob()
    _download_all_avatars_from_blob()
