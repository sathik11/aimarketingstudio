import logging
from flask import Blueprint, request, jsonify

from auth import require_auth
import config

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")

# Mutable prompt store — initialized from config defaults, editable at runtime
_prompts = {
    "gpt_ssml_translation": config.TRANSLATION_SYSTEM_PROMPT,
    "gpt_ssml_annotation": config.SSML_ANNOTATION_PROMPT,
    "gpt_ssml_rewrite": config.SSML_REWRITE_PROMPT,
    "gpt_audio_system": config.GPT_AUDIO_SYSTEM_PROMPT,
    "gpt_audio_faithful": None,  # loaded lazily from service
    "gpt_realtime_faithful": None,  # loaded lazily from service
    "gpt_realtime_creative": None,  # loaded lazily from service
}


def _ensure_service_prompts():
    """Load hardcoded service prompts on first access."""
    if _prompts["gpt_audio_faithful"] is None:
        from services.gpt_audio import _FAITHFUL_PROMPT
        _prompts["gpt_audio_faithful"] = _FAITHFUL_PROMPT
    if _prompts["gpt_realtime_faithful"] is None:
        from services.gpt_realtime import _FAITHFUL_INSTRUCTIONS
        _prompts["gpt_realtime_faithful"] = _FAITHFUL_INSTRUCTIONS
    if _prompts["gpt_realtime_creative"] is None:
        from services.gpt_realtime import _CREATIVE_INSTRUCTIONS
        _prompts["gpt_realtime_creative"] = _CREATIVE_INSTRUCTIONS


def get_prompt(key: str) -> str:
    _ensure_service_prompts()
    return _prompts.get(key, "")


@settings_bp.route("/prompts", methods=["GET"])
@require_auth
def api_get_prompts():
    _ensure_service_prompts()
    return jsonify({
        "prompts": {
            k: {
                "value": v,
                "description": _PROMPT_DESCRIPTIONS.get(k, ""),
                "method": _PROMPT_METHOD.get(k, ""),
            }
            for k, v in _prompts.items()
        }
    }), 200


@settings_bp.route("/prompts", methods=["PUT"])
@require_auth
def api_update_prompts():
    body = request.get_json(silent=True) or {}
    updates = body.get("prompts", {})

    _ensure_service_prompts()

    updated_keys = []
    for key, value in updates.items():
        if key in _prompts and isinstance(value, str):
            _prompts[key] = value
            updated_keys.append(key)

            # Propagate to config/service modules so generation uses updated values
            if key == "gpt_ssml_translation":
                config.TRANSLATION_SYSTEM_PROMPT = value
            elif key == "gpt_ssml_annotation":
                config.SSML_ANNOTATION_PROMPT = value
            elif key == "gpt_ssml_rewrite":
                config.SSML_REWRITE_PROMPT = value
            elif key == "gpt_audio_system":
                config.GPT_AUDIO_SYSTEM_PROMPT = value
            elif key == "gpt_audio_faithful":
                import services.gpt_audio as ga
                ga._FAITHFUL_PROMPT = value
            elif key == "gpt_realtime_faithful":
                import services.gpt_realtime as gr
                gr._FAITHFUL_INSTRUCTIONS = value
            elif key == "gpt_realtime_creative":
                import services.gpt_realtime as gr
                gr._CREATIVE_INSTRUCTIONS = value

    return jsonify({"updated": updated_keys}), 200


_PROMPT_DESCRIPTIONS = {
    "gpt_ssml_translation": "GPT prompt for translating English to Taglish with [FIL] markers. Used by GPT+SSML method.",
    "gpt_ssml_annotation": "GPT prompt for annotating existing Taglish text with [FIL] language markers for DragonHD voices.",
    "gpt_ssml_rewrite": "GPT prompt for rewriting scripts for better spoken SSML delivery. Used for the AI Suggested Version in GPT+SSML.",
    "gpt_audio_system": "Creative/alternate system prompt for GPT Audio. Used for the AI Suggested Version.",
    "gpt_audio_faithful": "Strict system prompt for GPT Audio primary output. Enforces exact text reproduction.",
    "gpt_realtime_faithful": "Strict instructions for GPT Realtime primary output. Enforces exact text reproduction.",
    "gpt_realtime_creative": "Creative instructions for GPT Realtime AI Suggested Version.",
}

_PROMPT_METHOD = {
    "gpt_ssml_translation": "GPT + SSML",
    "gpt_ssml_annotation": "GPT + SSML",
    "gpt_ssml_rewrite": "GPT + SSML",
    "gpt_audio_system": "GPT Audio",
    "gpt_audio_faithful": "GPT Audio",
    "gpt_realtime_faithful": "GPT Realtime",
    "gpt_realtime_creative": "GPT Realtime",
}
