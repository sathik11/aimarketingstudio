from flask import Blueprint, request, jsonify

from auth import require_auth
from db import create_script, get_script, list_scripts, update_script, delete_script

scripts_bp = Blueprint("scripts", __name__, url_prefix="/api/scripts")


@scripts_bp.route("", methods=["GET"])
@require_auth
def api_list_scripts():
    scripts = list_scripts()
    return jsonify(scripts), 200


@scripts_bp.route("", methods=["POST"])
@require_auth
def api_create_script():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    text = (body.get("text") or "").strip()
    if not title or not text:
        return jsonify({"error": "title and text are required"}), 400
    language = body.get("language", "fil-PH")
    script = create_script(title, text, language)
    return jsonify(script), 201


@scripts_bp.route("/<int:script_id>", methods=["GET"])
@require_auth
def api_get_script(script_id: int):
    script = get_script(script_id)
    if not script:
        return jsonify({"error": "Script not found"}), 404
    return jsonify(script), 200


@scripts_bp.route("/<int:script_id>", methods=["PUT"])
@require_auth
def api_update_script(script_id: int):
    body = request.get_json(silent=True) or {}
    script = update_script(
        script_id,
        title=body.get("title"),
        text=body.get("text"),
        language=body.get("language"),
    )
    if not script:
        return jsonify({"error": "Script not found"}), 404
    return jsonify(script), 200


@scripts_bp.route("/<int:script_id>", methods=["DELETE"])
@require_auth
def api_delete_script(script_id: int):
    deleted = delete_script(script_id)
    if not deleted:
        return jsonify({"error": "Script not found"}), 404
    return jsonify({"ok": True}), 200
