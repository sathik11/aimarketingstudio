import logging

from flask import Blueprint, request, jsonify, url_for

from auth import require_auth, require_quota
from db import record_generation
from services import azure_tts, gpt_ssml, gpt_audio, gpt_realtime

logger = logging.getLogger(__name__)

generate_bp = Blueprint("generate", __name__, url_prefix="/api/generate")


@generate_bp.route("/azure-tts", methods=["POST"])
@require_auth
@require_quota
def api_azure_tts():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        result = azure_tts.generate(
            text=text,
            voice=body.get("voice"),
            rate=body.get("rate"),
            pitch=body.get("pitch"),
            volume=body.get("volume"),
            language=body.get("language", "fil-PH"),
            fmt=body.get("format", "wav"),
            custom_subs=body.get("pronunciation"),
        )
    except Exception as e:
        logger.exception("azure-tts generation failed")
        return jsonify({"error": str(e)}), 500

    _enrich_audio_url(result)
    _record(result, body)
    return jsonify(result), 200


@generate_bp.route("/gpt-ssml", methods=["POST"])
@require_auth
@require_quota
def api_gpt_ssml():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        result = gpt_ssml.generate(
            text=text,
            voice=body.get("voice"),
            rate=body.get("rate"),
            pitch=body.get("pitch"),
            volume=body.get("volume"),
            language=body.get("language", "fil-PH"),
            fmt=body.get("format", "wav"),
            translate=body.get("translate", True),
            custom_subs=body.get("pronunciation"),
        )
    except Exception as e:
        logger.exception("gpt-ssml generation failed")
        return jsonify({"error": str(e)}), 500

    _enrich_audio_url(result)
    _record(result, body)
    return jsonify(result), 200


@generate_bp.route("/gpt-audio", methods=["POST"])
@require_auth
@require_quota
def api_gpt_audio():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        result = gpt_audio.generate(
            text=text,
            voice=body.get("voice", "alloy"),
            fmt=body.get("format", "wav"),
            system_prompt=body.get("system_prompt"),
        )
    except Exception as e:
        logger.exception("gpt-audio generation failed")
        return jsonify({"error": str(e)}), 500

    _enrich_audio_url(result)
    _record(result, body)
    return jsonify(result), 200


@generate_bp.route("/gpt-realtime", methods=["POST"])
@require_auth
@require_quota
def api_gpt_realtime():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    try:
        result = gpt_realtime.generate(
            text=text,
            voice=body.get("voice", "alloy"),
            instructions=body.get("instructions", ""),
            temperature=body.get("temperature"),
            max_output_tokens=body.get("max_output_tokens"),
        )
    except Exception as e:
        logger.exception("gpt-realtime generation failed")
        return jsonify({"error": str(e)}), 500

    _enrich_audio_url(result)
    _record(result, body)
    return jsonify(result), 200


@generate_bp.route("/ssml-playground", methods=["POST"])
@require_auth
def api_ssml_playground():
    """Synthesize raw SSML directly — for the SSML Playground."""
    body = request.get_json(silent=True) or {}
    ssml = (body.get("ssml") or "").strip()
    if not ssml:
        return jsonify({"error": "ssml is required"}), 400

    try:
        audio_bytes = azure_tts.synthesize(ssml)
        from services.audio_utils import store_and_upload
        result = store_and_upload(audio_bytes, "ssml", "wav")
        result["method"] = "ssml-playground"
        result["ssml"] = ssml
    except Exception as e:
        logger.exception("ssml-playground synthesis failed")
        return jsonify({"error": str(e)}), 500

    _enrich_audio_url(result)
    return jsonify(result), 200


def _enrich_audio_url(result: dict):
    local_file = result.get("local_audio_file")
    if local_file:
        result["audio_url"] = url_for("serve_audio", filename=local_file, _external=True)
        if not result.get("storage_url"):
            result["speech_output"] = result["audio_url"]
        else:
            result["speech_output"] = result["storage_url"]

    # Also enrich alternate audio URL if present
    alt = result.get("alternate")
    if alt and isinstance(alt, dict) and alt.get("local_audio_file"):
        alt["audio_url"] = url_for("serve_audio", filename=alt["local_audio_file"], _external=True)


def _record(result: dict, body: dict):
    try:
        record_generation(
            method=result.get("method", "unknown"),
            voice=body.get("voice"),
            params=body,
            audio_file=result.get("local_audio_file"),
            fmt=body.get("format", "wav"),
            text_output=result.get("text_output"),
            script_id=body.get("script_id"),
        )
    except Exception:
        logger.warning("Failed to record generation", exc_info=True)

    # Increment user iteration count
    try:
        from flask import session
        from db import increment_user_iterations
        user_id = session.get("user_id")
        if user_id:
            increment_user_iterations(user_id)
    except Exception:
        logger.warning("Failed to increment user iterations", exc_info=True)
