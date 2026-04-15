import os
import logging

from flask import Blueprint, request, jsonify, session, send_from_directory

from auth import require_auth
from db import create_avatar, get_all_avatars, delete_avatar, get_avatar
from services.image_gen import generate_avatar_from_photo, generate_avatar_from_text, AVATAR_DIR

logger = logging.getLogger(__name__)

assets_bp = Blueprint("assets", __name__, url_prefix="/api/assets")


@assets_bp.route("/avatars", methods=["GET"])
@require_auth
def api_list_avatars():
    user_id = session.get("user_id")
    avatars = get_all_avatars(user_id)
    for a in avatars:
        if a.get("landscape_file"):
            a["landscape_url"] = f"/api/assets/avatar/file/{a['landscape_file']}"
        if a.get("portrait_file"):
            a["portrait_url"] = f"/api/assets/avatar/file/{a['portrait_file']}"
        a["is_builtin"] = a.get("user_id") is None
    return jsonify(avatars), 200


@assets_bp.route("/avatar/from-photo", methods=["POST"])
@require_auth
def api_avatar_from_photo():
    user_id = session.get("user_id")
    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "photo file is required"}), 400

    try:
        photo_bytes = photo.read()
        result = generate_avatar_from_photo(photo_bytes, name)
        avatar = create_avatar(
            user_id=user_id,
            name=name,
            description=f"Generated from photo ({result['model_used']})",
            source=result["source"],
            model_used=result["model_used"],
            landscape_file=result["landscape_file"],
            portrait_file=result["portrait_file"],
        )
        return jsonify(avatar), 201
    except Exception as e:
        logger.exception("Avatar from photo failed")
        return jsonify({"error": str(e)}), 500


@assets_bp.route("/avatar/from-text", methods=["POST"])
@require_auth
def api_avatar_from_text():
    user_id = session.get("user_id")
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    model = body.get("model", "gpt-image-1.5")

    if not name or not description:
        return jsonify({"error": "name and description are required"}), 400

    if model not in ("gpt-image-1.5", "MAI-Image-2"):
        return jsonify({"error": "model must be gpt-image-1.5 or MAI-Image-2"}), 400

    try:
        result = generate_avatar_from_text(description, name, model)
        avatar = create_avatar(
            user_id=user_id,
            name=name,
            description=description,
            source=result["source"],
            model_used=result["model_used"],
            landscape_file=result["landscape_file"],
            portrait_file=result["portrait_file"],
        )
        return jsonify(avatar), 201
    except Exception as e:
        logger.exception("Avatar from text failed")
        return jsonify({"error": str(e)}), 500


@assets_bp.route("/avatar/<int:avatar_id>", methods=["DELETE"])
@require_auth
def api_delete_avatar(avatar_id: int):
    user_id = session.get("user_id")
    av = get_avatar(avatar_id)
    if not av:
        return jsonify({"error": "Not found"}), 404
    if av.get("user_id") is None:
        return jsonify({"error": "Cannot delete built-in avatars"}), 403

    # Delete files
    for key in ("landscape_file", "portrait_file"):
        fpath = os.path.join(AVATAR_DIR, av.get(key, ""))
        if os.path.exists(fpath):
            os.unlink(fpath)

    deleted = delete_avatar(avatar_id, user_id)
    if not deleted:
        return jsonify({"error": "Not found or not yours"}), 404
    return jsonify({"ok": True}), 200


@assets_bp.route("/avatar/file/<path:filename>", methods=["GET"])
@require_auth
def api_avatar_file(filename: str):
    return send_from_directory(AVATAR_DIR, filename, mimetype="image/png")
