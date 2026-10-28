"""Test setup: a throwaway SQLite DB filled from the committed fixture subset."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
_db_file = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.as_posix()}"
os.environ["UPLOAD_DIR"] = str(_db_file.parent / "uploads")
os.environ["ANTHROPIC_API_KEY"] = ""
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from load_db import populate  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    db = SessionLocal()
    populate(db, FIXTURES, reset_trainer=True)
    db.close()


@pytest.fixture()
def client():
    return TestClient(app)
