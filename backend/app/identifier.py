"""CNN inference with ONNX Runtime (the trained PyTorch model exported to models/pokemon_cnn.onnx)."""
import io
import json
from functools import lru_cache

import numpy as np
from PIL import Image

from .config import CONFIDENCE_THRESHOLD, LABELS_PATH, MODEL_PATH

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class ModelNotReady(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load():
    if not MODEL_PATH.exists() or not LABELS_PATH.exists():
        raise ModelNotReady("Model not trained yet - run scripts/train.py first.")
    import onnxruntime as ort
    meta = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    return session, meta


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


def identify(data: bytes, top_k: int = 3) -> dict:
    session, meta = _load()
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        raise ValueError("That file is not a readable image.") from exc
    logits = session.run(None, {session.get_inputs()[0].name: preprocess(image, meta["img_size"])})[0][0]
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    top = np.argsort(probs)[::-1][:top_k]
    predictions = [{"name": meta["classes"][i], "confidence": round(float(probs[i]), 4)} for i in top]
    confident = predictions[0]["confidence"] >= CONFIDENCE_THRESHOLD
    return {
        "predictions": predictions,
        "confident": confident,
        "message": None if confident else "Not sure - the top guess is below 50% confidence.",
    }
