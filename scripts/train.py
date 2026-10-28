"""Train the Pokémon identifier: MobileNetV2 transfer learning on data/images (+ optional Kaggle images).

GPU (default):  .\\.venv\\Scripts\\python.exe scripts\\train.py
CPU-only:       .\\.venv\\Scripts\\python.exe scripts\\train.py --cpu      (128px, 8 epochs)
Extra data:     .\\.venv\\Scripts\\python.exe scripts\\train.py --extra-dir data\\kaggle

Outputs: models/pokemon_cnn.pt (best by val accuracy), models/pokemon_cnn.onnx, models/labels.json,
models/split.json, and plots/metrics in docs/results/.
"""
import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageFilter
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "data" / "images"
MODELS = ROOT / "models"
RESULTS = ROOT / "docs" / "results"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def load_rgba(path: Path, base: int) -> Image.Image:
    """Open, crop to the visible sprite (transparent padding removed) and fit into a base x base square."""
    img = Image.open(path).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    scale = base / max(img.size)  # fill the square, up or down, exactly like inference does
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                     Image.LANCZOS if scale < 1 else Image.BILINEAR)
    canvas = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    canvas.paste(img, ((base - img.width) // 2, (base - img.height) // 2))
    return canvas


def random_background(size: int) -> Image.Image:
    """Solid colour, gradient or noise - real photos/screenshots rarely have white backgrounds."""
    kind = random.random()
    if kind < 0.35:
        return Image.new("RGB", (size, size), (255, 255, 255))
    if kind < 0.65:
        return Image.new("RGB", (size, size), tuple(random.randint(0, 255) for _ in range(3)))
    if kind < 0.85:
        a, b = np.random.randint(0, 256, 3), np.random.randint(0, 256, 3)
        t = np.linspace(0, 1, size)[:, None, None]
        grad = (a * (1 - t) + b * t).astype(np.uint8)
        return Image.fromarray(np.repeat(grad, size, axis=1))
    return Image.fromarray(np.random.randint(0, 256, (size, size, 3), dtype=np.uint8)).filter(ImageFilter.GaussianBlur(3))


def flatten(img: Image.Image, background: Image.Image | None = None) -> Image.Image:
    bg = (background or Image.new("RGB", img.size, (255, 255, 255))).convert("RGBA")
    bg.alpha_composite(img)
    return bg.convert("RGB")


class PokemonImages(Dataset):
    def __init__(self, items, size, train):
        self.items, self.train = items, train
        self.aug = transforms.Compose([
            transforms.RandomResizedCrop(size, scale=(0.6, 1.0), ratio=(0.8, 1.25)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.03),
            transforms.RandomApply([transforms.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.25),
        ])
        self.plain = transforms.Resize((size, size))
        self.to_tensor = transforms.Compose([transforms.ToTensor(), transforms.Normalize(MEAN, STD)])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        img, label = self.items[i]
        if self.train:
            out = self.aug(flatten(img, random_background(img.width)))
        else:
            out = self.plain(flatten(img))
        return self.to_tensor(out), label


def collect(extra_dir: Path | None):
    classes = sorted(d.name for d in IMAGES.iterdir() if d.is_dir() and any(d.iterdir()))
    files = {c: sorted(p for p in (IMAGES / c).iterdir() if p.suffix.lower() in IMAGE_EXTS) for c in classes}
    if extra_dir and extra_dir.exists():
        for d in extra_dir.iterdir():
            key = d.name.lower().replace(" ", "-").replace("'", "").replace(".", "")
            if d.is_dir() and key in files:
                files[key] += sorted(p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    return classes, files


def split(classes, files, seed=42):
    """Hold out one image per class (never the official artwork, which is the cleanest training example)."""
    rng = random.Random(seed)
    train, val = [], []
    for c in classes:
        paths = list(files[c])
        candidates = [p for p in paths if p.stem not in ("artwork",)]
        if len(paths) >= 3 and candidates:
            held = rng.choice(candidates)
            val.append((c, held))
            paths.remove(held)
        train += [(c, p) for p in paths]
    return train, val


def build_model(num_classes):
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V2)
    model.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(model.last_channel, num_classes))
    return model


def run_epoch(model, loader, device, criterion, optimizer=None, scaler=None):
    training = optimizer is not None
    model.train(training)
    total, loss_sum, top1, top3 = 0, 0.0, 0, 0
    with torch.set_grad_enabled(training):
        for x, y in loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                logits = model(x)
                loss = criterion(logits, y)
            if training:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total += y.size(0)
            loss_sum += loss.item() * y.size(0)
            pred = logits.topk(3, dim=1).indices
            top1 += (pred[:, 0] == y).sum().item()
            top3 += (pred == y[:, None]).any(dim=1).sum().item()
    return loss_sum / total, top1 / total, top3 / total


def plot_history(history):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    epochs = [h["epoch"] for h in history]
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4))
    a.plot(epochs, [h["train_loss"] for h in history], label="train", color="#7a1f2b")
    a.plot(epochs, [h["val_loss"] for h in history], label="val", color="#8c8279")
    a.set_title("Loss"), a.set_xlabel("epoch"), a.legend()
    b.plot(epochs, [h["train_acc"] for h in history], label="train top-1", color="#7a1f2b")
    b.plot(epochs, [h["val_acc"] for h in history], label="val top-1", color="#8c8279")
    b.plot(epochs, [h["val_top3"] for h in history], label="val top-3", color="#c9a227", linestyle="--")
    b.set_title("Accuracy"), b.set_xlabel("epoch"), b.set_ylim(0, 1), b.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "training_curves.png", dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", action="store_true", help="force CPU mode (smaller images, fewer epochs)")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--img-size", type=int)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--extra-dir", type=Path, help="optional folder of <pokemon-name>/ image folders (e.g. Kaggle)")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    img_size = args.img_size or (160 if device.type == "cuda" else 128)
    epochs = args.epochs or (30 if device.type == "cuda" else 8)
    random.seed(0), np.random.seed(0), torch.manual_seed(0)
    MODELS.mkdir(exist_ok=True), RESULTS.mkdir(parents=True, exist_ok=True)
    print(f"device={device} img_size={img_size} epochs={epochs}")

    classes, files = collect(args.extra_dir)
    index = {c: i for i, c in enumerate(classes)}
    train_paths, val_paths = split(classes, files)
    print(f"{len(classes)} classes, {len(train_paths)} train / {len(val_paths)} val images")
    (MODELS / "split.json").write_text(json.dumps({"val": [[c, str(p.relative_to(ROOT))] for c, p in val_paths]}))

    base = int(img_size * 1.15)
    t0 = time.time()
    train_items = [(load_rgba(p, base), index[c]) for c, p in train_paths]
    val_items = [(load_rgba(p, base), index[c]) for c, p in val_paths]
    print(f"loaded images in {time.time() - t0:.0f}s")

    train_loader = DataLoader(PokemonImages(train_items, img_size, True), batch_size=args.batch_size, shuffle=True,
                              pin_memory=device.type == "cuda", drop_last=True)
    val_loader = DataLoader(PokemonImages(val_items, img_size, False), batch_size=128)

    model = build_model(len(classes)).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    warmup = min(3, max(1, epochs // 6))

    # Stage 1: train only the new head; stage 2: fine-tune everything with a cosine schedule.
    for p in model.features.parameters():
        p.requires_grad = False
    optimizer = torch.optim.AdamW(model.classifier.parameters(), lr=3e-3, weight_decay=1e-4)
    history, best = [], 0.0
    for epoch in range(1, epochs + 1):
        if epoch == warmup + 1:
            for p in model.features.parameters():
                p.requires_grad = True
            optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs - warmup)
        start = time.time()
        tr_loss, tr_acc, _ = run_epoch(model, train_loader, device, criterion, optimizer, scaler)
        va_loss, va_acc, va_top3 = run_epoch(model, val_loader, device, criterion)
        if epoch > warmup:
            scheduler.step()
        history.append({"epoch": epoch, "train_loss": tr_loss, "train_acc": tr_acc,
                        "val_loss": va_loss, "val_acc": va_acc, "val_top3": va_top3})
        flag = ""
        if va_acc > best:
            best = va_acc
            torch.save({"state_dict": model.state_dict(), "classes": classes, "img_size": img_size,
                        "arch": "mobilenet_v2", "epoch": epoch, "val_acc": va_acc, "val_top3": va_top3},
                       MODELS / "pokemon_cnn.pt")
            flag = "  * saved"
        print(f"epoch {epoch:2d}/{epochs} loss {tr_loss:.3f}/{va_loss:.3f} acc {tr_acc:.3f}/{va_acc:.3f} "
              f"top3 {va_top3:.3f} ({time.time() - start:.0f}s){flag}")

    (RESULTS / "history.json").write_text(json.dumps(history, indent=1))
    plot_history(history)

    # Export the best checkpoint to ONNX for the API server and the in-browser demo.
    ckpt = torch.load(MODELS / "pokemon_cnn.pt", map_location="cpu")
    model = build_model(len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    torch.onnx.export(model, torch.randn(1, 3, img_size, img_size), MODELS / "pokemon_cnn.onnx",
                      input_names=["input"], output_names=["logits"], opset_version=17,
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}, dynamo=False)
    (MODELS / "labels.json").write_text(json.dumps({"img_size": img_size, "classes": classes}))
    print(f"best val top-1 {ckpt['val_acc']:.3f} (epoch {ckpt['epoch']}); exported models/pokemon_cnn.onnx")


if __name__ == "__main__":
    main()
