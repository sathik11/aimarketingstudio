import base64
import re
import logging

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_AUDIO_DEPLOYMENT,
    AZURE_OPENAI_AUDIO_API_VERSION, GPT_AUDIO_SYSTEM_PROMPT,
)
from services.audio_utils import store_and_upload

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        # AzureOpenAI needs the base host, strip any /openai/v1/ path
        endpoint = (AZURE_OPENAI_ENDPOINT or "").rstrip("/")
        for suffix in ["/openai/v1", "/openai"]:
            if endpoint.endswith(suffix):
                endpoint = endpoint[:-len(suffix)]
                break
        _client = AzureOpenAI(
            azure_ad_token_provider=token_provider,
            azure_endpoint=endpoint,
            api_version=AZURE_OPENAI_AUDIO_API_VERSION,
        )
    return _client


def _call_audio(client, text: str, voice: str, fmt: str, system_prompt: str) -> tuple[bytes, str]:
    """Make a single gpt-audio chat completion and return (audio_bytes, transcript)."""
    try:
        completion = client.chat.completions.create(
            model=AZURE_OPENAI_AUDIO_DEPLOYMENT,
            modalities=["text", "audio"],
            audio={"voice": voice, "format": fmt},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "not found" in err_str.lower():
            raise RuntimeError(
                f"GPT Audio deployment '{AZURE_OPENAI_AUDIO_DEPLOYMENT}' not found. "
                f"Deploy the model in Azure OpenAI first. Set AZURE_OPENAI_AUDIO_DEPLOYMENT env var."
            ) from e
        raise

    choice = completion.choices[0]
    audio_data = choice.message.audio
    return base64.b64decode(audio_data.data), audio_data.transcript or ""


# System prompt that enforces exact text reproduction
_FAITHFUL_PROMPT = (
    "You are a professional voice-over artist for BDO (B-D-O), a major Philippine bank. "
    "CRITICAL: You MUST speak the EXACT text provided by the user word-for-word. "
    "Do NOT add, remove, rephrase, or translate any words. "
    "Speak in a warm, professional, and engaging tone. "
    "Pronounce 'BDO' as individual letters: B-D-O. Express numbers in English words."
)


def generate(
    text: str,
    voice: str = "alloy",
    fmt: str = "wav",
    system_prompt: str | None = None,
) -> dict:
    if not text or not text.strip():
        raise ValueError("Text is required.")

    text = text.strip()
    prefix = re.sub(r"[^a-zA-Z0-9-]", "", text[:8]) or "gptaud"
    client = _get_client()

    # --- Primary: Speak the EXACT text, no rephrasing ---
    faithful_prompt = _FAITHFUL_PROMPT
    if system_prompt and system_prompt.strip():
        faithful_prompt += "\n\nAdditional style instructions: " + system_prompt.strip()

    audio_bytes, transcript = _call_audio(client, text, voice, fmt, faithful_prompt)
    result = store_and_upload(audio_bytes, prefix, fmt)

    output = {
        "method": "gpt-audio",
        "text_output": transcript,
        "original_text": text,
        **result,
    }

    # --- Alternate: AI-improved/creative version ---
    try:
        creative_prompt = GPT_AUDIO_SYSTEM_PROMPT
        if system_prompt and system_prompt.strip():
            creative_prompt += "\n\nAdditional instructions: " + system_prompt.strip()
        creative_prompt += (
            "\n\nYou may naturally adapt/improve the script for better spoken delivery — "
            "adjust phrasing, add natural emphasis, or translate to Taglish if appropriate. "
            "Keep the same meaning and intent."
        )
        alt_bytes, alt_transcript = _call_audio(client, text, voice, fmt, creative_prompt)
        alt_result = store_and_upload(alt_bytes, f"{prefix}-alt", fmt)

        output["alternate"] = {
            "text_output": alt_transcript,
            **alt_result,
        }
    except Exception as exc:
        logger.warning(f"Alternate GPT audio generation failed: {exc}")
        output["alternate"] = {"error": str(exc)}

    return output
