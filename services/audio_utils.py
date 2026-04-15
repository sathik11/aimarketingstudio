import os
import uuid
import subprocess
import logging

from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

from config import AUDIO_OUTPUT_DIR, AZURE_STORAGE_ACCOUNT_URL, AZURE_STORAGE_CONTAINER_NAME

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

_credential = None


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def save_audio_file(audio_bytes: bytes, prefix: str = "out", ext: str = "wav") -> str:
    safe_prefix = "".join(c for c in (prefix or "out")[:8] if c.isalnum() or c == "-") or "out"
    filename = f"{safe_prefix}-{uuid.uuid4()}.{ext}"
    filepath = os.path.join(AUDIO_OUTPUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(audio_bytes)
    return filename


def convert_wav_to_mp3(wav_filename: str) -> str:
    wav_path = os.path.join(AUDIO_OUTPUT_DIR, wav_filename)
    mp3_filename = wav_filename.rsplit(".", 1)[0] + ".mp3"
    mp3_path = os.path.join(AUDIO_OUTPUT_DIR, mp3_filename)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
            check=True,
            capture_output=True,
        )
        return mp3_filename
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"ffmpeg conversion failed: {e}")
        return wav_filename


def pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM16 bytes in a WAV header so browsers can play it."""
    import struct
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1,  # PCM format
        channels, sample_rate, byte_rate, block_align, sample_width * 8,
        b'data', data_size,
    )
    return header + pcm_bytes


def upload_audio_to_blob(local_filename: str) -> str | None:
    if not AZURE_STORAGE_ACCOUNT_URL or not AZURE_STORAGE_CONTAINER_NAME:
        return None

    local_path = os.path.join(AUDIO_OUTPUT_DIR, local_filename)
    credential = _get_credential()
    blob_service_client = BlobServiceClient(account_url=AZURE_STORAGE_ACCOUNT_URL, credential=credential)
    blob_client = blob_service_client.get_blob_client(container=AZURE_STORAGE_CONTAINER_NAME, blob=local_filename)

    with open(local_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    return blob_client.url


def store_and_upload(audio_bytes: bytes, prefix: str = "out", fmt: str = "wav") -> dict:
    filename = save_audio_file(audio_bytes, prefix, fmt)

    # Convert WAV to MP3 if requested
    if fmt == "mp3" and filename.endswith(".wav"):
        filename = convert_wav_to_mp3(filename)

    storage_url = None
    storage_error = None
    try:
        storage_url = upload_audio_to_blob(filename)
    except Exception as exc:
        storage_error = str(exc)
        logger.warning(f"Blob upload failed: {storage_error}")

    return {
        "local_audio_file": filename,
        "storage_url": storage_url,
        "storage_error": storage_error,
    }
