import os
import time
import logging
import threading

from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from config import (
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_SORA_DEPLOYMENT, VIDEO_OUTPUT_DIR,
    SORA_PROMPT_SYSTEM,
)
from db import update_video_job, increment_user_videos

logger = logging.getLogger(__name__)

os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        endpoint = (AZURE_OPENAI_ENDPOINT or "").rstrip("/")
        for suffix in ["/openai/v1", "/openai"]:
            if endpoint.endswith(suffix):
                endpoint = endpoint[:-len(suffix)]
                break
        base_url = f"{endpoint}/openai/v1/"
        _client = OpenAI(base_url=base_url, api_key=token_provider)
    return _client


# --- Style prompt fragments ---
STYLE_PROMPTS = {
    "animation": "Style: Colorful 3D animation with smooth character movements, vibrant colors, and clean stylized environments. Pixar-like quality with warm lighting.",
    "cinematic": "Style: Photorealistic cinematic footage with professional color grading, shallow depth of field, and smooth camera movements. Film-quality lighting.",
    "motion-graphics": "Style: Clean motion graphics with geometric shapes, smooth transitions, brand-colored elements (blue and gold), and dynamic text animations on a clean background.",
    "illustration": "Style: Hand-drawn illustration style with watercolor textures, gentle line work, and soft pastel colors. The illustrations come alive with subtle, organic animation.",
}


def generate_video_prompt(script: str, style: str, extra_instructions: str = "") -> str:
    """Use GPT to convert a marketing script into a Sora 2 visual prompt."""
    client = _get_client()

    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["animation"])

    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=SORA_PROMPT_SYSTEM + f"\n\n{style_instruction}",
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": script}],
            },
        ],
    )

    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    output = getattr(response, "output", []) or []
    parts = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def submit_video_job(
    job_id: int,
    user_id: int,
    prompt: str,
    resolution: str = "1280x720",
    reference_image_path: str | None = None,
):
    """Submit video generation to Sora 2 and poll in a background thread."""

    def _run():
        try:
            client = _get_client()
            size = resolution  # e.g. "1280x720" or "720x1280"

            create_kwargs = {
                "model": AZURE_OPENAI_SORA_DEPLOYMENT,
                "prompt": prompt,
                "size": size,
                "seconds": 12,
            }

            if reference_image_path and os.path.exists(reference_image_path):
                create_kwargs["input_reference"] = open(reference_image_path, "rb")

            update_video_job(job_id, status="submitting")

            video = client.videos.create(**create_kwargs)
            sora_id = video.id

            update_video_job(job_id, status="queued", sora_video_id=sora_id, progress=0)

            # Poll for completion
            while True:
                time.sleep(15)
                video = client.videos.retrieve(sora_id)
                status = video.status
                progress = getattr(video, "progress", 0) or 0

                if status == "completed":
                    update_video_job(job_id, status="downloading", progress=90)

                    # Download video
                    filename = f"video-{job_id}.mp4"
                    filepath = os.path.join(VIDEO_OUTPUT_DIR, filename)
                    content = client.videos.download_content(sora_id, variant="video")
                    content.write_to_file(filepath)

                    update_video_job(job_id, status="completed", progress=100, video_file=filename)
                    increment_user_videos(user_id)
                    logger.info(f"Video job {job_id} completed: {filename}")
                    break

                elif status == "failed":
                    err = getattr(video, "error", None)
                    error_msg = str(err) if err else "Video generation failed"
                    update_video_job(job_id, status="failed", error=error_msg)
                    logger.warning(f"Video job {job_id} failed: {error_msg}")
                    break

                elif status == "cancelled":
                    update_video_job(job_id, status="cancelled", error="Job was cancelled")
                    break

                else:
                    update_video_job(job_id, status=status, progress=progress)

        except Exception as exc:
            logger.exception(f"Video job {job_id} error")
            update_video_job(job_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


# --- Storyboard Mode ---

def split_script_into_scenes(script: str, style: str, avatar_description: str | None = None, cohesion: dict | None = None) -> list[dict]:
    """Use GPT to break a script into visual scenes with Sora 2 prompts."""
    import json as _json
    from config import SCENE_SPLITTER_PROMPT

    client = _get_client()
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["animation"])

    extra = ""
    if avatar_description:
        extra += f"\n\nIMPORTANT: The main character in EVERY scene must be: {avatar_description}. Include this exact description in every scene prompt for visual consistency."

    if cohesion:
        camera = cohesion.get("camera_style", "slow-pan")
        mood = cohesion.get("color_mood", "warm")
        no_text = cohesion.get("no_text_overlay", False)
        nat = cohesion.get("nationality", "filipino")

        nationality_map = {
            "filipino": "Filipino/Philippine", "chinese": "Chinese", "indian": "Indian",
            "thai": "Thai", "indonesian": "Indonesian", "malay": "Malaysian",
            "vietnamese": "Vietnamese", "japanese": "Japanese", "korean": "Korean",
            "singaporean": "Singaporean",
        }
        nat_label = nationality_map.get(nat, nat.capitalize())

        camera_map = {"static": "static locked camera", "slow-pan": "smooth slow panning camera", "dolly": "cinematic dolly movement", "orbit": "gentle orbital camera", "handheld": "slight handheld camera motion"}
        mood_map = {"warm": "warm golden tones", "cool": "cool blue tones", "neutral": "neutral balanced colors", "vibrant": "vibrant saturated colors", "pastel": "soft pastel palette"}

        extra += f"\n\nCOHESION RULES for ALL scenes:"
        extra += f"\n- Nationality/ethnicity: All people/characters MUST be {nat_label}. Use {nat_label} settings, architecture, urban/rural environments, and cultural context."
        extra += f"\n- Camera: {camera_map.get(camera, camera)} in every scene"
        extra += f"\n- Color mood: {mood_map.get(mood, mood)} consistent across all scenes"
        if no_text:
            extra += "\n- CRITICAL: Do NOT include any text, words, titles, letters, numbers, or written content visible in the video. Pure visual only."

    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=SCENE_SPLITTER_PROMPT + f"\n\n{style_instruction}{extra}",
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": script}],
            },
        ],
    )

    text = getattr(response, "output_text", None)
    if not text:
        output = getattr(response, "output", []) or []
        parts = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                t = getattr(content, "text", None)
                if t:
                    parts.append(t)
        text = "\n".join(parts)

    # Parse JSON from response (strip markdown fences if present)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()

    scenes = _json.loads(text)
    # Validate
    for i, s in enumerate(scenes):
        s["scene_number"] = i + 1
        s["duration"] = s.get("duration", 12)
        if s["duration"] not in (4, 8, 12):
            s["duration"] = 12
    return scenes


def submit_storyboard(project_id: int, user_id: int, resolution: str, reference_image_path: str | None = None):
    """Generate all scenes for a storyboard project, 2 at a time, then stitch."""

    def _run():
        try:
            from db import (
                get_video_project, update_video_scene, update_video_project,
                count_completed_scenes, get_project_scene_files, increment_user_videos,
            )

            project = get_video_project(project_id)
            if not project:
                return

            scenes = project["scenes"]
            update_video_project(project_id, status="generating")

            client = _get_client()

            # Process scenes in batches of 2 (Sora 2 max concurrent = 2)
            import concurrent.futures

            def _generate_scene(scene):
                scene_id = scene["id"]
                try:
                    update_video_scene(scene_id, status="submitting")

                    create_kwargs = {
                        "model": AZURE_OPENAI_SORA_DEPLOYMENT,
                        "prompt": scene["prompt"],
                        "size": resolution,
                        "seconds": scene.get("duration", 12),
                    }

                    # Pass avatar reference image for animation consistency
                    if reference_image_path and os.path.exists(reference_image_path):
                        create_kwargs["input_reference"] = open(reference_image_path, "rb")

                    video = client.videos.create(**create_kwargs)

                    update_video_scene(scene_id, status="queued", sora_video_id=video.id)

                    # Poll
                    while True:
                        time.sleep(15)
                        video = client.videos.retrieve(video.id)
                        status = video.status
                        progress = getattr(video, "progress", 0) or 0

                        if status == "completed":
                            filename = f"scene-{project_id}-{scene['scene_number']}.mp4"
                            filepath = os.path.join(VIDEO_OUTPUT_DIR, filename)
                            content = client.videos.download_content(video.id, variant="video")
                            content.write_to_file(filepath)
                            update_video_scene(scene_id, status="completed", progress=100, video_file=filename)

                            # Update project progress
                            done = count_completed_scenes(project_id)
                            total = len(scenes)
                            update_video_project(project_id, completed_scenes=done)
                            logger.info(f"Scene {scene['scene_number']}/{total} completed for project {project_id}")
                            return True

                        elif status in ("failed", "cancelled"):
                            err = str(getattr(video, "error", "")) or f"Scene {status}"
                            update_video_scene(scene_id, status="failed", error=err)
                            return False

                        else:
                            update_video_scene(scene_id, status=status, progress=progress)

                except Exception as exc:
                    logger.warning(f"Scene {scene_id} error: {exc}")
                    update_video_scene(scene_id, status="failed", error=str(exc))
                    return False

            # Run in batches of 2
            all_ok = True
            for batch_start in range(0, len(scenes), 2):
                batch = scenes[batch_start:batch_start + 2]
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(_generate_scene, batch))
                if not all(results):
                    all_ok = False

            if not all_ok:
                # Check if enough scenes completed
                done = count_completed_scenes(project_id)
                if done == 0:
                    update_video_project(project_id, status="failed", error="All scenes failed")
                    return

            # Stitch with ffmpeg
            update_video_project(project_id, status="stitching")

            scene_files = get_project_scene_files(project_id)
            if not scene_files:
                update_video_project(project_id, status="failed", error="No scene videos to stitch")
                return

            final_filename = f"project-{project_id}-final.mp4"
            _stitch_videos(scene_files, final_filename)

            update_video_project(project_id, status="completed", final_video_file=final_filename)
            increment_user_videos(user_id)
            logger.info(f"Storyboard project {project_id} completed: {final_filename}")

        except Exception as exc:
            logger.exception(f"Storyboard project {project_id} error")
            update_video_project(project_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _stitch_videos(scene_files: list[str], output_filename: str):
    """Stitch scene videos together using ffmpeg with crossfade transitions."""
    import subprocess
    import tempfile

    scene_paths = [os.path.join(VIDEO_OUTPUT_DIR, f) for f in scene_files]
    output_path = os.path.join(VIDEO_OUTPUT_DIR, output_filename)

    if len(scene_paths) == 1:
        # Just copy
        import shutil
        shutil.copy2(scene_paths[0], output_path)
        return

    # Create concat file for ffmpeg
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in scene_paths:
            f.write(f"file '{path}'\n")
        concat_file = f.name

    try:
        # Simple concat with re-encoding for consistency
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                "-movflags", "+faststart",
                output_path,
            ],
            check=True,
            capture_output=True,
        )
    finally:
        os.unlink(concat_file)


def retry_scene(project_id: int, scene_id: int, user_id: int, resolution: str, reference_image_path: str | None = None):
    """Retry a single failed scene, then restitch the project."""

    def _run():
        try:
            from db import (
                get_video_project, update_video_scene, update_video_project,
                count_completed_scenes, get_project_scene_files,
            )

            project = get_video_project(project_id)
            if not project:
                return

            scene = None
            for s in project["scenes"]:
                if s["id"] == scene_id:
                    scene = s
                    break
            if not scene:
                return

            client = _get_client()
            update_video_scene(scene_id, status="submitting", error="")

            create_kwargs = {
                "model": AZURE_OPENAI_SORA_DEPLOYMENT,
                "prompt": scene["prompt"],
                "size": resolution,
                "seconds": scene.get("duration", 12),
            }
            if reference_image_path and os.path.exists(reference_image_path):
                create_kwargs["input_reference"] = open(reference_image_path, "rb")

            video = client.videos.create(**create_kwargs)
            update_video_scene(scene_id, status="queued", sora_video_id=video.id)

            # Poll
            while True:
                time.sleep(15)
                video = client.videos.retrieve(video.id)
                status = video.status
                progress = getattr(video, "progress", 0) or 0

                if status == "completed":
                    filename = f"scene-{project_id}-{scene['scene_number']}.mp4"
                    filepath = os.path.join(VIDEO_OUTPUT_DIR, filename)
                    content = client.videos.download_content(video.id, variant="video")
                    content.write_to_file(filepath)
                    update_video_scene(scene_id, status="completed", progress=100, video_file=filename)

                    done = count_completed_scenes(project_id)
                    total = project["total_scenes"]
                    update_video_project(project_id, completed_scenes=done)

                    # Restitch if all scenes now complete
                    if done == total:
                        update_video_project(project_id, status="stitching")
                        scene_files = get_project_scene_files(project_id)
                        final_filename = f"project-{project_id}-final.mp4"
                        _stitch_videos(scene_files, final_filename)
                        update_video_project(project_id, status="completed", final_video_file=final_filename)
                        logger.info(f"Restitch completed for project {project_id}")
                    break

                elif status in ("failed", "cancelled"):
                    err = str(getattr(video, "error", "")) or f"Scene retry {status}"
                    update_video_scene(scene_id, status="failed", error=err)
                    break
                else:
                    update_video_scene(scene_id, status=status, progress=progress)

        except Exception as exc:
            logger.exception(f"Scene retry {scene_id} error")
            update_video_scene(scene_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
