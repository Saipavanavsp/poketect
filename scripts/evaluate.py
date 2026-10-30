"""Evaluate an exported model exactly as the API runs it (ONNX Runtime + identifier.preprocess).

    .\\.venv\\Scripts\\python.exe scripts\\evaluate.py                       # current model, writes the report
    .\\.venv\\Scripts\\python.exe scripts\\evaluate.py --model-dir data\\baseline_v1 --no-report
    .\\.venv\\Scripts\\python.exe scripts\\evaluate.py --image pikachu.jpg    # one image

Test sets (from scripts/prepare_dataset.py, none used for training):
  clean      one unseen sprite style per Pokémon (1,025 images)
  hard       the same images cropped, shrunk, blurred and JPEG-compressed, like a bad upload
  partial30  the clean images cropped so only 30% of the Pokémon is visible (3 different crops each)
  real       732 real-world images (fan art, cards, toys, photos) of Gen 1 Pokémon, Public Domain set
  real_partial30  the real-world images cropped to 30% of the subject
  uploads    pictures users reported as wrong (backend/tests/fixtures/user_*.png)
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
RESULTS = ROOT / "docs" / "results"
CACHE = ROOT / "data" / "cache"
FIXTURES = ROOT / "backend" / "tests" / "fixtures"

from app import identifier  # noqa: E402

SETS = [("clean", "val"), ("hard", "val_hard"), ("partial30", "val_partial30"), ("real", "test_real"),
        ("real_partial30", "test_real_partial30")]
TARGET = 0.90  # required top-1 accuracy with only 30% of the Pokémon visible


def use_model(model_dir: Path):
    identifier.MODEL_PATH = model_dir / "pokemon_cnn.onnx"
    identifier.LABELS_PATH = model_dir / "labels.json"
    identifier._load.cache_clear()


def score(items):
    """items: [(true_label, path)] -> metrics + (true, predicted) pairs."""
    pairs, top3, sure, sure_right = [], 0, 0, 0
    for label, path in items:
        result = identifier.identify(Path(path).read_bytes())
        names = [p["name"] for p in result["predictions"]]
        pairs.append((label, names[0]))
        top3 += label in names
        if result["confident"]:
            sure += 1
            sure_right += names[0] == label
    n = len(pairs)
    return {
        "images": n,
        "top1": round(sum(t == p for t, p in pairs) / n, 4),
        "top3": round(top3 / n, 4),
        "sure_share": round(sure / n, 4),
        "precision_when_sure": round(sure_right / sure, 4) if sure else None,
    }, pairs


def upload_cases():
    """backend/tests/fixtures/user_<pokemon>.png -> expected label from the filename."""
    return [(re.sub(r"^user_", "", p.stem).replace("_", "-"), p) for p in sorted(FIXTURES.glob("user_*.png"))]


def confusion_plot(pairs, path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mistakes = Counter(c for t, p in pairs if t != p for c in (t, p))
    focus = [c for c, _ in mistakes.most_common(20)]
    if not focus:
        return
    pos = {c: i for i, c in enumerate(focus)}
    mat = np.zeros((len(focus), len(focus)), dtype=int)
    for t, p in pairs:
        if t in pos and p in pos:
            mat[pos[t], pos[p]] += 1
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(mat, cmap="Reds")
    ax.set_xticks(range(len(focus)), focus, rotation=75, fontsize=8)
    ax.set_yticks(range(len(focus)), focus, fontsize=8)
    ax.set_xlabel("predicted"), ax.set_ylabel("true"), ax.set_title(title)
    fig.colorbar(im, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def evaluate(model_dir: Path):
    use_model(model_dir)
    rows = json.loads((CACHE / "manifest.json").read_text())["images"]
    metrics, all_pairs = {}, {}
    for name, split in SETS:
        items = [(r["label"], CACHE / r["path"]) for r in rows if r["split"] == split]
        metrics[name], all_pairs[name] = score(items)
    uploads = []
    for label, path in upload_cases():
        result = identifier.identify(path.read_bytes())
        top = result["predictions"][0]
        uploads.append({"file": path.name, "expected": label, "predicted": top["name"],
                        "confidence": top["confidence"], "correct": top["name"] == label})
    metrics["uploads"] = uploads
    return metrics, all_pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    parser.add_argument("--baseline-dir", type=Path, default=ROOT / "data" / "baseline_v1")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args()

    if args.image:
        use_model(args.model_dir)
        print(json.dumps(identifier.identify(args.image.read_bytes()), indent=2))
        return

    metrics, pairs = evaluate(args.model_dir)
    print(json.dumps(metrics, indent=2))
    if args.no_report:
        return

    baseline = None
    if args.baseline_dir.exists():
        baseline, _ = evaluate(args.baseline_dir)
        use_model(args.model_dir)
    labels = json.loads((args.model_dir / "labels.json").read_text())
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps({"model": metrics, "baseline_v1": baseline}, indent=2))
    confusion_plot(pairs["real"], RESULTS / "confusion_matrix.png", "20 most-confused classes, real-world test set")

    def row(label, key, fmt="{:.1%}"):
        new = metrics[key]
        old = baseline[key] if baseline else None
        cells = [fmt.format(new["top1"]), fmt.format(new["top3"])]
        prev = [fmt.format(old["top1"]), fmt.format(old["top3"])] if old else ["", ""]
        return f"| {label} | {new['images']} | {prev[0]} | {prev[1]} | **{cells[0]}** | **{cells[1]}** |"

    lines = [
        "# Model evaluation", "",
        f"Model: **{labels.get('arch', 'mobilenet_v2')}** at {labels['img_size']} px, {len(labels['classes'])} classes. "
        "All numbers come from the ONNX model run through the same code as `POST /api/identify`.", "",
        "| Test set | Images | v1 top-1 | v1 top-3 | v2 top-1 | v2 top-3 |", "|---|---|---|---|---|---|",
        row("Clean: one unseen sprite style per Pokémon", "clean"),
        row("Hard: same images cropped, low-res, blurred, JPEG", "hard"),
        row("**30% visible**: clean images, only 30% of the Pokémon shown", "partial30"),
        row("Real world: fan art, cards, toys, photos (Gen 1)", "real"),
        row("Real world, 30% of the subject shown", "real_partial30"),
        "",
        f"**30%-visible target ({TARGET:.0%} top-1): "
        f"{'met' if metrics['partial30']['top1'] >= TARGET else 'not met'}** "
        f"({metrics['partial30']['top1']:.1%} on {metrics['partial30']['images']} crops of unseen sprite styles).", "",
        "v1 was MobileNetV2 trained on clean sprites only. v2 adds animated-sprite frames and more game styles, "
        "public-domain real-world images for Gen 1, Pokémon GO / HOME / Scarlet-Violet styles and alternate forms "
        "from pokemondb.net, partial-view training (crops keeping 15-90% of the Pokémon), class-balanced sampling "
        "and heavy low-quality augmentation.", "",
        f"When v2 says it is sure (above 50%), it is right {metrics['real']['precision_when_sure'] or 0:.1%} of the time "
        f"on real-world images and {metrics['hard']['precision_when_sure'] or 0:.1%} on hard ones.", "",
        "## Reported uploads", "", "| File | Expected | v2 prediction | Confidence |", "|---|---|---|---|",
    ]
    lines += [f"| {u['file']} | {u['expected']} | {u['predicted']} {'✓' if u['correct'] else '✗'} | {u['confidence']:.0%} |"
              for u in metrics["uploads"]]
    lines += ["", "Real-world images exist only for Gen 1 in the public dataset, so later generations are tested on "
              "sprites (clean and hard sets) only.", "", "![Confusion matrix](confusion_matrix.png)", ""]
    (RESULTS / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote docs/results/evaluation.md")


if __name__ == "__main__":
    main()
