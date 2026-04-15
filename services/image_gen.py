import base64
import os
import logging
import uuid

from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from PIL import Image
from io import BytesIO

from config import AZURE_OPENAI_ENDPOINT

logger = logging.getLogger(__name__)

AVATAR_DIR = os.path.abspath("static/avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

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


ANIMATION_STYLE_PROMPT = (
    "Transform into a Pixar-style 3D animated character. "
    "Keep the same facial features, expression, and pose but render in clean colorful 3D animation style. "
    "Smooth skin, stylized proportions, vibrant colors, soft studio lighting. "
    "Professional appearance suitable for a corporate animated explainer video. "
    "Clean background."
)


def generate_avatar_from_photo(
    photo_bytes: bytes,
    name: str,
    style: str = "animation",
) -> dict:
    """Transform a photo into an animated avatar using gpt-image-1.5 edits."""
    client = _get_client()

    style_prompt = ANIMATION_STYLE_PROMPT
    if style == "illustration":
        style_prompt = (
            "Transform into a hand-drawn watercolor illustration character. "
            "Keep the same facial features and expression but render in soft watercolor style with gentle lines."
        )

    # Use Image API edits endpoint
    photo_io = BytesIO(photo_bytes)
    photo_io.name = "photo.png"

    result = client.images.edit(
        model="gpt-image-1.5",
        image=photo_io,
        prompt=style_prompt,
        size="1536x1024",
    )

    img_data = base64.b64decode(result.data[0].b64_json)
    return _save_avatar_files(img_data, name, "photo", "gpt-image-1.5")


def generate_avatar_from_text(
    description: str,
    name: str,
    model: str = "gpt-image-1.5",
) -> dict:
    """Generate an avatar from a text description."""
    client = _get_client()

    prompt = (
        f"A Pixar-style 3D animated character: {description}. "
        "Clean colorful 3D animation style, professional corporate look, "
        "warm lighting, clean background, suitable for animated explainer video. "
        "Landscape 16:9 composition."
    )

    result = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size="1536x1024",
        quality="high",
    )

    img_data = base64.b64decode(result.data[0].b64_json)
    return _save_avatar_files(img_data, name, "text", model)


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

    return {
        "landscape_file": land_name,
        "portrait_file": port_name,
        "source": source,
        "model_used": model,
    }
