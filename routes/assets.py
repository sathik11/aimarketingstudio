import os
import logging
import threading

from flask import Blueprint, request, jsonify, session, send_from_directory

from auth import require_auth
from db import create_avatar, get_all_avatars, delete_avatar, get_avatar, check_user_image_quota, increment_user_images, update_avatar_status
from services.image_gen import generate_avatar_from_photo, generate_avatar_from_text, AVATAR_DIR, QUALITY_PRESETS
from config import ASSET_STYLES, ASSET_TYPES

logger = logging.getLogger(__name__)

assets_bp = Blueprint("assets", __name__, url_prefix="/api/assets")


@assets_bp.route("/avatars", methods=["GET"])
@require_auth
def api_list_avatars():
    user_id = session.get("user_id")
    avatars = get_all_avatars(user_id)
    for a in avatars:
        status = a.get("status", "ready")
        if status == "ready":
            if a.get("landscape_file"):
                a["landscape_url"] = f"/api/assets/avatar/file/{a['landscape_file']}"
            if a.get("portrait_file"):
                a["portrait_url"] = f"/api/assets/avatar/file/{a['portrait_file']}"
        a["is_builtin"] = a.get("user_id") is None
        a["status"] = status
    return jsonify(avatars), 200


@assets_bp.route("/config", methods=["GET"])
@require_auth
def api_assets_config():
    qualities = [
        {"id": "low", "label": "Low (Fast)", "description": "~10-15 seconds, 1024px"},
        {"id": "medium", "label": "Medium", "description": "~15-25 seconds, 1024px"},
        {"id": "high", "label": "High (Slow)", "description": "~40-70 seconds, 1536px"},
    ]
    return jsonify({"styles": ASSET_STYLES, "asset_types": ASSET_TYPES, "qualities": qualities}), 200


@assets_bp.route("/avatar/from-photo", methods=["POST"])
@require_auth
def api_avatar_from_photo():
    user_id = session.get("user_id")
    if not check_user_image_quota(user_id):
        return jsonify({"error": "Image generation quota exhausted", "code": "IMAGE_QUOTA_EXHAUSTED"}), 429

    name = request.form.get("name", "").strip()
    style = request.form.get("style", "pixar-3d")
    quality = request.form.get("quality", "medium")
    if quality not in QUALITY_PRESETS:
        quality = "medium"
    if not name:
        return jsonify({"error": "name is required"}), 400

    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "photo file is required"}), 400

    photo_bytes = photo.read()

    # Create placeholder record immediately
    avatar = create_avatar(
        user_id=user_id, name=name,
        description=f"Generating from photo ({style}, {quality})…",
        source="photo", model_used="gpt-image-2",
        landscape_file="", portrait_file="",
        asset_type="character", style=style,
        status="generating", quality=quality,
    )
    increment_user_images(user_id)
    avatar_id = avatar["id"]

    def _generate():
        try:
            result = generate_avatar_from_photo(photo_bytes, name, style=style, quality=quality)
            update_avatar_status(
                avatar_id, "ready",
                landscape_file=result["landscape_file"],
                portrait_file=result["portrait_file"],
            )
            logger.info(f"Avatar {avatar_id} from photo completed")
            try:
                from services.blob_sync import upload_db_to_blob
                upload_db_to_blob()
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Avatar {avatar_id} from photo failed")
            update_avatar_status(avatar_id, "failed", error_message=str(e)[:200])

    threading.Thread(target=_generate, daemon=True).start()
    return jsonify(avatar), 202


@assets_bp.route("/avatar/from-text", methods=["POST"])
@require_auth
def api_avatar_from_text():
    user_id = session.get("user_id")
    if not check_user_image_quota(user_id):
        return jsonify({"error": "Image generation quota exhausted", "code": "IMAGE_QUOTA_EXHAUSTED"}), 429

    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    model = body.get("model", "gpt-image-2")
    style = body.get("style", "pixar-3d")
    asset_type = body.get("asset_type", "character")
    quality = body.get("quality", "medium")

    if not name or not description:
        return jsonify({"error": "name and description are required"}), 400

    valid_styles = {s["id"] for s in ASSET_STYLES}
    if style not in valid_styles:
        return jsonify({"error": f"Invalid style. Must be one of: {', '.join(valid_styles)}"}), 400

    valid_types = {t["id"] for t in ASSET_TYPES}
    if asset_type not in valid_types:
        return jsonify({"error": f"Invalid asset type. Must be one of: {', '.join(valid_types)}"}), 400

    if quality not in QUALITY_PRESETS:
        quality = "medium"

    # Create placeholder record immediately
    avatar = create_avatar(
        user_id=user_id, name=name, description=description,
        source="text", model_used=model,
        landscape_file="", portrait_file="",
        asset_type=asset_type, style=style,
        status="generating", quality=quality,
    )
    increment_user_images(user_id)
    avatar_id = avatar["id"]

    def _generate():
        try:
            result = generate_avatar_from_text(description, name, model=model, style=style, asset_type=asset_type, quality=quality)
            update_avatar_status(
                avatar_id, "ready",
                landscape_file=result["landscape_file"],
                portrait_file=result["portrait_file"],
            )
            logger.info(f"Avatar {avatar_id} from text completed")
            try:
                from services.blob_sync import upload_db_to_blob
                upload_db_to_blob()
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Avatar {avatar_id} from text failed")
            update_avatar_status(avatar_id, "failed", error_message=str(e)[:200])

    threading.Thread(target=_generate, daemon=True).start()
    return jsonify(avatar), 202


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
    from services.blob_sync import download_avatar_file_on_demand
    if not download_avatar_file_on_demand(filename):
        return jsonify({"error": "Avatar file not found"}), 404
    return send_from_directory(AVATAR_DIR, filename, mimetype="image/png")


@assets_bp.route("/avatar/<int:avatar_id>/status", methods=["GET"])
@require_auth
def api_avatar_status(avatar_id: int):
    av = get_avatar(avatar_id)
    if not av:
        return jsonify({"error": "Not found"}), 404
    resp = {"id": av["id"], "status": av.get("status", "ready")}
    if resp["status"] == "ready":
        if av.get("landscape_file"):
            resp["landscape_url"] = f"/api/assets/avatar/file/{av['landscape_file']}"
        if av.get("portrait_file"):
            resp["portrait_url"] = f"/api/assets/avatar/file/{av['portrait_file']}"
    elif resp["status"] == "failed":
        resp["error"] = av.get("error_message", "Generation failed")
    return jsonify(resp), 200
