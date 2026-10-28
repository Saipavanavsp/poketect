"""POST /api/identify: real model on a real image, plus error handling."""
import io
from pathlib import Path

import pytest
from PIL import Image

from app import identifier

FIXTURE = Path(__file__).parent / "fixtures" / "pikachu.png"
needs_model = pytest.mark.skipif(not identifier.MODEL_PATH.exists(), reason="model not trained")


@needs_model
def test_identifies_pikachu(client):
    with FIXTURE.open("rb") as f:
        res = client.post("/api/identify", files={"file": ("pikachu.png", f, "image/png")})
    assert res.status_code == 200
    body = res.json()
    assert len(body["predictions"]) == 3
    assert body["predictions"][0]["name"] == "pikachu"
    assert body["confident"] is True and body["message"] is None
    confidences = [p["confidence"] for p in body["predictions"]]
    assert confidences == sorted(confidences, reverse=True) and 0 < sum(confidences) <= 1.0001


@needs_model
def test_low_confidence_says_not_sure(client):
    noise = Image.frombytes("RGB", (64, 64), bytes(range(256)) * 48)
    buf = io.BytesIO()
    noise.save(buf, "PNG")
    body = client.post("/api/identify", files={"file": ("noise.png", buf.getvalue(), "image/png")}).json()
    if not body["confident"]:
        assert body["message"].startswith("Not sure")


def test_rejects_non_images(client):
    res = client.post("/api/identify", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert res.status_code in (400, 503)


def test_rejects_empty_upload(client):
    assert client.post("/api/identify", files={"file": ("empty.png", b"", "image/png")}).status_code == 400


def test_model_missing_returns_503(client, monkeypatch, tmp_path):
    identifier._load.cache_clear()
    monkeypatch.setattr(identifier, "MODEL_PATH", tmp_path / "missing.onnx")
    with FIXTURE.open("rb") as f:
        res = client.post("/api/identify", files={"file": ("p.png", f, "image/png")})
    assert res.status_code == 503
    identifier._load.cache_clear()
