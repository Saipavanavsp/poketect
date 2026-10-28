"""Evaluate the exported model (models/pokemon_cnn.onnx) exactly as the API runs it.

    .\\.venv\\Scripts\\python.exe scripts\\evaluate.py                    # held-out split
    .\\.venv\\Scripts\\python.exe scripts\\evaluate.py --image pikachu.jpg # one image

Writes docs/results/metrics.json, evaluation.md and confusion_matrix.png.
"""
import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
RESULTS = ROOT / "docs" / "results"

from app import identifier  # noqa: E402


def predict(path: Path):
    return identifier.identify(path.read_bytes(), top_k=3)


def confusion_plot(pairs, classes):
    """Confusion matrix restricted to the 20 classes involved in the most mistakes (1025x1025 is unreadable)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mistakes = Counter(c for t, p in pairs if t != p for c in (t, p))
    focus = [c for c, _ in mistakes.most_common(20)] or classes[:20]
    pos = {c: i for i, c in enumerate(focus)}
    mat = np.zeros((len(focus), len(focus)), dtype=int)
    for t, p in pairs:
        if t in pos and p in pos:
            mat[pos[t], pos[p]] += 1
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(mat, cmap="Reds")
    ax.set_xticks(range(len(focus)), focus, rotation=75, fontsize=8)
    ax.set_yticks(range(len(focus)), focus, fontsize=8)
    ax.set_xlabel("predicted"), ax.set_ylabel("true")
    ax.set_title("Confusion matrix - 20 most-confused classes (held-out set)")
    fig.colorbar(im, fraction=0.046)
    fig.tight_layout()
    fig.savefig(RESULTS / "confusion_matrix.png", dpi=130)
    plt.close(fig)


def external_eval(sample=300, seed=7):
    """Extra check on Pokémon Showdown sprites (not in the training folders, but related to game sprites that are)."""
    import random

    import requests

    out = ROOT / "data" / "external"
    out.mkdir(parents=True, exist_ok=True)
    pokemon = json.loads((ROOT / "data" / "processed" / "pokemon.json").read_text(encoding="utf-8"))
    random.Random(seed).shuffle(pokemon)
    hits = top3 = n = 0
    for p in pokemon:
        if n >= sample:
            break
        raw = json.loads((ROOT / "data" / "raw" / "pokemon" / f"{p['id']}.json").read_text(encoding="utf-8"))
        url = ((raw["sprites"].get("other") or {}).get("showdown") or {}).get("front_default")
        if not url:
            continue
        dest = out / f"{p['name']}.gif"
        if not dest.exists():
            resp = requests.get(url, timeout=30)
            if not resp.ok:
                continue
            dest.write_bytes(resp.content)
        frame = Image.open(dest).convert("RGBA")  # first animation frame
        buf = io.BytesIO()
        frame.save(buf, "PNG")
        names = [x["name"] for x in identifier.identify(buf.getvalue())["predictions"]]
        hits += names[0] == p["name"]
        top3 += p["name"] in names
        n += 1
    return {"images": n, "top1": round(hits / n, 4), "top3": round(top3 / n, 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path)
    parser.add_argument("--skip-external", action="store_true")
    args = parser.parse_args()

    if args.image:
        print(json.dumps(predict(args.image), indent=2))
        return

    split = json.loads((ROOT / "models" / "split.json").read_text())["val"]
    classes = json.loads((ROOT / "models" / "labels.json").read_text())["classes"]
    gens = {p["name"]: p["generation"] for p in json.loads((ROOT / "data" / "processed" / "pokemon.json").read_text(encoding="utf-8"))}
    pairs, top3, confident, confident_right = [], 0, 0, 0
    by_gen, by_kind = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for name, rel in split:
        result = predict(ROOT / rel)
        names = [p["name"] for p in result["predictions"]]
        right = names[0] == name
        pairs.append((name, names[0]))
        top3 += name in names
        if result["confident"]:
            confident += 1
            confident_right += right
        for bucket, key in ((by_gen, gens.get(name)), (by_kind, Path(rel).stem)):
            bucket[key][0] += right
            bucket[key][1] += 1

    n = len(pairs)
    metrics = {
        "images": n, "classes": len(classes),
        "top1": round(sum(t == p for t, p in pairs) / n, 4), "top3": round(top3 / n, 4),
        "confident_share": round(confident / n, 4),
        "precision_when_confident": round(confident_right / confident, 4) if confident else None,
        "by_generation": {g: round(r / t, 4) for g, (r, t) in sorted(by_gen.items())},
        "by_image_kind": {k: {"top1": round(r / t, 4), "n": t} for k, (r, t) in sorted(by_kind.items())},
    }
    if not args.skip_external:
        metrics["external_showdown"] = external_eval()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(metrics, indent=2))
    confusion_plot(pairs, classes)

    lines = ["# Model evaluation", "",
             f"Held-out set: **{n} images**, one unseen image per Pokémon across **{len(classes)} classes**.", "",
             "| Metric | Value |", "|---|---|",
             f"| Top-1 accuracy | {metrics['top1']:.1%} |", f"| Top-3 accuracy | {metrics['top3']:.1%} |",
             f"| Predictions above 50% confidence | {metrics['confident_share']:.1%} |",
             f"| Accuracy of those confident predictions | {(metrics['precision_when_confident'] or 0):.1%} |", ""]
    if "external_showdown" in metrics:
        ext = metrics["external_showdown"]
        lines += ["## Different sprite set", "",
                  f"{ext['images']} Pokémon Showdown sprites (first animation frame), a sprite set not in the training "
                  f"folders: **top-1 {ext['top1']:.1%}, top-3 {ext['top3']:.1%}**. Many Showdown sprites are animated "
                  "versions of game sprites the model did see, so this is not a real-world test. Photos, toys, cards and "
                  "fan art have not been measured and will score lower; see docs/IMPROVING_ACCURACY.md.", ""]
    lines += ["## By generation", "", "| Gen | Top-1 |", "|---|---|"]
    lines += [f"| {g} | {a:.1%} |" for g, a in metrics["by_generation"].items()]
    lines += ["", "## By held-out image style", "", "| Style | Images | Top-1 |", "|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {v['top1']:.1%} |" for k, v in metrics["by_image_kind"].items()]
    lines += ["", "![Confusion matrix](confusion_matrix.png)", ""]
    (RESULTS / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: metrics.get(k) for k in ("images", "top1", "top3", "confident_share",
                                                  "precision_when_confident", "external_showdown")}, indent=2))


if __name__ == "__main__":
    main()
