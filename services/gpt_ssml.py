import re
import logging

from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
    TRANSLATION_SYSTEM_PROMPT, SSML_ANNOTATION_PROMPT, SSML_REWRITE_PROMPT,
    AZURE_SPEECH_VOICE,
)
from services.azure_tts import build_ssml, synthesize, _is_multilingual_voice
from services.audio_utils import store_and_upload, convert_wav_to_mp3

logger = logging.getLogger(__name__)

_client = None


def _normalize_openai_base_url(raw_endpoint: str) -> str:
    endpoint = (raw_endpoint or "").rstrip("/")
    if not endpoint:
        return "https://your-openai-resource.openai.azure.com/openai/v1/"
    if endpoint.endswith("/openai/v1") or endpoint.endswith("/openai/v1/"):
        return f"{endpoint.rstrip('/')}/"
    if ".openai.azure.com" in endpoint and "/openai/" not in endpoint:
        return f"{endpoint}/openai/v1/"
    return f"{endpoint}/"


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        base_url = _normalize_openai_base_url(AZURE_OPENAI_ENDPOINT)
        _client = OpenAI(base_url=base_url, api_key=token_provider)
    return _client


def _extract_response_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text
    output = getattr(response, "output", []) or []
    parts = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts)


def translate_text(text: str) -> str:
    client = _get_client()
    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=TRANSLATION_SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    )
    return _extract_response_text(response).strip()


def annotate_taglish(text: str) -> str:
    """Use GPT to annotate existing Taglish text with [FIL]...[/FIL] language markers."""
    client = _get_client()
    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=SSML_ANNOTATION_PROMPT,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    )
    return _extract_response_text(response).strip()


def rewrite_for_ssml(text: str) -> str:
    """GPT rewrites the script for better spoken delivery, with [FIL] annotations."""
    client = _get_client()
    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=SSML_REWRITE_PROMPT,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    )
    return _extract_response_text(response).strip()


def _strip_fil_tags(text: str) -> str:
    """Strip [FIL]/[/FIL] markers for clean display."""
    return text.replace("[FIL]", "").replace("[/FIL]", "")


def generate(
    text: str,
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    volume: str | None = None,
    language: str = "fil-PH",
    fmt: str = "wav",
    translate: bool = True,
    custom_subs: dict | None = None,
) -> dict:
    if not text or not text.strip():
        raise ValueError("Text is required.")

    text = text.strip()
    voice = voice or AZURE_SPEECH_VOICE
    prefix = re.sub(r"[^a-zA-Z0-9-]", "", text[:8]) or "gpt"
    is_multi = _is_multilingual_voice(voice)

    # --- Primary: GPT annotates original text with [FIL] markers → SSML with <lang> → synthesize ---
    if is_multi:
        annotated_text = annotate_taglish(text)
    else:
        annotated_text = text

    ssml_primary = build_ssml(annotated_text, voice, rate, pitch, volume, language, custom_subs)
    audio_bytes_primary = synthesize(ssml_primary)
    result_primary = store_and_upload(audio_bytes_primary, prefix, "wav")

    if fmt == "mp3":
        result_primary["local_audio_file"] = convert_wav_to_mp3(result_primary["local_audio_file"])

    # Show annotated text cleanly (strip [FIL] tags) for display
    result = {
        "method": "gpt-ssml",
        "text_output": _strip_fil_tags(annotated_text),
        "original_text": text,
        "ssml": ssml_primary,
        **result_primary,
    }

    # --- Alternate: GPT rewrites script for better spoken delivery ---
    if translate:
        try:
            rewritten = rewrite_for_ssml(text)
            ssml_alt = build_ssml(rewritten, voice, rate, pitch, volume, language, custom_subs)
            audio_bytes_alt = synthesize(ssml_alt)
            result_alt = store_and_upload(audio_bytes_alt, f"{prefix}-alt", "wav")

            if fmt == "mp3":
                result_alt["local_audio_file"] = convert_wav_to_mp3(result_alt["local_audio_file"])

            result["alternate"] = {
                "text_output": _strip_fil_tags(rewritten),
                "ssml": ssml_alt,
                **result_alt,
            }
        except Exception as exc:
            logger.warning(f"Alternate rewrite failed: {exc}")
            result["alternate"] = {"error": str(exc)}

    return result
