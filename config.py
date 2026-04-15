import os
from dotenv import load_dotenv

load_dotenv()

# --- Directories ---
AUDIO_OUTPUT_DIR = os.path.abspath(os.getenv("LOCAL_AUDIO_OUTPUT_DIR", "generated_audio"))
DATA_DIR = os.path.abspath(os.getenv("DATA_DIR", "data"))
DB_PATH = os.path.join(DATA_DIR, "tts.db")

# --- Azure OpenAI (for GPT translation / Responses API) ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", os.getenv("ENDPOINT_URL", ""))
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", os.getenv("DEPLOYMENT_NAME", "gpt-5.4"))

# --- Azure OpenAI Audio (for gpt-audio-1.5 chat completions) ---
AZURE_OPENAI_AUDIO_DEPLOYMENT = os.getenv("AZURE_OPENAI_AUDIO_DEPLOYMENT", "gpt-audio-1.5")
AZURE_OPENAI_AUDIO_API_VERSION = os.getenv("AZURE_OPENAI_AUDIO_API_VERSION", "2025-01-01-preview")

# --- Azure OpenAI Realtime ---
AZURE_OPENAI_REALTIME_DEPLOYMENT = os.getenv("AZURE_OPENAI_REALTIME_DEPLOYMENT", "gpt-realtime-1.5")

# --- Azure Speech ---
AZURE_SPEECH_RESOURCE_ID = os.getenv("AZURE_SPEECH_RESOURCE_ID", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")
AZURE_SPEECH_VOICE = os.getenv("AZURE_SPEECH_VOICE", "fil-PH-BlessicaNeural")

# --- Azure Storage ---
AZURE_STORAGE_ACCOUNT_URL = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "")

# --- Azure AD / Entra ID ---
AZURE_AD_TENANT_ID = os.getenv("AZURE_AD_TENANT_ID", "")
AZURE_AD_CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID", "")
AZURE_AD_API_SCOPE = os.getenv("AZURE_AD_API_SCOPE", "")

# --- Curated Voice Lists ---
VOICES = {
    "azure-tts": [
        {"id": "fil-PH-AngeloNeural", "name": "Angelo (Filipino Male)", "locale": "fil-PH", "gender": "Male"},
        {"id": "fil-PH-BlessicaNeural", "name": "Blessica (Filipino Female)", "locale": "fil-PH", "gender": "Female"},
        {"id": "en-US-Andrew:DragonHDLatestNeural", "name": "Andrew HD (English Male)", "locale": "en-US", "gender": "Male"},
        {"id": "en-AU-WilliamMultilingualNeural", "name": "William Multilingual (English Male)", "locale": "en-AU", "gender": "Male"},
        {"id": "en-US-AvaMultilingualNeural", "name": "Ava Multilingual (English Female)", "locale": "en-US", "gender": "Female"},
    ],
    "gpt-ssml": [
        {"id": "fil-PH-AngeloNeural", "name": "Angelo (Filipino Male)", "locale": "fil-PH", "gender": "Male"},
        {"id": "fil-PH-BlessicaNeural", "name": "Blessica (Filipino Female)", "locale": "fil-PH", "gender": "Female"},
        {"id": "en-US-Andrew:DragonHDLatestNeural", "name": "Andrew HD (English Male)", "locale": "en-US", "gender": "Male"},
        {"id": "en-AU-WilliamMultilingualNeural", "name": "William Multilingual (English Male)", "locale": "en-AU", "gender": "Male"},
        {"id": "en-US-AvaMultilingualNeural", "name": "Ava Multilingual (English Female)", "locale": "en-US", "gender": "Female"},
    ],
    "gpt-audio": [
        # Male voices first
        {"id": "ash", "name": "Ash", "gender": "Male"},
        {"id": "ballad", "name": "Ballad", "gender": "Male"},
        {"id": "cedar", "name": "Cedar", "gender": "Male"},
        {"id": "echo", "name": "Echo", "gender": "Male"},
        {"id": "verse", "name": "Verse", "gender": "Male"},
        # Female voices
        {"id": "alloy", "name": "Alloy", "gender": "Female"},
        {"id": "coral", "name": "Coral", "gender": "Female"},
        {"id": "marin", "name": "Marin", "gender": "Female"},
        {"id": "sage", "name": "Sage", "gender": "Female"},
        {"id": "shimmer", "name": "Shimmer", "gender": "Female"},
    ],
    "gpt-realtime": [
        # Male voices first
        {"id": "ash", "name": "Ash", "gender": "Male"},
        {"id": "ballad", "name": "Ballad", "gender": "Male"},
        {"id": "echo", "name": "Echo", "gender": "Male"},
        {"id": "verse", "name": "Verse", "gender": "Male"},
        # Female voices
        {"id": "alloy", "name": "Alloy", "gender": "Female"},
        {"id": "coral", "name": "Coral", "gender": "Female"},
        {"id": "sage", "name": "Sage", "gender": "Female"},
        {"id": "shimmer", "name": "Shimmer", "gender": "Female"},
    ],
}

# --- Pronunciation Substitution Dictionary ---
# Applied as <sub alias="..."> in SSML for Azure Speech methods
PRONUNCIATION_DICT = {
    "BDO": "B D O",
    "SME": "S M E",
    "e-banking": "ee banking",
    "ATM": "A T M",
    "OTP": "O T P",
    "PIN": "P I N",
    "QR": "Q R",
    "GCash": "G Cash",
    "UnionBank": "Union Bank",
    "EastWest": "East West",
}

# --- SSML Prosody Defaults ---
PROSODY_DEFAULTS = {
    "rate": "0%",       # -50% to +50%
    "pitch": "default",  # x-low, low, medium, high, x-high, default, or +/-Nst
    "volume": "default", # silent, x-soft, soft, medium, loud, x-loud, default, or 0-100
}

# --- GPT Audio System Prompt (for gpt-audio-1.5 method) ---
GPT_AUDIO_SYSTEM_PROMPT = (
    "You are a professional voice-over artist for BDO (B-D-O), a major Philippine bank. "
    "Speak in a warm, professional, and engaging tone suitable for marketing videos and customer communications. "
    "When speaking in Taglish (Tagalog-English mix), maintain natural conversational flow. "
    "Keep brand names exactly as written (BDO should be said as B-D-O). "
    "Express numbers in English words."
)

# --- GPT Translation System Prompt (for gpt-ssml method) ---
TRANSLATION_SYSTEM_PROMPT = """You are an AI Taglish Translator expert in translating English to Filipino context. You work for BDO (B-D-O).

## Rules
- Translate incoming text into Taglish (casual Filipino-English mix).
- Tonality: professional, suitable for bank customer service and marketing.
- Always express numbers as English words. Phone numbers: each digit as an English word.
  e.g. (02) 6321 8000 → (zero two) six three two one eight zero zero zero
- Never produce pure Tagalog. Always mix English naturally.
- Keep brand names exactly as-is (BDO, SME, etc.) — do NOT expand or rename them. Pronunciation is handled separately.
- You may reorder sentences for natural Taglish grammar, but never change meaning or add content.

## Critical Output Format
You MUST tag Filipino/Tagalog segments with [FIL]...[/FIL] markers so the TTS engine can switch pronunciation.
English segments should NOT be wrapped — leave them plain.
Only wrap segments that are genuinely Filipino/Tagalog words or phrases.

Example input: "Have you tried checking your account balance while having breakfast?"
Example output: [FIL]Nasubukan niyo na bang mag check ng[/FIL] account balance [FIL]niyo habang nag-aalmusal?[/FIL]

Example input: "Let BDO handle your payments and collections so you can focus on your business!"
Example output: Let BDO handle your payments and collections [FIL]para maka focus ka sa business mo![/FIL] [FIL]Tara na, mag-enroll na sa[/FIL] SME Online Banking!

Return ONLY the tagged translated text. No SSML, no XML, no additional commentary.
"""

# --- GPT SSML Annotation Prompt (for annotating existing Taglish text) ---
SSML_ANNOTATION_PROMPT = """You are an expert in Filipino/Tagalog and English language identification.

Your task: Given Taglish (mixed Filipino-English) text, identify which segments are Filipino/Tagalog and mark them with [FIL]...[/FIL] tags. Leave English segments unmarked.

Rules:
- Only wrap genuinely Filipino/Tagalog words and phrases.
- Common English words used in Filipino context (like "focus", "business", "online", "banking") should NOT be wrapped — they are spoken in English.
- Filipino particles, connectors, and phrases like "para", "maka", "ka sa", "mo", "Tara na", "mag-enroll na sa", "niyo", "nag-", "bang" MUST be wrapped.
- Keep the original text exactly — do NOT translate, rephrase, or add words.
- Brand names (BDO, SME) stay in English (unwrapped).

Example input: "Let BDO handle your payments and collections para maka focus ka sa business mo! Tara na, mag-enroll na sa SME Online Banking!"
Example output: Let BDO handle your payments and collections [FIL]para maka focus ka sa business mo![/FIL] [FIL]Tara na, mag-enroll na sa[/FIL] SME Online Banking!

Return ONLY the annotated text.
"""

# --- GPT SSML Rewrite Prompt (for AI suggested version) ---
SSML_REWRITE_PROMPT = """You are an expert voice-over script optimizer for BDO (B-D-O), a Philippine bank.

Your task: Given a Taglish script, rewrite it to sound better when spoken aloud via text-to-speech.

Improvements you should make:
- Adjust phrasing for more natural spoken rhythm and flow
- Add natural emphasis points — restructure sentences for impact
- Improve Taglish balance — make it sound more conversational and engaging
- Break long sentences into shorter, punchier phrases
- Ensure brand names (BDO, SME) are preserved exactly
- Keep the same core message and intent — don't change the meaning
- Keep numbers in English words

You MUST also tag Filipino/Tagalog segments with [FIL]...[/FIL] markers.
Only genuinely Filipino words/phrases get tagged; English stays unwrapped.

Example input: "Kayang kaya with SME Online Banking! Ayaw mo bang na-lalate mag-bayad ng bills at suppliers?"
Example output: [FIL]Kayang-kaya mo 'yan[/FIL] with SME Online Banking! [FIL]Ayaw mo na bang ma-late sa pagbayad ng[/FIL] bills [FIL]at[/FIL] suppliers? [FIL]Gawin mo nang madali![/FIL]

Return ONLY the rewritten and annotated text.
"""

# --- Supported audio formats ---
AUDIO_FORMATS = {
    "azure-tts": ["wav", "mp3"],
    "gpt-ssml": ["wav", "mp3"],
    "gpt-audio": ["wav", "mp3", "flac", "opus", "pcm16", "aac"],
    "gpt-realtime": ["pcm16"],
}

# --- Sora 2 Video Generation ---
AZURE_OPENAI_SORA_DEPLOYMENT = os.getenv("AZURE_OPENAI_SORA_DEPLOYMENT", "sora-2")
VIDEO_OUTPUT_DIR = os.path.abspath(os.getenv("VIDEO_OUTPUT_DIR", "generated_video"))

VIDEO_STYLES = [
    {"id": "animation", "label": "Animation", "description": "Colorful animated style with smooth motion, ideal for explainer and marketing content", "supports_avatar": True},
    {"id": "cinematic", "label": "Cinematic", "description": "Photorealistic cinematic look with professional lighting and camera work", "supports_avatar": False},
    {"id": "motion-graphics", "label": "Motion Graphics", "description": "Clean motion graphics with text overlays, transitions, and branded elements", "supports_avatar": False},
    {"id": "illustration", "label": "Illustration", "description": "Hand-drawn illustration style brought to life with gentle animation", "supports_avatar": False},
]

VIDEO_RESOLUTIONS = [
    {"id": "1280x720", "label": "Landscape 16:9 (1280×720)", "aspect": "16:9"},
    {"id": "720x1280", "label": "Portrait 9:16 (720×1280)", "aspect": "9:16"},
]

AVATARS = [
    {
        "id": "filipina-professional",
        "name": "Maria (Professional Woman)",
        "description": "Filipino woman, early 30s, shoulder-length black hair, navy blazer, white blouse, gold accessories, warm smile",
        "landscape_file": "static/avatars/filipina-professional.png",
        "portrait_file": "static/avatars/filipina-professional-portrait.png",
    },
    {
        "id": "filipino-professional",
        "name": "Juan (Professional Man)",
        "description": "Filipino man, mid-30s, short black hair, dark blue suit, gold tie, professional smile",
        "landscape_file": "static/avatars/filipino-professional.png",
        "portrait_file": "static/avatars/filipino-professional-portrait.png",
    },
    {
        "id": "filipina-casual",
        "name": "Ana (Young Professional)",
        "description": "Young Filipino woman, late 20s, long wavy black hair, teal blouse, casual smart look, holding tablet",
        "landscape_file": "static/avatars/filipina-casual.png",
        "portrait_file": "static/avatars/filipina-casual-portrait.png",
    },
    {
        "id": "filipino-entrepreneur",
        "name": "Carlo (Entrepreneur)",
        "description": "Filipino man, early 30s, medium black hair, white shirt with dark vest, energetic entrepreneur look",
        "landscape_file": "static/avatars/filipino-entrepreneur.png",
        "portrait_file": "static/avatars/filipino-entrepreneur-portrait.png",
    },
]

SORA_PROMPT_SYSTEM = """You are an expert video prompt engineer for Sora 2 (OpenAI's video generation model).

Your task: Convert a marketing/advertising script into a detailed Sora 2 video generation prompt.

Rules:
- Describe the VISUAL scene, not the spoken words. The script tells you what the message is — you describe what the VIDEO should show.
- Include: shot type (close-up, medium, wide), subject/characters, actions, setting/location, lighting, camera movement, color palette, mood.
- The video has NO spoken dialogue — it's a visual accompaniment to a voice-over.
- Keep the prompt under 200 words — Sora 2 works best with focused, specific prompts.
- Match the brand context: BDO is a major Philippine bank. Use Filipino business/urban settings when relevant.

Style instructions will be appended separately. Focus on the visual narrative.

Example input script: "Let BDO handle your payments and collections para maka focus ka sa business mo!"
Example output prompt: "Medium shot of a confident Filipino business owner at a modern desk, smiling while reviewing a tablet showing transaction dashboards. Warm golden lighting from a large window. The scene transitions with a smooth dolly movement to show the bustling city skyline of Manila through the glass. Clean, professional office environment with subtle blue and gold accents."

Return ONLY the video prompt. No explanations.
"""

SCENE_SPLITTER_PROMPT = """You are an expert video storyboard planner for marketing and explainer videos.

Your task: Break a marketing/explainer script into 4-6 visual scenes that can each be generated as a separate 12-second video clip, then stitched together into a cohesive final video.

Rules:
- Each scene should cover ONE visual concept/moment from the script
- Scenes should flow logically and build a narrative arc
- Include visual transition hints between scenes for continuity
- Keep the same visual style, color palette, and setting references across all scenes
- Each scene prompt should be self-contained but reference shared visual elements
- Duration: most scenes should be 12s, but key moments can be 8s or 4s

Output ONLY valid JSON array with this structure:
[
  {
    "scene_number": 1,
    "description": "Brief description of what this scene covers",
    "duration": 12,
    "prompt": "Detailed Sora 2 visual prompt for this scene"
  }
]

Keep each prompt under 150 words. Ensure visual consistency by repeating key style/setting elements.
Do NOT include any text outside the JSON array.
"""
