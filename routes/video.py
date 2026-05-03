import os
import logging

from flask import Blueprint, request, jsonify, session, send_from_directory

from auth import require_auth
from db import (
    get_user_by_id, check_user_video_quota,
    create_video_job, get_video_job, get_user_video_jobs,
    create_video_project, add_project_scenes, get_video_project,
    get_user_video_projects, update_video_project,
)
from config import VIDEO_OUTPUT_DIR, VIDEO_STYLES, VIDEO_RESOLUTIONS, AVATARS
from services.sora_video import generate_video_prompt, submit_video_job, split_script_into_scenes, submit_storyboard

logger = logging.getLogger(__name__)

video_bp = Blueprint("video", __name__, url_prefix="/api/video")


@video_bp.route("/config", methods=["GET"])
@require_auth
def api_video_config():
    return jsonify({"styles": VIDEO_STYLES, "resolutions": VIDEO_RESOLUTIONS, "avatars": AVATARS}), 200


@video_bp.route("/avatar/<path:filename>", methods=["GET"])
def api_avatar_image(filename: str):
    """Serve avatar images (on-demand download from blob)."""
    from services.blob_sync import download_avatar_file_on_demand
    if not download_avatar_file_on_demand(filename):
        return jsonify({"error": "Avatar file not found"}), 404
    return send_from_directory("static/avatars", filename, mimetype="image/png")


@video_bp.route("/generate", methods=["POST"])
@require_auth
def api_video_generate():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if not check_user_video_quota(user_id):
        user = get_user_by_id(user_id)
        return jsonify({
            "error": "Video quota exhausted",
            "code": "VIDEO_QUOTA_EXHAUSTED",
            "max_videos": user["max_videos"] if user else 0,
            "used_videos": user["used_videos"] if user else 0,
        }), 429

    # Parse form data (multipart for image upload)
    script = request.form.get("script", "").strip()
    style = request.form.get("style", "animation")
    resolution = request.form.get("resolution", "1280x720")

    if not script:
        return jsonify({"error": "script is required"}), 400

    # Handle optional reference image
    ref_image_path = None
    ref_file = request.files.get("reference_image")
    if ref_file and ref_file.filename:
        os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
        safe_name = f"ref-{user_id}-{os.urandom(4).hex()}.{ref_file.filename.rsplit('.', 1)[-1]}"
        ref_image_path = os.path.join(VIDEO_OUTPUT_DIR, safe_name)
        ref_file.save(ref_image_path)

    # Generate Sora 2 prompt from script using GPT
    try:
        video_prompt = generate_video_prompt(script, style)
    except Exception as e:
        logger.exception("Failed to generate video prompt")
        return jsonify({"error": f"Prompt generation failed: {e}"}), 500

    # Create DB job
    job = create_video_job(
        user_id=user_id,
        script=script,
        generated_prompt=video_prompt,
        style=style,
        resolution=resolution,
        has_ref=ref_image_path is not None,
    )

    # Submit to Sora 2 in background
    submit_video_job(
        job_id=job["id"],
        user_id=user_id,
        prompt=video_prompt,
        resolution=resolution,
        reference_image_path=ref_image_path,
    )

    return jsonify({
        "job_id": job["id"],
        "status": "pending",
        "generated_prompt": video_prompt,
    }), 202


@video_bp.route("/jobs", methods=["GET"])
@require_auth
def api_video_jobs():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    jobs = get_user_video_jobs(user_id)
    # Don't expose internal fields
    for j in jobs:
        if j.get("video_file"):
            j["video_url"] = f"/api/video/file/{j['video_file']}"
    return jsonify(jobs), 200


@video_bp.route("/jobs/<int:job_id>", methods=["GET"])
@require_auth
def api_video_job_status(job_id: int):
    job = get_video_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    # Verify ownership
    user_id = session.get("user_id")
    if job["user_id"] != user_id:
        return jsonify({"error": "Forbidden"}), 403
    if job.get("video_file"):
        job["video_url"] = f"/api/video/file/{job['video_file']}"
    return jsonify(job), 200


@video_bp.route("/file/<path:filename>", methods=["GET"])
@require_auth
def api_video_file(filename: str):
    from services.blob_sync import download_video_file_on_demand
    if not download_video_file_on_demand(filename):
        return jsonify({"error": "Video file not found"}), 404
    return send_from_directory(VIDEO_OUTPUT_DIR, filename, mimetype="video/mp4")


# --- Storyboard Mode ---

@video_bp.route("/storyboard/plan", methods=["POST"])
@require_auth
def api_storyboard_plan():
    """Split a script into scenes using GPT. Returns scene plan for review."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    script = (body.get("script") or "").strip()
    style = body.get("style", "animation")
    resolution = body.get("resolution", "1280x720")
    avatar_id = body.get("avatar_id")
    no_text_overlay = body.get("no_text_overlay", False)
    camera_style = body.get("camera_style", "slow-pan")
    color_mood = body.get("color_mood", "warm")
    nationality = body.get("nationality", "filipino")

    if not script:
        return jsonify({"error": "script is required"}), 400

    # Resolve avatar for character consistency
    avatar = None
    avatar_description = None
    if avatar_id and style == "animation":
        from db import get_avatar
        avatar = get_avatar(int(avatar_id))
        if avatar:
            avatar_description = avatar.get("description", "")

    # Build cohesion hints
    cohesion = {
        "no_text_overlay": no_text_overlay,
        "camera_style": camera_style,
        "color_mood": color_mood,
        "nationality": nationality,
    }

    try:
        scenes = split_script_into_scenes(
            script, style,
            avatar_description=avatar_description,
            cohesion=cohesion,
        )
        project = create_video_project(user_id, script, style, resolution)
        add_project_scenes(project["id"], scenes)

        full_project = get_video_project(project["id"])
        full_project["avatar_id"] = avatar_id
        return jsonify(full_project), 200
    except Exception as e:
        logger.exception("Storyboard planning failed")
        return jsonify({"error": str(e)}), 500


@video_bp.route("/storyboard/<int:project_id>/update-scene", methods=["PUT"])
@require_auth
def api_storyboard_update_scene(project_id: int):
    """Edit a scene prompt before generating."""
    project = get_video_project(project_id)
    if not project or project["user_id"] != session.get("user_id"):
        return jsonify({"error": "Not found"}), 404

    body = request.get_json(silent=True) or {}
    scene_id = body.get("scene_id")
    prompt = body.get("prompt")
    description = body.get("description")
    duration = body.get("duration")

    if not scene_id:
        return jsonify({"error": "scene_id required"}), 400

    from db import update_video_scene
    updates = {}
    if prompt is not None:
        updates["prompt"] = prompt
    if description is not None:
        updates["description"] = description
    if duration is not None and duration in (4, 8, 12):
        updates["duration"] = duration

    if updates:
        update_video_scene(scene_id, **updates)

    return jsonify({"ok": True}), 200


@video_bp.route("/storyboard/<int:project_id>/generate", methods=["POST"])
@require_auth
def api_storyboard_generate(project_id: int):
    """Start generating all scenes for a storyboard project."""
    user_id = session.get("user_id")
    project = get_video_project(project_id)
    if not project or project["user_id"] != user_id:
        return jsonify({"error": "Not found"}), 404

    if not check_user_video_quota(user_id):
        return jsonify({"error": "Video quota exhausted", "code": "VIDEO_QUOTA_EXHAUSTED"}), 429

    if project["status"] not in ("ready", "planning", "failed"):
        return jsonify({"error": f"Project already in status: {project['status']}"}), 400

    # Resolve avatar reference image for animation style
    body = request.get_json(silent=True) or {}
    avatar_id = body.get("avatar_id")
    ref_image_path = None
    if avatar_id and project["style"] == "animation":
        from db import get_avatar
        from services.image_gen import AVATAR_DIR
        avatar = get_avatar(int(avatar_id))
        if avatar:
            is_portrait = project["resolution"] == "720x1280"
            fname = avatar["portrait_file"] if is_portrait else avatar["landscape_file"]
            ref_image_path = os.path.join(AVATAR_DIR, fname)

    submit_storyboard(project_id, user_id, project["resolution"], ref_image_path)
    return jsonify({"status": "generating", "project_id": project_id}), 202


@video_bp.route("/storyboard/<int:project_id>/retry-scene/<int:scene_id>", methods=["POST"])
@require_auth
def api_storyboard_retry_scene(project_id: int, scene_id: int):
    """Retry a failed scene, then restitch when done."""
    user_id = session.get("user_id")
    project = get_video_project(project_id)
    if not project or project["user_id"] != user_id:
        return jsonify({"error": "Not found"}), 404

    scene = None
    for s in project.get("scenes", []):
        if s["id"] == scene_id:
            scene = s
            break
    if not scene or scene["status"] != "failed":
        return jsonify({"error": "Scene not found or not failed"}), 400

    # Resolve avatar reference image
    body = request.get_json(silent=True) or {}
    avatar_id = body.get("avatar_id")
    ref_image_path = None
    if avatar_id and project["style"] == "animation":
        from db import get_avatar as _get_av
        from services.image_gen import AVATAR_DIR as _ADIR
        av = _get_av(int(avatar_id))
        if av:
            is_portrait = project["resolution"] == "720x1280"
            fname = av["portrait_file"] if is_portrait else av["landscape_file"]
            ref_image_path = os.path.join(_ADIR, fname)

    from services.sora_video import retry_scene
    retry_scene(project_id, scene_id, user_id, project["resolution"], ref_image_path)

    return jsonify({"status": "retrying", "scene_id": scene_id}), 202


@video_bp.route("/storyboard/<int:project_id>/remix-scene/<int:scene_id>", methods=["POST"])
@require_auth
def api_storyboard_remix_scene(project_id: int, scene_id: int):
    """Remix a completed scene with an edited prompt using the Sora edit API."""
    user_id = session.get("user_id")
    project = get_video_project(project_id)
    if not project or project["user_id"] != user_id:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json(silent=True) or {}
    new_prompt = (body.get("prompt") or "").strip()
    if not new_prompt:
        return jsonify({"error": "prompt is required"}), 400

    scene = None
    for s in project.get("scenes", []):
        if s["id"] == scene_id:
            scene = s
            break
    if not scene:
        return jsonify({"error": "Scene not found"}), 404

    if scene["status"] not in ("completed", "failed"):
        return jsonify({"error": "Scene must be completed or failed to remix"}), 400

    from services.sora_video import remix_scene
    remix_scene(project_id, scene_id, new_prompt)

    return jsonify({"status": "remixing", "scene_id": scene_id}), 202


@video_bp.route("/storyboard/<int:project_id>", methods=["GET"])
@require_auth
def api_storyboard_status(project_id: int):
    """Get storyboard project status with all scenes."""
    project = get_video_project(project_id)
    if not project or project["user_id"] != session.get("user_id"):
        return jsonify({"error": "Not found"}), 404

    if project.get("final_video_file"):
        project["final_video_url"] = f"/api/video/file/{project['final_video_file']}"
    for scene in project.get("scenes", []):
        if scene.get("video_file"):
            scene["video_url"] = f"/api/video/file/{scene['video_file']}"
    return jsonify(project), 200


@video_bp.route("/storyboard", methods=["GET"])
@require_auth
def api_storyboard_list():
    """List user's storyboard projects."""
    user_id = session.get("user_id")
    projects = get_user_video_projects(user_id)
    for p in projects:
        if p.get("final_video_file"):
            p["final_video_url"] = f"/api/video/file/{p['final_video_file']}"
    return jsonify(projects), 200
