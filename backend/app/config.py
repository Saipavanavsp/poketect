"""Runtime settings, read from environment variables / the project-root .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'pokedex.db').as_posix()}")
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "pokemon_cnn.onnx"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", ROOT / "models" / "labels.json"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://saipavanavsp.github.io").split(",") if o.strip()]
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
# When set, trainer/badge/team edits need "Authorization: Bearer <ADMIN_TOKEN>". Empty = open (local dev).
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
# Requests per minute per client IP; 0 turns the limit off.
RATE_LIMIT_IDENTIFY = int(os.getenv("RATE_LIMIT_IDENTIFY", "30"))
RATE_LIMIT_CHAT = int(os.getenv("RATE_LIMIT_CHAT", "10"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))  # checked from the header, before decoding
