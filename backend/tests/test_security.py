"""Admin token on edits, per-IP rate limits, and upload validation."""
import io

from PIL import Image

from app import config, main


def png(size=(8, 8), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


def test_edits_need_admin_token_when_set(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    assert client.put("/api/trainer", json={"bio": "x"}).status_code == 401
    assert client.put("/api/trainer", json={"bio": "x"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.put("/api/trainer/badges/1", json={"earned": True}).status_code == 401
    assert client.put("/api/trainer/team/1", json={"level": 50}).status_code == 401
    ok = client.put("/api/trainer", json={"bio": "x"}, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json()["bio"] == "x"
    assert client.get("/api/trainer").status_code == 200  # reads stay public


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_CHAT", 2)
    main.chat_limit.hits.clear()
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert [client.post("/api/chat", json=body).status_code for _ in range(3)] == [200, 200, 429]
    main.chat_limit.hits.clear()


def test_rejects_oversized_upload(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 1024)
    res = client.post("/api/identify", files={"file": ("big.png", b"x" * 5000, "image/png")})
    assert res.status_code == 413


def test_rejects_unsupported_format(client):
    res = client.post("/api/identify", files={"file": ("a.tiff", png(fmt="TIFF"), "image/png")})
    assert res.status_code in (400, 503)
    if res.status_code == 400:
        assert "Unsupported image format TIFF" in res.json()["detail"]


def test_rejects_too_many_pixels_before_decoding(monkeypatch):
    from app import identifier
    monkeypatch.setattr(identifier, "MAX_IMAGE_PIXELS", 1000)
    try:
        identifier.open_image(png((100, 100)))
    except identifier.ImageTooLarge as exc:
        assert "megapixels" in str(exc)
    else:
        raise AssertionError("expected ImageTooLarge")
