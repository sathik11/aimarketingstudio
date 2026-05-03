"""
MAI-Voice-1 text-to-speech service.

Uses the same Azure Speech SDK as azure_tts but connects to a separate
resource in northcentralus.  MAI-Voice-1 supports mstts:express-as for
emotional style control and produces highly expressive speech.
"""

import os
import re
import logging
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk
from azure.identity import DefaultAzureCredential

from config import (
    AZURE_SPEECH_RESOURCE_ID,
    AZURE_SPEECH_REGION,
    PRONUNCIATION_DICT,
    AUDIO_OUTPUT_DIR,
)
from services.audio_utils import store_and_upload

logger = logging.getLogger(__name__)

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

_credential = None


def _get_credential():
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def _apply_pronunciation_subs(text: str, custom_subs: dict | None = None) -> str:
    """Plain-text pronunciation replacement (MAI voices may not support <sub>)."""
    subs = {**PRONUNCIATION_DICT}
    if custom_subs:
        subs.update(custom_subs)
    for term, replacement in subs.items():
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text = pattern.sub(replacement, text)
    return text


def _strip_lang_tags(text: str) -> str:
    return text.replace("[FIL]", "").replace("[/FIL]", "")


def build_ssml(
    text: str,
    voice: str = "en-us-Jasper:MAI-Voice-1",
    custom_subs: dict | None = None,
) -> str:
    """Build SSML for MAI-Voice-1.

    MAI-Voice-1 automatically adapts tone/emotion so we keep the SSML
    minimal — no prosody overrides.  We strip [FIL] markers since these
    are English-only voices.
    """
    processed = _apply_pronunciation_subs(text, custom_subs)
    processed = _strip_lang_tags(processed)
    processed = escape(processed)

    return (
        '<speak version="1.0" xml:lang="en-US" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts">'
        f'<voice name="{escape(voice)}">'
        f'{processed}'
        '</voice>'
        '</speak>'
    )


def synthesize(ssml: str) -> bytes:
    if not AZURE_SPEECH_RESOURCE_ID:
        raise ValueError("Set AZURE_SPEECH_RESOURCE_ID env var.")
    if not AZURE_SPEECH_REGION:
        raise ValueError("Set AZURE_SPEECH_REGION env var.")

    credential = _get_credential()
    speech_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    speech_auth_token = f"aad#{AZURE_SPEECH_RESOURCE_ID}#{speech_token}"

    speech_config = speechsdk.SpeechConfig(
        auth_token=speech_auth_token,
        region=AZURE_SPEECH_REGION,
    )
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=None,
    )

    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(
            f"MAI-Voice-1 synthesis canceled: {details.reason}. "
            f"Details: {details.error_details or 'none'}"
        )
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"Unexpected MAI-Voice-1 result: {result.reason}")

    stream = speechsdk.AudioDataStream(result)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        stream.save_to_wav_file(tmp.name)
        with open(tmp.name, "rb") as f:
            audio_bytes = f.read()
        os.unlink(tmp.name)

    return audio_bytes


def generate(
    text: str,
    voice: str = "en-us-Jasper:MAI-Voice-1",
    fmt: str = "wav",
    custom_subs: dict | None = None,
) -> dict:
    if not text or not text.strip():
        raise ValueError("Text is required.")

    ssml = build_ssml(text.strip(), voice, custom_subs)
    audio_bytes = synthesize(ssml)

    prefix = re.sub(r"[^a-zA-Z0-9-]", "", text[:8]) or "mai"
    result = store_and_upload(audio_bytes, prefix, "wav")

    # Convert to MP3 if requested
    if fmt == "mp3":
        from services.audio_utils import convert_wav_to_mp3
        mp3_file = convert_wav_to_mp3(result["local_audio_file"])
        result["local_audio_file"] = mp3_file

    return {
        "method": "mai-voice-1",
        "text_output": text.strip(),
        "ssml": ssml,
        **result,
    }
