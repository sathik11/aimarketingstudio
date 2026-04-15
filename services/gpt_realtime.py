import asyncio
import base64
import json
import logging

import websockets
from azure.identity import DefaultAzureCredential

from config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_REALTIME_DEPLOYMENT,
)

logger = logging.getLogger(__name__)

_credential = None


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _get_realtime_url() -> str:
    endpoint = (AZURE_OPENAI_ENDPOINT or "").rstrip("/")
    # Strip /openai/v1 path if present to get the base host
    for suffix in ["/openai/v1", "/openai"]:
        if endpoint.endswith(suffix):
            endpoint = endpoint[:-len(suffix)]
            break
    # Azure OpenAI Realtime API uses /openai/realtime (not /openai/v1/realtime)
    return (
        f"{endpoint.replace('https://', 'wss://').replace('http://', 'ws://')}"
        f"/openai/realtime?api-version=2025-04-01-preview&deployment={AZURE_OPENAI_REALTIME_DEPLOYMENT}"
    )


def _get_auth_token() -> str:
    credential = _get_credential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    return token


async def realtime_text_to_audio(
    text: str,
    voice: str = "alloy",
    instructions: str = "",
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Send text to the Realtime API and collect audio response."""
    url = _get_realtime_url()
    token = _get_auth_token()

    headers = {"Authorization": f"Bearer {token}"}

    audio_chunks = []
    transcript = ""

    try:
        ws_conn = websockets.connect(url, additional_headers=headers)
    except Exception as e:
        raise RuntimeError(
            f"GPT Realtime deployment '{AZURE_OPENAI_REALTIME_DEPLOYMENT}' not reachable. "
            f"Deploy the model in Azure OpenAI first. Set AZURE_OPENAI_REALTIME_DEPLOYMENT env var."
        ) from e

    async with ws_conn as ws:
        # Configure session
        session_config: dict = {
            "voice": voice,
            "instructions": instructions,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": None,
        }
        if temperature is not None:
            session_config["temperature"] = temperature
        if max_output_tokens is not None:
            session_config["max_response_output_tokens"] = max_output_tokens

        session_update = {"type": "session.update", "session": session_config}
        await ws.send(json.dumps(session_update))

        # Wait for session.updated
        msg = json.loads(await ws.recv())
        if msg.get("type") == "error":
            raise RuntimeError(f"Realtime session error: {msg}")

        # Send text as a conversation item
        item_create = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
        await ws.send(json.dumps(item_create))

        # Request response
        response_create = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"],
            },
        }
        await ws.send(json.dumps(response_create))

        # Collect response events
        while True:
            raw = await ws.recv()
            event = json.loads(raw)
            etype = event.get("type", "")

            if etype == "response.audio.delta":
                chunk = base64.b64decode(event.get("delta", ""))
                audio_chunks.append(chunk)
            elif etype == "response.audio_transcript.done":
                transcript = event.get("transcript", transcript)
            elif etype == "response.done":
                break
            elif etype == "error":
                raise RuntimeError(f"Realtime error: {event}")

    audio_bytes = b"".join(audio_chunks)
    return {
        "audio_bytes": audio_bytes,
        "transcript": transcript,
        "format": "pcm16",
    }


_FAITHFUL_INSTRUCTIONS = (
    "You are a professional voice-over artist for BDO (B-D-O), a major Philippine bank. "
    "CRITICAL: You MUST speak the EXACT text provided by the user word-for-word. "
    "Do NOT add, remove, rephrase, or translate any words. "
    "Speak in a warm, professional, and engaging tone suitable for marketing videos. "
    "Pronounce 'BDO' as individual letters: B-D-O. Express numbers in English words."
)

_CREATIVE_INSTRUCTIONS = (
    "You are a professional voice-over artist for BDO (B-D-O), a major Philippine bank. "
    "Speak in a warm, professional, and engaging tone suitable for marketing videos. "
    "You may naturally adapt/improve the script for better spoken delivery — "
    "adjust phrasing, add natural emphasis, or enhance with Taglish if appropriate. "
    "Keep the same meaning and intent. Pronounce 'BDO' as B-D-O."
)


def generate(
    text: str,
    voice: str = "alloy",
    instructions: str = "",
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> dict:
    """Synchronous wrapper for realtime TTS with dual output."""
    if not text or not text.strip():
        raise ValueError("Text is required.")

    text = text.strip()

    from services.audio_utils import store_and_upload, pcm16_to_wav
    import re

    prefix = re.sub(r"[^a-zA-Z0-9-]", "", text[:8]) or "rt"

    # --- Primary: Speak EXACT text ---
    faithful = _FAITHFUL_INSTRUCTIONS
    if instructions and instructions.strip():
        faithful += "\n\nAdditional instructions: " + instructions.strip()

    result = asyncio.run(realtime_text_to_audio(
        text, voice, faithful, temperature, max_output_tokens
    ))
    wav_bytes = pcm16_to_wav(result["audio_bytes"])
    stored = store_and_upload(wav_bytes, prefix, "wav")

    output = {
        "method": "gpt-realtime",
        "text_output": result["transcript"],
        "original_text": text,
        **stored,
    }

    # --- Alternate: AI-improved version ---
    try:
        creative = _CREATIVE_INSTRUCTIONS
        if instructions and instructions.strip():
            creative += "\n\nAdditional instructions: " + instructions.strip()

        alt_result = asyncio.run(realtime_text_to_audio(
            text, voice, creative, temperature, max_output_tokens
        ))
        alt_wav = pcm16_to_wav(alt_result["audio_bytes"])
        alt_stored = store_and_upload(alt_wav, f"{prefix}-alt", "wav")

        output["alternate"] = {
            "text_output": alt_result["transcript"],
            **alt_stored,
        }
    except Exception as exc:
        logger.warning(f"Alternate realtime generation failed: {exc}")
        output["alternate"] = {"error": str(exc)}

    return output
