"""
Central config. Everything here is read from environment variables so that
in GitHub Actions it comes from repo Secrets, and locally you can use a .env
file (see .env.example) loaded via `python -m dotenv run -- python src/main.py`
or by exporting the vars yourself.
"""
import os

# --- Required API credentials -----------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Cloudflare R2 (S3-compatible): temporary public hosting so Instagram/
# TikTok's servers have a URL to fetch the finished video from -- neither
# platform accepts a direct file upload the way YouTube's API does.
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "cobble-tales-media")
R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")

# Instagram Graph API (Instagram professional account + Meta app)
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("IG_USER_ID", "")

# TikTok Content Posting API. Until TikTok audits the developer app, every
# post is forced private regardless of this setting -- flip it to
# "PUBLIC_TO_EVERYONE" once the app is approved. See SETUP.md.
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_PRIVACY_LEVEL = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")

CROSSPOST_HOSTING_ENABLED = bool(
    R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_PUBLIC_BASE_URL
)
IG_CROSSPOST_ENABLED = CROSSPOST_HOSTING_ENABLED and bool(IG_ACCESS_TOKEN and IG_USER_ID)
TIKTOK_CROSSPOST_ENABLED = CROSSPOST_HOSTING_ENABLED and bool(TIKTOK_ACCESS_TOKEN)

# --- Brand / format settings --------------------------------------------
CHANNEL_BRAND = "Cobble Tales"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")  # edge-tts voice name
# Speaking speed. The genre's narration runs a little faster than a normal
# read; this is an edge-tts percentage string ("+0%" = normal).
TTS_RATE = os.environ.get("TTS_RATE", "+5%")

# Vertical (9:16), Reels/TikTok native format
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

# Reddit-story videos. Original AI-written stories in the genre/voice of
# viral Reddit posts (AITA, TIFU, confession, revenge, etc.) -- not scraped
# real posts, see SETUP.md for why. Background is one continuous parkour
# gameplay shot, the genre convention, rather than cut-between-topical
# b-roll -- see PARKOUR_CLIP_URLS below for where it comes from.
REDDIT_STORIES_PER_DAY = int(os.environ.get("REDDIT_STORIES_PER_DAY", "3"))
REDDIT_STORY_TARGET_SECONDS_MIN = 40
REDDIT_STORY_TARGET_SECONDS_MAX = 75

# Background gameplay, in priority order:
#   1. real clips committed to assets/parkour/ (*.mp4 etc.)
#   2. real clips downloaded from PARKOUR_CLIP_URLS -- comma/space/newline
#      separated direct links (e.g. files in your R2 bucket), for footage too
#      big to commit to GitHub (100MB/file limit)
#   3. otherwise, freshly generated block-parkour gameplay (src/gameplay.py),
#      so every video always has moving gameplay behind it
PARKOUR_CLIP_URLS = [u for u in os.environ.get("PARKOUR_CLIP_URLS", "").replace(",", " ").split() if u]

# --- Paths ---------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
PARKOUR_DIR = os.path.join(ASSETS_DIR, "parkour")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
CAPTION_FONT = os.path.join(FONTS_DIR, "Montserrat-Black.ttf")
WORK_DIR = os.path.join(ROOT_DIR, "work")  # scratch dir, gitignored
PARKOUR_CACHE_DIR = os.path.join(WORK_DIR, "parkour_cache")

REDDIT_STORY_CATEGORIES_FILE = os.path.join(DATA_DIR, "reddit_story_categories.json")
USED_REDDIT_STORY_CATEGORIES_FILE = os.path.join(DATA_DIR, "used_reddit_story_categories.json")


def require(*names):
    """Raise a clear error if any of the named config values are empty."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            f"Missing required config/secrets: {', '.join(missing)}. "
            f"Set them as environment variables (GitHub Actions: repo Secrets). "
            f"See SETUP.md."
        )
