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
CALIBRATION_SETS = ("clean", "hard", "partial30")  # validation splits; the real-world test set stays untouched


def use_model(model_dir: Path):
    identifier.MODEL_PATH = model_dir / "pokemon_cnn.onnx"
    identifier.LABELS_PATH = model_dir / "labels.json"
    identifier._load.cache_clear()


def collect(items, index):
    """items: [(true_label, path)] -> (true class indices, logits) from the deployed ONNX pipeline."""
    y = np.array([index[label] for label, _ in items])
    return y, np.stack([identifier.logits(Path(path).read_bytes()) for _, path in items])


def ece(confidence, correct, bins=15):
    """Expected Calibration Error: gap between confidence and accuracy, averaged over confidence bins."""
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(confidence, edges[1:-1]), 0, bins - 1)
    return float(sum(abs(correct[which == b].mean() - confidence[which == b].mean()) * (which == b).mean()
                     for b in range(bins) if (which == b).any()))


def fit_temperature(logits, y):
    """Temperature that minimises negative log-likelihood (grid search is plenty for one parameter)."""
    grid = np.geomspace(0.2, 5.0, 300)
    nll = [-np.log(identifier.softmax(logits, t)[np.arange(len(y)), y] + 1e-12).mean() for t in grid]
    return float(grid[int(np.argmin(nll))])


def score(y, logits, classes, temperature):
    """Metrics + (true, predicted) name pairs, using the same threshold as the API."""
    probs = identifier.softmax(logits, temperature)
    top3 = np.argsort(-probs, axis=1)[:, :3]
    confidence = probs[np.arange(len(y)), top3[:, 0]]
    correct = top3[:, 0] == y
    sure = confidence >= identifier.CONFIDENCE_THRESHOLD
    return {
        "images": len(y),
        "top1": round(float(correct.mean()), 4),
        "top3": round(float((top3 == y[:, None]).any(axis=1).mean()), 4),
        "sure_share": round(float(sure.mean()), 4),
        "precision_when_sure": round(float(correct[sure].mean()), 4) if sure.any() else None,
        "ece": round(ece(confidence, correct), 4),
        "ece_uncalibrated": round(ece(identifier.softmax(logits).max(axis=1), correct), 4),
    }, [(classes[t], classes[p]) for t, p in zip(y, top3[:, 0])]


def reliability_plot(raw, temperature, path):
    """raw: {name: (y, logits)} -> accuracy vs confidence, before and after temperature scaling."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    edges = np.linspace(0, 1, 11)
    colors = {"validation (clean+hard+30%)": "#2b6f7a", "real world (test)": "#7a1f2b"}
    groups = {"validation (clean+hard+30%)": [raw[k] for k in CALIBRATION_SETS], "real world (test)": [raw["real"]]}
    for ax, t, title in [(axes[0], 1.0, "Raw softmax"), (axes[1], temperature, f"Temperature {temperature:.2f}")]:
        ax.plot([0, 1], [0, 1], ls="--", color="#8c8279", lw=1, label="perfect calibration")
        for name, parts in groups.items():
            y = np.concatenate([p[0] for p in parts])
            probs = identifier.softmax(np.concatenate([p[1] for p in parts]), t)
            conf, correct = probs.max(axis=1), probs.argmax(axis=1) == y
            which = np.clip(np.digitize(conf, edges[1:-1]), 0, 9)
            xs = [conf[which == b].mean() for b in range(10) if (which == b).sum() >= 5]
            ys = [correct[which == b].mean() for b in range(10) if (which == b).sum() >= 5]
            ax.plot(xs, ys, marker="o", color=colors[name], label=f"{name}, ECE {ece(conf, correct):.3f}")
        ax.set_title(title), ax.set_xlabel("confidence"), ax.set_xlim(0, 1), ax.set_ylim(0, 1.02)
        ax.legend(fontsize=8, loc="upper left")
    axes[0].set_ylabel("accuracy")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


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


def evaluate(model_dir: Path, calibrate: bool = False):
    """Score every test set. With calibrate, fit the temperature on the validation sets (never on the real-world
    test set) and save it to labels.json, where the API and the browser pick it up."""
    use_model(model_dir)
    labels_path = model_dir / "labels.json"
    meta = json.loads(labels_path.read_text())
    classes = meta["classes"]
    index = {c: i for i, c in enumerate(classes)}
    rows = json.loads((CACHE / "manifest.json").read_text())["images"]
    raw = {name: collect([(r["label"], CACHE / r["path"]) for r in rows if r["split"] == split], index)
           for name, split in SETS}
    temperature = meta.get("temperature", 1.0)
    if calibrate:
        temperature = fit_temperature(np.concatenate([raw[k][1] for k in CALIBRATION_SETS]),
                                      np.concatenate([raw[k][0] for k in CALIBRATION_SETS]))
        labels_path.write_text(json.dumps({**meta, "temperature": round(temperature, 4)}))
        use_model(model_dir)
    metrics, all_pairs = {"temperature": round(temperature, 4)}, {}
    for name, (y, logits) in raw.items():
        metrics[name], all_pairs[name] = score(y, logits, classes, temperature)
    uploads = []
    for label, path in upload_cases():
        result = identifier.identify(path.read_bytes())
        top = result["predictions"][0]
        uploads.append({"file": path.name, "expected": label, "predicted": top["name"],
                        "confidence": top["confidence"], "correct": top["name"] == label})
    metrics["uploads"] = uploads
    return metrics, all_pairs, raw


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

    metrics, pairs, raw = evaluate(args.model_dir, calibrate=not args.no_report)
    print(json.dumps(metrics, indent=2))
    if args.no_report:
        return

    baseline = None
    if args.baseline_dir.exists():
        baseline, _, _ = evaluate(args.baseline_dir)
        use_model(args.model_dir)
    labels = json.loads((args.model_dir / "labels.json").read_text())
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps({"model": metrics, "baseline_v1": baseline}, indent=2))
    confusion_plot(pairs["real"], RESULTS / "confusion_matrix.png", "20 most-confused classes, real-world test set")
    reliability_plot(raw, metrics["temperature"], RESULTS / "reliability.png")

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
        "## Calibration", "",
        "A softmax score is not automatically a probability of being right, so the confidence is calibrated with "
        f"**temperature scaling**: logits are divided by T = {metrics['temperature']:.2f}, fitted by minimising "
        "log-loss on the validation sets (clean, hard, 30% visible). The real-world sets are never used for fitting. "
        "The API and the browser both read T from `labels.json`. ECE (expected calibration error, 15 bins) is the "
        "average gap between confidence and accuracy; lower is better.", "",
        "| Test set | ECE raw softmax | ECE calibrated |", "|---|---|---|",
        *[f"| {label} | {metrics[key]['ece_uncalibrated']:.3f} | **{metrics[key]['ece']:.3f}** |" for label, key in [
            ("Clean", "clean"), ("Hard", "hard"), ("30% visible", "partial30"), ("Real world (test)", "real"),
            ("Real world, 30% visible (test)", "real_partial30")]],
        "", "![Reliability diagram](reliability.png)", "",
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
