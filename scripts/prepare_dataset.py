"""Build the training cache + splits from PokéAPI sprites and the public-domain real-world image set.

    .\\.venv\\Scripts\\python.exe scripts\\prepare_dataset.py

Inputs
  data/images/<pokemon>/*.png|*.gif|*.jpg   from scripts/fetch_data.py (PokéAPI) and scripts/fetch_pokemondb.py
                                             (GO, HOME, SV ... styles and alternate forms); GIFs give several frames
  data/external_real/zips/{train,valid,test}.zip
      Roboflow "Pokedex" dataset (Public Domain), mirrored at
      https://huggingface.co/datasets/keremberke/pokemon-classification - 6,991 photos, fan art,
      cards and toys of Gen 1 Pokémon. train+valid are used for training, test is a real-world benchmark.
Outputs
  data/cache/img/...            RGBA PNGs, sprite trimmed and centred on a BASE x BASE canvas
  data/cache/manifest.json      every image with label, source and split (train / val / test_real)
  data/cache/hard/...           degraded copies of the val images (crop, low-res, blur, JPEG) for testing
  data/cache/partial30/...      crops of the val / real test images showing only 30% of the Pokémon
"""
import io
import json
import random
import re
import zipfile
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageSequence

from partial_view import crop_visible, subject_mask

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "data" / "images"
ZIPS = ROOT / "data" / "external_real" / "zips"
CACHE = ROOT / "data" / "cache"
BASE = 256
GIF_FRAMES = 4
HELD_OUT_NEVER = {"artwork"}  # keep the cleanest example in training
PARTIAL_VISIBLE = 0.30  # share of the Pokémon left visible in the partial-view test sets
PARTIAL_PER_IMAGE = 3


def never_held_out(variant: str) -> bool:
    """Alternate forms (Mega, Alolan, costumes ...) would make an unfair test of the species' normal look."""
    return variant in HELD_OUT_NEVER or variant.startswith("pdbform_")

# Roboflow folder names that don't normalise to the PokéAPI name.
REAL_NAME_FIX = {"mrmime": "mr-mime", "alolan-sandslash": "sandslash", "farfetchd": "farfetchd"}


def fit(img: Image.Image, base: int = BASE) -> Image.Image:
    """Trim transparent padding and scale to fill a base x base transparent square (same as inference).
    Opaque artwork (JPEG on white) gets its background cut out first so training can swap backgrounds."""
    img = img.convert("RGBA")
    if img.getchannel("A").getextrema()[0] == 255:
        img.putalpha(Image.fromarray(subject_mask(img).astype(np.uint8) * 255))
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    scale = base / max(img.size)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                     Image.LANCZOS if scale < 1 else Image.BILINEAR)
    canvas = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    canvas.paste(img, ((base - img.width) // 2, (base - img.height) // 2))
    return canvas


def sprite_job(args):
    label, path = args
    out = []
    try:
        src = Image.open(path)
        if path.suffix == ".gif":
            frames = [f.copy() for f in ImageSequence.Iterator(src)]
            step = max(1, len(frames) // GIF_FRAMES)
            frames = frames[::step][:GIF_FRAMES]
        else:
            frames = [src]
        for i, frame in enumerate(frames):
            rel = f"img/{label}/{path.stem}_{i}.png"
            dest = CACHE / rel
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                fit(frame).save(dest)
            out.append({"path": rel, "label": label, "variant": path.stem, "source": "sprite"})
    except Exception as exc:  # a corrupt download shouldn't stop the build
        print(f"  ! skipped {path}: {exc}")
    return out


def real_job(args):
    label, split, name, data = args
    rel = f"img/_real/{split}/{label}/{Path(name).stem}.png"
    dest = CACHE / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.open(io.BytesIO(data)).convert("RGBA").resize((BASE, BASE), Image.LANCZOS).save(dest)
    return {"path": rel, "label": label, "variant": "real", "source": "real",
            "split": "test_real" if split == "test" else "train"}


def degrade(img: Image.Image, rng: random.Random) -> Image.Image:
    """Make a 'bad upload': partial crop, low resolution, blur, JPEG artefacts, flattened on white."""
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img, mask=img.getchannel("A"))
    w, h = flat.size
    frac = rng.uniform(0.6, 0.85)
    cw, ch = int(w * frac), int(h * frac)
    x, y = rng.randint(0, w - cw), rng.randint(0, h - ch)
    flat = flat.crop((x, y, x + cw, y + ch))
    small = rng.randint(40, 96)
    flat = flat.resize((small, small), Image.BILINEAR).resize((cw, ch), Image.BILINEAR)
    if rng.random() < 0.5:
        flat = flat.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.5)))
    buf = io.BytesIO()
    flat.save(buf, "JPEG", quality=rng.randint(25, 60))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def flatten_white(img: Image.Image) -> Image.Image:
    flat = Image.new("RGB", img.size, (255, 255, 255))
    flat.paste(img, mask=img.convert("RGBA").getchannel("A"))
    return flat


def partial_rows(rows: list[dict]) -> list[dict]:
    """val_partial30: unseen sprite styles with only 30% of the Pokémon visible (PARTIAL_PER_IMAGE crops each).
    test_real_partial30: the same for the real-world test images, one crop each."""
    rng = np.random.default_rng(30)
    out, shares = [], []
    for source_split, split, per_image in [("val", "val_partial30", PARTIAL_PER_IMAGE),
                                           ("test_real", "test_real_partial30", 1)]:
        for row in sorted((r for r in rows if r["split"] == source_split), key=lambda r: r["path"]):
            img = Image.open(CACHE / row["path"]).convert("RGBA")
            for k in range(per_image):
                crop, visible = crop_visible(img, PARTIAL_VISIBLE, rng)
                rel = f"partial30/{split}/{row['label']}_{Path(row['path']).stem}_{k}.png"
                (CACHE / rel).parent.mkdir(parents=True, exist_ok=True)
                flatten_white(crop).save(CACHE / rel)
                out.append({**row, "path": rel, "split": split, "visible": round(visible, 3)})
                shares.append(visible)
    print(f"  partial-view crops: {len(out)}, visible share {min(shares):.2f}-{max(shares):.2f} "
          f"(mean {np.mean(shares):.3f})")
    return out


def normalise(folder: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", folder.lower()).strip("-")
    return REAL_NAME_FIX.get(key, key)


def main():
    classes = sorted(d.name for d in IMAGES.iterdir() if d.is_dir())
    known = set(classes)
    sprite_jobs = [(c, p) for c in classes for p in sorted((IMAGES / c).iterdir()) if p.suffix in (".png", ".gif", ".jpg")]

    real_jobs, unknown = [], defaultdict(int)
    for split in ("train", "valid", "test"):
        with zipfile.ZipFile(ZIPS / f"{split}.zip") as z:
            for name in z.namelist():
                if name.endswith("/") or ".." in name or not name.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                label = normalise(name.split("/")[0])
                if label not in known:
                    unknown[label] += 1
                    continue
                real_jobs.append((label, split, name, z.read(name)))
    if unknown:
        print("  real-world labels not matched:", dict(unknown))

    with Pool(12) as pool:
        sprites = [row for rows in pool.imap_unordered(sprite_job, sprite_jobs, chunksize=32) for row in rows]
        reals = list(pool.imap_unordered(real_job, real_jobs, chunksize=32))

    # Hold out one whole sprite style (all of its frames) per Pokémon.
    rng = random.Random(42)
    by_class = defaultdict(lambda: defaultdict(list))
    for row in sprites:
        by_class[row["label"]][row["variant"]].append(row)
    for label, variants in by_class.items():
        candidates = sorted(v for v in variants if not never_held_out(v))
        held = rng.choice(candidates) if len(variants) >= 3 and candidates else None
        for variant, rows in variants.items():
            for row in rows:
                row["split"] = "val" if variant == held else "train"
    # Use one frame per held-out GIF so every class counts once in validation.
    seen = set()
    for row in sorted(sprites, key=lambda r: r["path"]):
        if row["split"] == "val":
            if row["label"] in seen:
                row["split"] = "unused"
            seen.add(row["label"])

    rows = [r for r in sprites + reals if r["split"] != "unused"]
    hard_rng = random.Random(7)
    (CACHE / "hard").mkdir(parents=True, exist_ok=True)
    for row in sorted((r for r in rows if r["split"] == "val"), key=lambda r: r["label"]):
        rel = f"hard/{row['label']}.jpg"
        degrade(Image.open(CACHE / row["path"]), hard_rng).save(CACHE / rel)
        rows.append({**row, "path": rel, "split": "val_hard"})
    rows += partial_rows(rows)

    manifest = {"base": BASE, "classes": classes, "images": rows}
    (CACHE / "manifest.json").write_text(json.dumps(manifest))
    counts = defaultdict(int)
    for r in rows:
        counts[(r["split"], r["source"])] += 1
    print({f"{s}/{src}": n for (s, src), n in sorted(counts.items())})


if __name__ == "__main__":
    main()
