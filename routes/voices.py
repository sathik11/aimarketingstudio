from flask import Blueprint, jsonify

from auth import require_auth
from config import VOICES, AUDIO_FORMATS

voices_bp = Blueprint("voices", __name__, url_prefix="/api/voices")


@voices_bp.route("", methods=["GET"])
@require_auth
def api_list_voices():
    return jsonify({
        "voices": VOICES,
        "formats": AUDIO_FORMATS,
    }), 200
