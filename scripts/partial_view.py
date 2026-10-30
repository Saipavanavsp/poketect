"""Crop windows that show a chosen fraction of a Pokémon, shared by prepare_dataset.py (test set) and train.py.

"30% visible" means the window contains 30% of the Pokémon's own pixels (its alpha mask), not 30% of the
canvas - otherwise most of a crop could be empty background.
"""
import numpy as np
from PIL import Image, ImageChops, ImageDraw


def subject_mask(img: Image.Image) -> np.ndarray:
    """Boolean mask of the Pokémon: alpha if the image has transparency, else everything that isn't background
    connected to the corners (artwork JPEGs on white)."""
    img = img.convert("RGBA")
    alpha = np.asarray(img.getchannel("A")) > 127
    if not alpha.all():
        return alpha
    rgb = img.convert("RGB")
    filled = rgb.copy()
    w, h = rgb.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(filled, corner, (255, 0, 255), thresh=24)
    mask = np.asarray(ImageChops.difference(rgb, filled).convert("L")) == 0  # untouched by the fill
    return mask if mask.sum() > 0.02 * mask.size else np.ones_like(mask)


def partial_window(mask: np.ndarray, target: float, rng: np.random.Generator, tol: float = 0.03,
                   tries: int = 6, batch: int = 256) -> tuple[tuple[int, int, int, int], float]:
    """A box (left, top, right, bottom) whose share of the mask's pixels is target +- tol (or the closest found)."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        h, w = mask.shape
        return (0, 0, w, h), 1.0
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    bw, bh, total = x1 - x0, y1 - y0, len(ys)
    integral = np.pad(mask.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    best, best_err = None, np.inf
    for _ in range(tries):
        share = rng.uniform(target * 0.7, min(1.0, target * 2.2), batch)  # of the bounding box area
        ratio = np.exp(rng.uniform(np.log(0.5), np.log(2.0), batch))
        w = np.clip(np.sqrt(share * bw * bh * ratio), 2, bw).astype(int)
        h = np.clip(np.sqrt(share * bw * bh / ratio), 2, bh).astype(int)
        left = x0 + (rng.random(batch) * (bw - w + 1)).astype(int)
        top = y0 + (rng.random(batch) * (bh - h + 1)).astype(int)
        right, bottom = left + w, top + h
        inside = integral[bottom, right] - integral[top, right] - integral[bottom, left] + integral[top, left]
        err = np.abs(inside / total - target)
        i = int(err.argmin())
        if err[i] < best_err:
            best_err, best = err[i], (int(left[i]), int(top[i]), int(right[i]), int(bottom[i]), inside[i] / total)
        if best_err <= tol:
            break
    return best[:4], float(best[4])


def crop_visible(img: Image.Image, target: float, rng: np.random.Generator, tol: float = 0.03):
    """Crop `img` so about `target` of the Pokémon is visible. Returns (crop, actual visible share)."""
    box, visible = partial_window(subject_mask(img), target, rng, tol)
    return img.crop(box), visible
