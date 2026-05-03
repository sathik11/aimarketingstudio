from flask import Blueprint, request, jsonify, session

from db import verify_user, get_user_by_id, create_user, update_user_quotas

auth_bp = Blueprint("auth_routes", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def api_login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    user = verify_user(username, password)
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "max_iterations": user["max_iterations"],
        "used_iterations": user["used_iterations"],
        "iterations_remaining": user["max_iterations"] - user["used_iterations"],
        "max_videos": user.get("max_videos", 5),
        "used_videos": user.get("used_videos", 0),
        "videos_remaining": user.get("max_videos", 5) - user.get("used_videos", 0),
        "max_images": user.get("max_images", 20),
        "used_images": user.get("used_images", 0),
        "images_remaining": user.get("max_images", 20) - user.get("used_images", 0),
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True}), 200


@auth_bp.route("/me", methods=["GET"])
def api_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated", "code": "AUTH_REQUIRED"}), 401
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"error": "User not found", "code": "AUTH_REQUIRED"}), 401
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "name": user["name"],
        "max_iterations": user["max_iterations"],
        "used_iterations": user["used_iterations"],
        "iterations_remaining": user["max_iterations"] - user["used_iterations"],
        "max_videos": user.get("max_videos", 5),
        "used_videos": user.get("used_videos", 0),
        "videos_remaining": user.get("max_videos", 5) - user.get("used_videos", 0),
        "max_images": user.get("max_images", 20),
        "used_images": user.get("used_images", 0),
        "images_remaining": user.get("max_images", 20) - user.get("used_images", 0),
    }), 200


@auth_bp.route("/create-user", methods=["POST"])
def api_create_user():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    name = (body.get("name") or "").strip()
    max_iterations = body.get("max_iterations", 50)
    max_videos = body.get("max_videos", 5)
    max_images = body.get("max_images", 20)

    if not username or not password or not name:
        return jsonify({"error": "username, password, and name required"}), 400

    try:
        user = create_user(username, password, name, max_iterations, max_videos, max_images)
        return jsonify(user), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 409


@auth_bp.route("/update-user/<int:user_id>", methods=["PUT"])
def api_update_user(user_id: int):
    """Update quota limits for an existing user."""
    body = request.get_json(silent=True) or {}
    max_iterations = body.get("max_iterations")
    max_videos = body.get("max_videos")
    max_images = body.get("max_images")

    if max_iterations is None and max_videos is None and max_images is None:
        return jsonify({"error": "Provide at least one of: max_iterations, max_videos, max_images"}), 400

    user = update_user_quotas(user_id, max_iterations=max_iterations, max_videos=max_videos, max_images=max_images)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user), 200
