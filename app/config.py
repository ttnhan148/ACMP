import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = BASE_DIR / "projects"
BIN_DIR = BASE_DIR / "bin"
SEED_DIR = BASE_DIR / "seed"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
SEED_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "acmp.db"

# Cross-platform FFmpeg path resolution
# On Windows, if we downloaded it to bin/ffmpeg.exe, use it directly.
# Otherwise, fall back to global path 'ffmpeg' (which works on Linux).
ffmpeg_local = BIN_DIR / "ffmpeg.exe"
ffprobe_local = BIN_DIR / "ffprobe.exe"

if os.name == 'nt' and ffmpeg_local.exists():
    FFMPEG_PATH = str(ffmpeg_local.absolute())
    FFPROBE_PATH = str(ffprobe_local.absolute())
else:
    FFMPEG_PATH = "ffmpeg"
    FFPROBE_PATH = "ffprobe"

# Server network settings
PORT = 5678
HOST = "127.0.0.1"

# YouTube Mock / Integration flag
# The app supports mock data if no keys are provided, and real APIs if configured.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
# OAuth2 client secrets path for YouTube Analytics (loaded from settings in DB or local file)
CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
