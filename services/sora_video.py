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

# Sora 2 currently accepts seconds in this set on Azure OpenAI. Update when
# Azure exposes additional values.
ALLOWED_SCENE_DURATIONS = (4, 8, 12)
DEFAULT_SCENE_DURATION = 12

# Hard limits on scene count so the LLM cannot blow user quota.
MIN_SCENES = 4
MAX_SCENES = 10

_client = None


def _upload_video(filename: str):
    """Upload video to blob in background. Non-blocking."""
    try:
        from services.blob_sync import upload_video_file_to_blob
        upload_video_file_to_blob(filename)
    except Exception:
        pass


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
                    _upload_video(filename)
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


def _responses_text(client: OpenAI, instructions: str, user_text: str) -> str:
    """Run a single GPT responses.create call and return the flat text output."""
    response = client.responses.create(
        model=AZURE_OPENAI_DEPLOYMENT,
        instructions=instructions,
        input=[{"role": "user", "content": [{"type": "input_text", "text": user_text}]}],
    )
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()
    parts = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            t = getattr(content, "text", None)
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    if text.startswith("json"):
        text = text[4:].strip()
    return text


# Shared mapping used by both planner cohesion block and per-scene camera override.
_CAMERA_MAP = {
    "static": "static locked camera",
    "slow-pan": "smooth slow panning camera",
    "dolly": "cinematic dolly movement",
    "orbit": "gentle orbital camera",
    "handheld": "slight handheld camera motion",
}


def _camera_hint(camera_style: str | None) -> str:
    """Translate a camera_style code into a Sora-friendly description, or '' if unknown."""
    if not camera_style:
        return ""
    return _CAMERA_MAP.get(camera_style, camera_style)


def _cohesion_block(cohesion: dict | None, avatar_description: str | None) -> str:
    """Build the shared cohesion + avatar guidance string used by all planner stages."""
    extra = ""
    if avatar_description:
        extra += f"\n\nMAIN CHARACTER (must appear in every scene unless a different asset is explicitly assigned): {avatar_description}."

    if not cohesion:
        return extra

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

    camera_map = _CAMERA_MAP
    mood_map = {
        "warm": "warm golden tones", "cool": "cool blue tones",
        "neutral": "neutral balanced colors", "vibrant": "vibrant saturated colors",
        "pastel": "soft pastel palette",
    }

    extra += "\n\nCOHESION RULES for ALL scenes:"
    extra += f"\n- Nationality/ethnicity: people, settings, architecture, and cultural context are {nat_label}."
    extra += f"\n- Camera: {camera_map.get(camera, camera)} in every scene."
    extra += f"\n- Color mood: {mood_map.get(mood, mood)} consistent across all scenes."
    if no_text:
        extra += "\n- CRITICAL: Do NOT include any text, words, titles, letters, or numbers visible in the video. Pure visual only."
    return extra


def _format_asset_bank(assets: list[dict] | None) -> str:
    """Render the asset bank into a compact string for the scene planner."""
    if not assets:
        return ""
    lines = ["AVAILABLE REFERENCE ASSETS (you may assign one per scene by id, or leave null):"]
    for a in assets:
        asset_type = a.get("asset_type", "character")
        desc = (a.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 220:
            desc = desc[:217] + "..."
        lines.append(f"- id={a['id']} | type={asset_type} | name={a['name']} | desc={desc}")
    return "\n".join(lines)


def director_brief(
    script: str,
    style: str,
    cohesion: dict | None = None,
    avatar_description: str | None = None,
) -> str:
    """Stage 1: produce a creative brief that anchors the whole video."""
    from config import DIRECTOR_BRIEF_PROMPT
    client = _get_client()
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["animation"])
    instructions = (
        DIRECTOR_BRIEF_PROMPT
        + f"\n\nVISUAL STYLE: {style_instruction}"
        + _cohesion_block(cohesion, avatar_description)
    )
    return _responses_text(client, instructions, script)


def plan_scenes(
    brief: str,
    script: str,
    available_assets: list[dict] | None = None,
) -> list[dict]:
    """Stage 2: break the script into N scenes (no Sora prompts yet)."""
    import json as _json
    from config import SCENE_PLANNER_PROMPT

    client = _get_client()
    asset_block = _format_asset_bank(available_assets)
    user_payload = (
        f"DIRECTOR BRIEF:\n{brief}\n\n"
        f"SCRIPT:\n{script}\n\n"
        f"{asset_block}"
    ).strip()

    text = _strip_json_fence(_responses_text(client, SCENE_PLANNER_PROMPT, user_payload))
    scenes = _json.loads(text)

    # Validate / clamp
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Scene planner returned empty or invalid output")

    if len(scenes) < MIN_SCENES:
        logger.warning(f"Scene planner returned {len(scenes)} scenes; below minimum {MIN_SCENES}")
    if len(scenes) > MAX_SCENES:
        logger.warning(f"Scene planner returned {len(scenes)} scenes; truncating to {MAX_SCENES}")
        scenes = scenes[:MAX_SCENES]

    valid_asset_ids = {a["id"] for a in (available_assets or [])}
    for i, s in enumerate(scenes):
        s["scene_number"] = i + 1
        dur = s.get("duration", DEFAULT_SCENE_DURATION)
        if dur not in ALLOWED_SCENE_DURATIONS:
            dur = DEFAULT_SCENE_DURATION
        s["duration"] = dur
        ref = s.get("reference_asset_id")
        if ref is not None and ref not in valid_asset_ids:
            ref = None
        s["reference_asset_id"] = ref
        s.setdefault("description", "")
    return scenes


def plan_shot(
    brief: str,
    scene: dict,
    style: str,
    cohesion: dict | None = None,
    avatar_description: str | None = None,
    asset_description: str | None = None,
) -> str:
    """Stage 3: turn ONE scene into a single Sora 2 prompt."""
    from config import SHOT_PLANNER_PROMPT
    client = _get_client()
    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["animation"])

    instructions = (
        SHOT_PLANNER_PROMPT
        + f"\n\nVISUAL STYLE: {style_instruction}"
        + _cohesion_block(cohesion, avatar_description)
    )

    asset_line = ""
    if asset_description:
        asset_line = f"\nASSIGNED REFERENCE ASSET (describe explicitly): {asset_description}"

    user_payload = (
        f"DIRECTOR BRIEF:\n{brief}\n\n"
        f"SCENE {scene['scene_number']} ({scene['duration']}s):\n{scene.get('description', '')}"
        f"{asset_line}"
    )
    return _responses_text(client, instructions, user_payload)


def plan_storyboard(
    script: str,
    style: str,
    cohesion: dict | None = None,
    avatar_description: str | None = None,
    available_assets: list[dict] | None = None,
) -> dict:
    """Run the full director -> scene planner -> shot planner pipeline.

    Returns: {"director_brief": str, "scenes": [{scene_number, description, duration, prompt, reference_asset_id}]}
    Shot planning runs in parallel across scenes (one GPT call per scene).
    """
    import concurrent.futures

    brief = director_brief(script, style, cohesion, avatar_description)
    scenes = plan_scenes(brief, script, available_assets)

    # Build id -> description lookup so shot planner can describe assigned assets
    asset_desc_by_id = {a["id"]: a.get("description", "") for a in (available_assets or [])}

    def _shot(scene: dict) -> dict:
        asset_desc = asset_desc_by_id.get(scene.get("reference_asset_id"))
        prompt = plan_shot(
            brief, scene, style,
            cohesion=cohesion,
            avatar_description=avatar_description if not asset_desc else None,
            asset_description=asset_desc,
        )
        scene["prompt"] = prompt
        return scene

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(scenes), 5)) as pool:
        scenes = list(pool.map(_shot, scenes))

    return {"director_brief": brief, "scenes": scenes}


def split_script_into_scenes(
    script: str,
    style: str,
    avatar_description: str | None = None,
    cohesion: dict | None = None,
) -> list[dict]:
    """Backwards-compatible wrapper. Prefer plan_storyboard() in new code."""
    result = plan_storyboard(script, style, cohesion=cohesion, avatar_description=avatar_description)
    return result["scenes"]


def submit_storyboard(project_id: int, user_id: int, resolution: str, reference_image_path: str | None = None):
    """Generate all scenes for a storyboard project, then stitch.

    Scene-level reference image precedence (highest -> lowest):
      1. scene.reference_asset_id (per-scene avatar/asset)
      2. previous scene's last frame (only if project.chain_frames is on)
      3. project-level fallback reference_image_path (the project avatar)

    When chain_frames is on, scenes run STRICTLY sequentially so each can use the
    previous scene's last frame. Otherwise scenes run 2-at-a-time (Sora 2 concurrency cap).
    """

    def _run():
        try:
            from db import (
                get_video_project, update_video_scene, update_video_project,
                count_completed_scenes, get_project_scene_files, increment_user_videos,
                get_avatar,
            )
            from services.image_gen import AVATAR_DIR

            project = get_video_project(project_id)
            if not project:
                return

            scenes = project["scenes"]
            chain_frames = bool(project.get("chain_frames"))
            is_portrait = project["resolution"] == "720x1280"
            update_video_project(project_id, status="generating")

            client = _get_client()

            def _resolve_scene_ref(scene: dict, prev_frame_path: str | None) -> str | None:
                """Pick the best reference image for this scene."""
                ref_id = scene.get("reference_asset_id")
                if ref_id:
                    av = get_avatar(int(ref_id))
                    if av:
                        fname = av["portrait_file"] if is_portrait else av["landscape_file"]
                        candidate = os.path.join(AVATAR_DIR, fname)
                        if os.path.exists(candidate):
                            return candidate
                if chain_frames and prev_frame_path and os.path.exists(prev_frame_path):
                    return prev_frame_path
                if reference_image_path and os.path.exists(reference_image_path):
                    return reference_image_path
                return None

            def _generate_scene(scene: dict, scene_ref_path: str | None) -> bool:
                scene_id = scene["id"]
                try:
                    ref_label = "no reference"
                    if scene_ref_path:
                        ref_label = f"reference={os.path.basename(scene_ref_path)}"

                    # Apply per-scene camera override (winner over project default).
                    # We append a hint to the prompt rather than re-running shot planner.
                    effective_prompt = scene["prompt"]
                    scene_camera = (scene.get("camera_style") or "").strip()
                    if scene_camera:
                        cam_hint = _camera_hint(scene_camera)
                        if cam_hint:
                            effective_prompt = f"{effective_prompt}\n\nCAMERA OVERRIDE: {cam_hint}. Use this camera movement only; ignore any conflicting camera direction earlier in the prompt."

                    logger.info(
                        f"[Sora] Starting scene {scene['scene_number']}/{len(scenes)} "
                        f"(project={project_id}, duration={scene.get('duration', DEFAULT_SCENE_DURATION)}s, "
                        f"chain={chain_frames}, camera={scene_camera or 'project-default'}, {ref_label})"
                    )
                    update_video_scene(scene_id, status="submitting")

                    create_kwargs = {
                        "model": AZURE_OPENAI_SORA_DEPLOYMENT,
                        "prompt": effective_prompt,
                        "size": resolution,
                        "seconds": scene.get("duration", DEFAULT_SCENE_DURATION),
                    }

                    ref_fh = None
                    try:
                        if scene_ref_path:
                            ref_fh = open(scene_ref_path, "rb")
                            create_kwargs["input_reference"] = ref_fh
                        video = client.videos.create(**create_kwargs)
                    finally:
                        if ref_fh is not None:
                            try:
                                ref_fh.close()
                            except Exception:
                                pass

                    update_video_scene(scene_id, status="queued", sora_video_id=video.id)
                    logger.info(f"[Sora] Scene {scene['scene_number']} queued as {video.id} — polling every 15s")

                    poll_count = 0
                    last_logged_status = None
                    while True:
                        time.sleep(15)
                        poll_count += 1
                        video = client.videos.retrieve(video.id)
                        status = video.status
                        progress = getattr(video, "progress", 0) or 0

                        # Log on status change OR every 4 polls (~1 min) so terminal stays alive
                        if status != last_logged_status or poll_count % 4 == 0:
                            elapsed = poll_count * 15
                            logger.info(
                                f"[Sora] Scene {scene['scene_number']} status={status} progress={progress}% "
                                f"elapsed={elapsed}s"
                            )
                            last_logged_status = status

                        if status == "completed":
                            filename = f"scene-{project_id}-{scene['scene_number']}.mp4"
                            filepath = os.path.join(VIDEO_OUTPUT_DIR, filename)
                            content = client.videos.download_content(video.id, variant="video")
                            content.write_to_file(filepath)
                            update_video_scene(scene_id, status="completed", progress=100, video_file=filename)
                            _upload_video(filename)

                            done = count_completed_scenes(project_id)
                            update_video_project(project_id, completed_scenes=done)
                            logger.info(f"Scene {scene['scene_number']}/{len(scenes)} completed for project {project_id}")
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

            all_ok = True

            if chain_frames:
                # Sequential mode: each scene N+1 uses scene N's last frame as reference
                prev_frame_path: str | None = None
                for scene in scenes:
                    scene_ref = _resolve_scene_ref(scene, prev_frame_path)
                    ok = _generate_scene(scene, scene_ref)
                    if not ok:
                        all_ok = False
                        prev_frame_path = None
                        continue
                    # Extract last frame for next iteration
                    scene_file = f"scene-{project_id}-{scene['scene_number']}.mp4"
                    frame_file = f"frame-{project_id}-{scene['scene_number']}.png"
                    frame_path = os.path.join(VIDEO_OUTPUT_DIR, frame_file)
                    video_path = os.path.join(VIDEO_OUTPUT_DIR, scene_file)
                    if _extract_last_frame(video_path, frame_path):
                        update_video_scene(scene["id"], previous_frame_file=frame_file)
                        prev_frame_path = frame_path
                    else:
                        prev_frame_path = None
            else:
                # Parallel mode: batches of 2 (Sora 2 concurrency cap)
                import concurrent.futures
                for batch_start in range(0, len(scenes), 2):
                    batch = scenes[batch_start:batch_start + 2]
                    refs = [_resolve_scene_ref(s, None) for s in batch]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(lambda pair: _generate_scene(pair[0], pair[1]), zip(batch, refs)))
                    if not all(results):
                        all_ok = False

            if not all_ok:
                done = count_completed_scenes(project_id)
                if done == 0:
                    update_video_project(project_id, status="failed", error="All scenes failed")
                    return

            # Stitch
            update_video_project(project_id, status="stitching")
            scene_files = get_project_scene_files(project_id)
            if not scene_files:
                update_video_project(project_id, status="failed", error="No scene videos to stitch")
                return

            final_filename = f"project-{project_id}-final.mp4"
            _stitch_videos(scene_files, final_filename)

            update_video_project(project_id, status="completed", final_video_file=final_filename)
            increment_user_videos(user_id)
            _upload_video(final_filename)
            logger.info(f"Storyboard project {project_id} completed: {final_filename}")

        except Exception as exc:
            logger.exception(f"Storyboard project {project_id} error")
            update_video_project(project_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _stitch_videos(scene_files: list[str], output_filename: str):
    """Stitch scene videos together using ffmpeg.

    Uses the concat FILTER (not the demuxer) with explicit per-stream normalization
    so the final clip is never truncated. Sora 2 emits each scene with audio, so we
    keep audio (a=1). To stay safe against any future scene that lacks an audio
    track, we probe each input and synthesize silence when missing.
    """
    import subprocess, json

    scene_paths = [os.path.join(VIDEO_OUTPUT_DIR, f) for f in scene_files]
    output_path = os.path.join(VIDEO_OUTPUT_DIR, output_filename)

    if len(scene_paths) == 1:
        import shutil
        shutil.copy2(scene_paths[0], output_path)
        return

    # Probe each input: detect audio + duration (needed for silent-track injection).
    def _probe(path: str) -> tuple[bool, float]:
        try:
            out = subprocess.check_output([
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_streams", "-show_format", path,
            ], timeout=15)
            info = json.loads(out)
            has_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
            duration = float(info.get("format", {}).get("duration") or 0)
            return has_audio, duration
        except Exception:
            return False, 0.0

    probes = [_probe(p) for p in scene_paths]

    # Build input list. For inputs without audio, append a silent anullsrc input.
    cmd: list[str] = ["ffmpeg", "-y", "-fflags", "+genpts"]
    for p in scene_paths:
        cmd += ["-i", p]
    # Index of the silent generator input (added after all real inputs, if needed).
    n = len(scene_paths)
    silent_input_idx = None
    if any(not has_audio for has_audio, _ in probes):
        cmd += [
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        ]
        silent_input_idx = n  # the lavfi input's stream index

    norm_parts: list[str] = []
    concat_inputs: list[str] = []
    for i, (has_audio, duration) in enumerate(probes):
        norm_parts.append(f"[{i}:v]fps=30,setsar=1,format=yuv420p[v{i}]")
        if has_audio:
            norm_parts.append(
                f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo:sample_fmts=fltp[a{i}]"
            )
        else:
            # Pull a trimmed slice of silence sized to this scene's duration.
            dur = max(duration, 0.1)
            norm_parts.append(
                f"[{silent_input_idx}:a]atrim=duration={dur:.3f},asetpts=N/SR/TB,"
                f"aresample=48000,aformat=channel_layouts=stereo:sample_fmts=fltp[a{i}]"
            )
        concat_inputs.append(f"[v{i}][a{i}]")

    filter_complex = ";".join(norm_parts) + f";{''.join(concat_inputs)}concat=n={n}:v=1:a=1[out][outa]"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"[Stitch] Concatenated {n} scenes (with audio) -> {output_filename}")
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="ignore")[-2000:]
        logger.error(f"[Stitch] ffmpeg failed: {stderr}")
        raise


def _extract_last_frame(video_path: str, output_png_path: str) -> bool:
    """Extract the final frame of a video to a PNG using ffmpeg.

    Returns True on success. Used for last-frame chaining in storyboard mode so the
    next scene can use the previous scene's final frame as its input_reference image.
    """
    import subprocess

    if not os.path.exists(video_path):
        return False
    try:
        # -sseof -0.1 seeks 0.1s before EOF; grabbing 1 frame from there gives the last frame.
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-sseof", "-0.1",
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                output_png_path,
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return os.path.exists(output_png_path)
    except Exception as exc:
        logger.warning(f"Last-frame extraction failed for {video_path}: {exc}")
        return False


def retry_scene(project_id: int, scene_id: int, user_id: int, resolution: str, reference_image_path: str | None = None):
    """Retry a single failed scene, then restitch the project.

    Honours scene.reference_asset_id (per-scene asset) first; otherwise falls back
    to the project-level reference_image_path or the previous scene's last frame.
    """

    def _run():
        try:
            from db import (
                get_video_project, update_video_scene, update_video_project,
                count_completed_scenes, get_project_scene_files, get_avatar,
            )
            from services.image_gen import AVATAR_DIR

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

            # Resolve reference image: per-scene asset > project chain prev-frame > project avatar
            chain_frames = bool(project.get("chain_frames"))
            is_portrait = project["resolution"] == "720x1280"
            scene_ref_path: str | None = None

            ref_id = scene.get("reference_asset_id")
            if ref_id:
                av = get_avatar(int(ref_id))
                if av:
                    fname = av["portrait_file"] if is_portrait else av["landscape_file"]
                    candidate = os.path.join(AVATAR_DIR, fname)
                    if os.path.exists(candidate):
                        scene_ref_path = candidate

            if not scene_ref_path and chain_frames:
                # Use the previous scene's stored last frame if available
                scenes_sorted = sorted(project["scenes"], key=lambda s: s["scene_number"])
                for prev in scenes_sorted:
                    if prev["scene_number"] >= scene["scene_number"]:
                        break
                    pf = prev.get("previous_frame_file")
                    if pf:
                        candidate = os.path.join(VIDEO_OUTPUT_DIR, pf)
                        if os.path.exists(candidate):
                            scene_ref_path = candidate

            if not scene_ref_path and reference_image_path and os.path.exists(reference_image_path):
                scene_ref_path = reference_image_path

            client = _get_client()
            update_video_scene(scene_id, status="submitting", error="")

            create_kwargs = {
                "model": AZURE_OPENAI_SORA_DEPLOYMENT,
                "prompt": scene["prompt"],
                "size": resolution,
                "seconds": scene.get("duration", DEFAULT_SCENE_DURATION),
            }

            ref_fh = None
            try:
                if scene_ref_path:
                    ref_fh = open(scene_ref_path, "rb")
                    create_kwargs["input_reference"] = ref_fh
                video = client.videos.create(**create_kwargs)
            finally:
                if ref_fh is not None:
                    try:
                        ref_fh.close()
                    except Exception:
                        pass

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
                    _upload_video(filename)

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
                        _upload_video(final_filename)
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


def remix_scene(project_id: int, scene_id: int, new_prompt: str):
    """Edit/remix a completed scene using the Sora edit API, then restitch."""

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

            source_video_id = scene.get("sora_video_id")
            if not source_video_id:
                logger.warning(f"Remix scene {scene_id}: no source sora_video_id, falling back to create")

            # Apply per-scene camera override at submit time (same logic as fresh gen).
            effective_prompt = new_prompt
            scene_camera = (scene.get("camera_style") or "").strip()
            if scene_camera:
                cam_hint = _camera_hint(scene_camera)
                if cam_hint:
                    effective_prompt = (
                        f"{effective_prompt}\n\nCAMERA OVERRIDE: {cam_hint}. "
                        "Use this camera movement only; ignore any conflicting camera direction earlier in the prompt."
                    )

            client = _get_client()
            update_video_scene(scene_id, status="remixing", prompt=new_prompt, error="")

            if source_video_id:
                # Use REMIX API — regenerates the same scene with a new prompt, anchored to
                # the original video. (videos.edit is for inpainting/masked edits; videos.remix
                # is the correct call for a prompt-only re-take of a completed scene.)
                try:
                    video = client.videos.remix(
                        video_id=source_video_id,
                        prompt=effective_prompt,
                    )
                except Exception as remix_exc:
                    logger.error(f"Remix scene {scene_id}: videos.remix failed ({remix_exc}); regenerating from scratch")
                    video = client.videos.create(
                        model=AZURE_OPENAI_SORA_DEPLOYMENT,
                        prompt=effective_prompt,
                        size=project["resolution"],
                        seconds=scene.get("duration", 12),
                    )
            else:
                # Fallback to create from scratch
                video = client.videos.create(
                    model=AZURE_OPENAI_SORA_DEPLOYMENT,
                    prompt=effective_prompt,
                    size=project["resolution"],
                    seconds=scene.get("duration", 12),
                )

            update_video_scene(scene_id, status="queued", sora_video_id=video.id)

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
                    _upload_video(filename)

                    done = count_completed_scenes(project_id)
                    total = project["total_scenes"]
                    update_video_project(project_id, completed_scenes=done)

                    # Restitch if all scenes are complete
                    if done == total:
                        update_video_project(project_id, status="stitching")
                        scene_files = get_project_scene_files(project_id)
                        final_filename = f"project-{project_id}-final.mp4"
                        _stitch_videos(scene_files, final_filename)
                        update_video_project(project_id, status="completed", final_video_file=final_filename)
                        _upload_video(final_filename)
                        logger.info(f"Remix restitch completed for project {project_id}")
                    break

                elif status in ("failed", "cancelled"):
                    err = str(getattr(video, "error", "")) or f"Remix {status}"
                    update_video_scene(scene_id, status="failed", error=err)
                    break
                else:
                    update_video_scene(scene_id, status=status, progress=progress)

        except Exception as exc:
            logger.exception(f"Remix scene {scene_id} error")
            update_video_scene(scene_id, status="failed", error=str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
