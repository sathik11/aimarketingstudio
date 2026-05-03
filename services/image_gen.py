import base64
import os
import logging
import uuid

from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from PIL import Image
from io import BytesIO

from config import AZURE_OPENAI_IMAGE_ENDPOINT, AZURE_OPENAI_IMAGE_DEPLOYMENT

logger = logging.getLogger(__name__)

AVATAR_DIR = os.path.abspath("static/avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

# Quality presets: maps user-facing quality to gpt-image-2 params
QUALITY_PRESETS = {
    "low":    {"size": "1024x1024", "quality": "low"},
    "medium": {"size": "1024x1024", "quality": "medium"},
    "high":   {"size": "1536x1024", "quality": "high"},
}

_client = None


def _get_client() -> OpenAI:
    """Client for gpt-image-2 in eastus2 region."""
    global _client
    if _client is None:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        endpoint = (AZURE_OPENAI_IMAGE_ENDPOINT or "").rstrip("/")
        for suffix in ["/openai/v1", "/openai"]:
            if endpoint.endswith(suffix):
                endpoint = endpoint[:-len(suffix)]
                break
        base_url = f"{endpoint}/openai/v1/"
        _client = OpenAI(base_url=base_url, api_key=token_provider)
    return _client


# --- Style prompts by style ID ---
STYLE_PROMPTS = {
    "pixar-3d": (
        "Pixar-style 3D animated character. "
        "Clean colorful 3D animation style, smooth skin, stylized proportions, vibrant colors, soft studio lighting. "
        "Professional appearance suitable for a corporate animated explainer video. Clean background."
    ),
    "hyper-realistic": (
        "Hyper-realistic photographic portrait. "
        "Detailed skin texture, natural lighting, professional studio photography, "
        "sharp focus, high resolution, realistic proportions and features. Clean background."
    ),
    "anime": (
        "Anime / manga style character art. "
        "Large expressive eyes, clean line art, vibrant hair colors, "
        "dynamic shading, Japanese animation aesthetic. Clean background."
    ),
    "watercolor": (
        "Soft watercolor illustration character. "
        "Gentle brushstrokes, flowing colors, hand-painted feel, "
        "artistic texture, delicate features. Clean background."
    ),
    "flat-vector": (
        "Clean flat vector illustration. "
        "Minimal geometric shapes, solid colors, modern graphic design aesthetic, "
        "no gradients, bold simple shapes. Clean background."
    ),
    "comic-book": (
        "Comic book style character. "
        "Bold black outlines, cel-shading, dynamic pose, "
        "halftone dots, vivid colors, action-comic aesthetic. Clean background."
    ),
    "corporate": (
        "Polished corporate professional illustration. "
        "Clean modern business style, warm and approachable, "
        "subtle gradients, professional color palette, business-appropriate. Clean background."
    ),
}

# --- Asset type prompt prefixes ---
ASSET_TYPE_PROMPTS = {
    "character": "",  # User description is the character, style prompt handles the rest
    "background": "A detailed background scene or environment: ",
    "prop": "A single object or prop, isolated on a clean background: ",
    "logo-icon": "A simple iconic logo or icon design, flat clean style: ",
}


def generate_avatar_from_photo(
    photo_bytes: bytes,
    name: str,
    style: str = "pixar-3d",
    quality: str = "medium",
) -> dict:
    """Transform a photo into a styled avatar using gpt-image-2 edits."""
    client = _get_client()
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["medium"])

    style_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["pixar-3d"])
    edit_prompt = f"Transform this person into: {style_prompt}"

    # Use Image API edits endpoint
    photo_io = BytesIO(photo_bytes)
    photo_io.name = "photo.png"

    result = client.images.edit(
        model=AZURE_OPENAI_IMAGE_DEPLOYMENT,
        image=photo_io,
        prompt=edit_prompt,
        size=preset["size"],
    )

    img_data = base64.b64decode(result.data[0].b64_json)
    return _save_avatar_files(img_data, name, "photo", AZURE_OPENAI_IMAGE_DEPLOYMENT)


def generate_avatar_from_text(
    description: str,
    name: str,
    model: str = "gpt-image-2",
    style: str = "pixar-3d",
    asset_type: str = "character",
    quality: str = "medium",
) -> dict:
    """Generate an asset from a text description."""
    client = _get_client()
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["medium"])

    style_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["pixar-3d"])
    type_prefix = ASSET_TYPE_PROMPTS.get(asset_type, "")

    prompt = f"{type_prefix}{description}. Style: {style_prompt} Landscape 16:9 composition."

    result = client.images.generate(
        model=AZURE_OPENAI_IMAGE_DEPLOYMENT,
        prompt=prompt,
        n=1,
        size=preset["size"],
        quality=preset["quality"],
    )

    img_data = base64.b64decode(result.data[0].b64_json)
    return _save_avatar_files(img_data, name, "text", AZURE_OPENAI_IMAGE_DEPLOYMENT)


def _save_avatar_files(img_data: bytes, name: str, source: str, model: str) -> dict:
    """Save generated image as both landscape and portrait versions."""
    uid = uuid.uuid4().hex[:8]
    safe_name = "".join(c for c in name.lower().replace(" ", "-") if c.isalnum() or c == "-")[:20]

    img = Image.open(BytesIO(img_data))

    # Landscape (1280x720)
    land_name = f"{safe_name}-{uid}.png"
    land_path = os.path.join(AVATAR_DIR, land_name)
    img_land = img.resize((1280, 720), Image.LANCZOS)
    img_land.save(land_path, "PNG")

    # Portrait (720x1280)
    port_name = f"{safe_name}-{uid}-portrait.png"
    port_path = os.path.join(AVATAR_DIR, port_name)
    img_port = img.resize((720, 1280), Image.LANCZOS)
    img_port.save(port_path, "PNG")

    # Upload both to blob in background
    try:
        from services.blob_sync import upload_avatar_file_to_blob
        upload_avatar_file_to_blob(land_name)
        upload_avatar_file_to_blob(port_name)
    except Exception:
        pass

    return {
        "landscape_file": land_name,
        "portrait_file": port_name,
        "source": source,
        "model_used": model,
    }
