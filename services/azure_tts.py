import os
import re
import logging
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk
from azure.identity import DefaultAzureCredential

from config import (
    AZURE_SPEECH_RESOURCE_ID, AZURE_SPEECH_REGION, AZURE_SPEECH_VOICE,
    PRONUNCIATION_DICT, PROSODY_DEFAULTS, AUDIO_OUTPUT_DIR,
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


def _apply_pronunciation_subs(text: str, custom_subs: dict | None = None, use_ssml_tags: bool = True) -> str:
    subs = {**PRONUNCIATION_DICT}
    if custom_subs:
        subs.update(custom_subs)
    for term, replacement in subs.items():
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        if use_ssml_tags:
            text = pattern.sub(f'<sub alias="{escape(replacement)}">{escape(term)}</sub>', text)
        else:
            # Plain text replacement for voices that don't support <sub> (e.g. fil-PH)
            text = pattern.sub(replacement, text)
    return text


def _voice_supports_ssml_sub(voice: str) -> bool:
    """fil-PH voices (footnote 3 in Azure docs) don't support phoneme, custom lexicon, or sub."""
    return not voice.startswith("fil-PH")


def _is_multilingual_voice(voice: str) -> bool:
    """DragonHD and Multilingual voices support <lang> element for language switching."""
    return "DragonHD" in voice or "Multilingual" in voice


def _convert_lang_tags(text: str) -> str:
    """Convert [FIL]...[/FIL] markers to <lang xml:lang="fil-PH">...</lang> SSML elements."""
    return re.sub(
        r'\[FIL\](.*?)\[/FIL\]',
        r'<lang xml:lang="fil-PH">\1</lang>',
        text,
        flags=re.DOTALL,
    )


def _strip_lang_tags(text: str) -> str:
    """Remove [FIL]/[/FIL] markers, leaving plain text."""
    return text.replace("[FIL]", "").replace("[/FIL]", "")


def build_ssml(
    text: str,
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    volume: str | None = None,
    language: str = "fil-PH",
    custom_subs: dict | None = None,
) -> str:
    voice = voice or AZURE_SPEECH_VOICE
    rate = rate or PROSODY_DEFAULTS["rate"]
    pitch = pitch or PROSODY_DEFAULTS["pitch"]
    volume = volume or PROSODY_DEFAULTS["volume"]

    # Apply pronunciation substitutions
    # fil-PH voices don't support <sub alias> SSML tags (Azure docs footnote 3)
    use_ssml = _voice_supports_ssml_sub(voice)
    processed = _apply_pronunciation_subs(text, custom_subs, use_ssml_tags=use_ssml)
    if not use_ssml:
        processed = escape(processed)

    # For multilingual voices, convert [FIL]...[/FIL] to <lang> SSML elements
    # For non-multilingual voices, strip the markers
    if _is_multilingual_voice(voice):
        processed = _convert_lang_tags(processed)
        # Use en-US as root lang for multilingual voices (required by Azure docs)
        root_lang = "en-US"
    else:
        processed = _strip_lang_tags(processed)
        root_lang = language

    return (
        f'<speak version="1.0" xml:lang="{escape(root_lang)}" '
        f'xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="https://www.w3.org/2001/mstts">'
        f'<voice name="{escape(voice)}">'
        f'<prosody rate="{escape(rate)}" pitch="{escape(pitch)}" volume="{escape(volume)}">'
        f'{processed}'
        f'</prosody>'
        f'</voice>'
        f'</speak>'
    )


def synthesize(ssml: str) -> bytes:
    if not AZURE_SPEECH_RESOURCE_ID:
        raise ValueError("Set AZURE_SPEECH_RESOURCE_ID env var.")
    if not AZURE_SPEECH_REGION:
        raise ValueError("Set AZURE_SPEECH_REGION env var.")

    credential = _get_credential()
    speech_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    speech_auth_token = f"aad#{AZURE_SPEECH_RESOURCE_ID}#{speech_token}"

    speech_config = speechsdk.SpeechConfig(auth_token=speech_auth_token, region=AZURE_SPEECH_REGION)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(
            f"Speech synthesis canceled: {details.reason}. "
            f"Details: {details.error_details or 'none'}"
        )
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"Unexpected synthesis result: {result.reason}")

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
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    volume: str | None = None,
    language: str = "fil-PH",
    fmt: str = "wav",
    custom_subs: dict | None = None,
) -> dict:
    if not text or not text.strip():
        raise ValueError("Text is required.")

    ssml = build_ssml(text.strip(), voice, rate, pitch, volume, language, custom_subs)
    audio_bytes = synthesize(ssml)

    prefix = re.sub(r"[^a-zA-Z0-9-]", "", text[:8]) or "azure"
    result = store_and_upload(audio_bytes, prefix, "wav")

    # Convert to MP3 if requested
    if fmt == "mp3":
        from services.audio_utils import convert_wav_to_mp3
        mp3_file = convert_wav_to_mp3(result["local_audio_file"])
        result["local_audio_file"] = mp3_file

    return {
        "method": "azure-tts",
        "text_output": text.strip(),
        "ssml": ssml,
        **result,
    }
