"""CNN inference with ONNX Runtime (the trained PyTorch model exported to models/pokemon_cnn.onnx)."""
import io
import json
from functools import lru_cache

import numpy as np
from PIL import Image

from .config import CONFIDENCE_THRESHOLD, LABELS_PATH, MAX_IMAGE_PIXELS, MODEL_PATH

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# Decided from the file's own bytes (Pillow's format sniffing), never from the client's MIME type.
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}
# Pillow's own decompression-bomb guard, as a backstop to the explicit pixel check below.
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ModelNotReady(RuntimeError):
    pass


class ImageTooLarge(ValueError):
    pass


@lru_cache(maxsize=1)
def _load():
    if not MODEL_PATH.exists() or not LABELS_PATH.exists():
        raise ModelNotReady("Model not trained yet - run scripts/train.py first.")
    import onnxruntime as ort
    meta = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    return session, meta


def open_image(data: bytes) -> Image.Image:
    """Open an upload safely: allowed formats only, size checked from the header before any pixels are decoded."""
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ImageTooLarge("That image has too many pixels.") from exc
    except Exception as exc:
        raise ValueError("That file is not a readable image.") from exc
    if image.format not in ALLOWED_FORMATS:
        raise ValueError(f"Unsupported image format {image.format or 'unknown'} - use PNG, JPEG, WebP, GIF or BMP.")
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ImageTooLarge(f"Image is {image.width}x{image.height}; the limit is "
                            f"{MAX_IMAGE_PIXELS / 1e6:.0f} megapixels.")
    try:
        image.load()
    except Exception as exc:
        raise ValueError("That file is not a readable image.") from exc
    return image


def preprocess(image: Image.Image, size: int) -> np.ndarray:
    """Same steps as training: trim transparent padding, pad to a white square, resize, normalise, NCHW."""
    image = image.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if bbox:
        image = image.crop(bbox)
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    canvas.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
    image = canvas.convert("RGB").resize((size, size), Image.BILINEAR)
    arr = (np.asarray(image, dtype=np.float32) / 255.0 - MEAN) / STD
    return arr.transpose(2, 0, 1)[None].astype(np.float32)


def logits(data: bytes) -> np.ndarray:
    """Raw class scores, averaged over the image and its mirror (test-time augmentation)."""
    session, meta = _load()
    x = preprocess(open_image(data), meta["img_size"])
    batch = np.concatenate([x, x[..., ::-1]])
    return session.run(None, {session.get_inputs()[0].name: np.ascontiguousarray(batch)})[0].mean(axis=0)


def softmax(scores: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = scores / temperature
    probs = np.exp(z - z.max(axis=-1, keepdims=True))
    return probs / probs.sum(axis=-1, keepdims=True)


def identify(data: bytes, top_k: int = 3) -> dict:
    _, meta = _load()
    # Temperature from scripts/evaluate.py calibration, so a confidence of p means "right about p of the time".
    probs = softmax(logits(data), meta.get("temperature", 1.0))
    top = np.argsort(probs)[::-1][:top_k]
    predictions = [{"name": meta["classes"][i], "confidence": round(float(probs[i]), 4)} for i in top]
    confident = predictions[0]["confidence"] >= CONFIDENCE_THRESHOLD
    return {
        "predictions": predictions,
        "confident": confident,
        "message": None if confident else "Not sure - the top guess is below 50% confidence.",
    }
