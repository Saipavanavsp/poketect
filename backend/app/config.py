"""Runtime settings, read from environment variables / the project-root .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'pokedex.db').as_posix()}")
MODEL_PATH = Path(os.getenv("MODEL_PATH", ROOT / "models" / "pokemon_cnn.onnx"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", ROOT / "models" / "labels.json"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ROOT / "data" / "uploads"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://saipavanavsp.github.io").split(",") if o.strip()]
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
