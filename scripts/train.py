"""Train the Pokémon identifier with transfer learning on the cache built by scripts/prepare_dataset.py.

GPU (default):  .\\.venv\\Scripts\\python.exe scripts\\train.py              EfficientNet-B0, 224 px, 24 epochs
CPU-only:       .\\.venv\\Scripts\\python.exe scripts\\train.py --cpu        MobileNetV2, 128 px, 6 epochs
Options:        --arch mobilenet_v2|efficientnet_b0  --img-size N  --epochs N  --workers N

Outputs: models/pokemon_cnn.pt (best checkpoint), models/pokemon_cnn.onnx, models/labels.json,
docs/results/history.json and training_curves.png.
"""
import argparse
import io
import json
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image, ImageFilter
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

from partial_view import crop_visible

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
MODELS = ROOT / "models"
RESULTS = ROOT / "docs" / "results"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def random_background(size: int) -> Image.Image:
    """White, solid colour, gradient or blurred noise - uploads rarely have transparent backgrounds."""
    kind = random.random()
    if kind < 0.35:
        return Image.new("RGB", (size, size), (255, 255, 255))
    if kind < 0.6:
        return Image.new("RGB", (size, size), tuple(random.randint(0, 255) for _ in range(3)))
    if kind < 0.8:
        a, b = np.random.randint(0, 256, 3), np.random.randint(0, 256, 3)
        t = np.linspace(0, 1, size)[:, None, None]
        return Image.fromarray(np.repeat((a * (1 - t) + b * t).astype(np.uint8), size, axis=1))
    noise = np.random.randint(0, 256, (size // 8, size // 8, 3), dtype=np.uint8)
    return Image.fromarray(noise).resize((size, size), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))


def flatten(img: Image.Image, background: Image.Image | None = None) -> Image.Image:
    img = img.convert("RGBA")
    bg = (background or Image.new("RGB", img.size, (255, 255, 255))).convert("RGBA").resize(img.size)
    bg.alpha_composite(img)
    return bg.convert("RGB")


class Degrade:
    """Simulate low-quality uploads: low resolution, blur, JPEG artefacts, sensor noise."""

    def __call__(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        if random.random() < 0.5:
            small = random.randint(24, 112)
            method = random.choice([Image.NEAREST, Image.BILINEAR, Image.BICUBIC])
            img = img.resize((small, small), Image.BILINEAR).resize((w, h), method)
        if random.random() < 0.3:
            img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.3, 2.0)))
        if random.random() < 0.5:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=random.randint(15, 85))
            img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        if random.random() < 0.15:
            arr = np.asarray(img, dtype=np.float32) + np.random.normal(0, random.uniform(4, 16), (h, w, 3))
            img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
        return img


def partial_view(img: Image.Image) -> Image.Image:
    """Keep only 15-90% of the Pokémon (by its own pixels), centred on a transparent square like an upload crop."""
    crop, _ = crop_visible(img, random.uniform(0.15, 0.9), np.random.default_rng(random.getrandbits(32)), tol=0.05)
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(crop.convert("RGBA"), ((side - crop.width) // 2, (side - crop.height) // 2))
    return canvas


class CacheImages(Dataset):
    def __init__(self, rows, index, size, train, partial_p=0.0):
        self.rows, self.index, self.train, self.partial_p = rows, index, train, partial_p
        style = [
            transforms.RandomHorizontalFlip(),
            transforms.RandomApply([transforms.RandomRotation(20)], p=0.5),
            transforms.RandomPerspective(0.25, p=0.25),
            transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.4, hue=0.04),
            transforms.RandomGrayscale(0.05),
            Degrade(),
        ]
        self.aug = transforms.Compose(
            [transforms.RandomResizedCrop(size, scale=(0.35, 1.0), ratio=(0.75, 1.33))] + style)
        # A partial view is already a tight crop: only jitter it a little more.
        self.aug_partial = transforms.Compose(
            [transforms.RandomResizedCrop(size, scale=(0.75, 1.0), ratio=(0.85, 1.18))] + style)
        self.plain = transforms.Resize((size, size))
        self.to_tensor = transforms.Compose([transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
        self.erase = transforms.RandomErasing(p=0.2, scale=(0.02, 0.15))

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        img = Image.open(CACHE / row["path"])
        label = self.index[row["label"]]
        if self.train and random.random() < self.partial_p:
            img = partial_view(img)
            x = self.erase(self.to_tensor(self.aug_partial(flatten(img, random_background(img.width)))))
        elif self.train:
            x = self.erase(self.to_tensor(self.aug(flatten(img, random_background(img.width)))))
        else:
            x = self.to_tensor(self.plain(pad_square(flatten(img))))
        return x, label


def pad_square(img: Image.Image) -> Image.Image:
    side = max(img.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def seed_worker(worker_id):
    seed = torch.initial_seed() % 2**32
    random.seed(seed + worker_id)
    np.random.seed((seed + worker_id) % 2**32)


def build_model(arch, num_classes, pretrained=True):
    if arch == "convnext_tiny":
        model = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None)
        model.classifier[2] = nn.Linear(model.classifier[2].in_features, num_classes)
    elif arch == "efficientnet_v2_s":
        model = models.efficientnet_v2_s(weights=models.EfficientNet_V2_S_Weights.IMAGENET1K_V1 if pretrained else None)
        model.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(model.classifier[1].in_features, num_classes))
    elif arch == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None)
        model.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(model.classifier[1].in_features, num_classes))
    else:
        model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V2 if pretrained else None)
        model.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(model.last_channel, num_classes))
    return model


def run_epoch(model, loader, device, criterion, optimizer=None, scaler=None, scheduler=None):
    training = optimizer is not None
    model.train(training)
    total, loss_sum, top1, top3 = 0, 0.0, 0, 0
    with torch.set_grad_enabled(training):
        for x, y in loader:
            x = x.to(device, non_blocking=True).to(memory_format=torch.channels_last)
            y = y.to(device, non_blocking=True)
            # bfloat16: on this GPU fp16 + channels_last hits ~7x slower depthwise-conv kernels.
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits = model(x)
                loss = criterion(logits, y)
            if training:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
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
    a.plot(epochs, [h["val_loss"] for h in history], label="val (clean)", color="#8c8279")
    a.set_title("Loss"), a.set_xlabel("epoch"), a.legend()
    b.plot(epochs, [h["train_acc"] for h in history], label="train top-1", color="#7a1f2b")
    b.plot(epochs, [h["val_acc"] for h in history], label="val clean top-1", color="#8c8279")
    b.plot(epochs, [h["hard_acc"] for h in history], label="val hard top-1", color="#c9a227")
    b.plot(epochs, [h["partial_acc"] for h in history], label="val 30% visible top-1", color="#2b6f7a")
    b.set_title("Accuracy"), b.set_xlabel("epoch"), b.set_ylim(0, 1), b.legend()
    fig.tight_layout()
    fig.savefig(RESULTS / "training_curves.png", dpi=130)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", action="store_true", help="force CPU mode (MobileNetV2, 128 px, fewer epochs)")
    parser.add_argument("--arch", choices=["convnext_tiny", "efficientnet_v2_s", "efficientnet_b0", "mobilenet_v2"])
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--img-size", type=int)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--partial", type=float, default=0.5,
                        help="share of training samples cropped to a partial view (15-90%% of the Pokémon)")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    gpu = device.type == "cuda"
    arch = args.arch or ("efficientnet_b0" if gpu else "mobilenet_v2")
    img_size = args.img_size or (224 if gpu else 128)
    epochs = args.epochs or (24 if gpu else 6)
    random.seed(0), np.random.seed(0), torch.manual_seed(0)
    MODELS.mkdir(exist_ok=True), RESULTS.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CACHE / "manifest.json").read_text())
    classes = manifest["classes"]
    index = {c: i for i, c in enumerate(classes)}
    split = {s: [r for r in manifest["images"] if r["split"] == s]
             for s in ("train", "val", "val_hard", "val_partial30", "test_real")}
    print(f"device={device} arch={arch} img_size={img_size} epochs={epochs} classes={len(classes)} "
          + " ".join(f"{k}={len(v)}" for k, v in split.items()))

    # Balance classes: Gen 1 has real-world photos on top of sprites, so sample every class equally often.
    counts = Counter(r["label"] for r in split["train"])
    weights = [1.0 / counts[r["label"]] for r in split["train"]]
    sampler = WeightedRandomSampler(weights, num_samples=len(split["train"]), replacement=True)
    loader_kw = dict(num_workers=args.workers, persistent_workers=args.workers > 0, pin_memory=gpu,
                     worker_init_fn=seed_worker)
    train_loader = DataLoader(CacheImages(split["train"], index, img_size, True, args.partial),
                              batch_size=args.batch_size, sampler=sampler, drop_last=True, **loader_kw)
    # Eval sets are small: a few workers each (on Windows every worker is a ~6 s, ~600 MB process spawn).
    eval_kw = {**loader_kw, "num_workers": min(2, args.workers), "persistent_workers": args.workers > 0}
    eval_loaders = {name: DataLoader(CacheImages(split[s], index, img_size, False), batch_size=128, **eval_kw)
                    for name, s in [("val", "val"), ("hard", "val_hard"), ("partial", "val_partial30")]}

    model = build_model(arch, len(classes)).to(device).to(memory_format=torch.channels_last)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    scaler = torch.amp.GradScaler(enabled=False)  # not needed with bfloat16
    torch.backends.cudnn.benchmark = gpu
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.05)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=epochs * len(train_loader),
                                                    pct_start=0.1)
    history, best = [], -1.0
    for epoch in range(1, epochs + 1):
        start = time.time()
        tr_loss, tr_acc, _ = run_epoch(model, train_loader, device, criterion, optimizer, scaler, scheduler)
        entry = {"epoch": epoch, "train_loss": tr_loss, "train_acc": tr_acc}
        for name, loader in eval_loaders.items():
            loss, acc, top3 = run_epoch(model, loader, device, criterion)
            entry |= {f"{name}_loss": loss, f"{name}_acc": acc, f"{name}_top3": top3}
        history.append(entry)
        # Model selection never looks at the real-world test set.
        score = (entry["val_acc"] + entry["hard_acc"] + entry["partial_acc"]) / 3
        flag = ""
        if score > best:
            best = score
            torch.save({"state_dict": model.state_dict(), "classes": classes, "img_size": img_size, "arch": arch,
                        "epoch": epoch, **{k: entry[k] for k in ("val_acc", "hard_acc", "partial_acc")}},
                       MODELS / "pokemon_cnn.pt")
            flag = "  * saved"
        print(f"epoch {epoch:2d}/{epochs} loss {tr_loss:.3f}/{entry['val_loss']:.3f} train {tr_acc:.3f} "
              f"val {entry['val_acc']:.3f} hard {entry['hard_acc']:.3f} "
              f"30%-visible {entry['partial_acc']:.3f} (top3 {entry['partial_top3']:.3f}) "
              f"[{time.time() - start:.0f}s]{flag}", flush=True)

    (RESULTS / "history.json").write_text(json.dumps(history, indent=1))
    plot_history(history)

    ckpt = torch.load(MODELS / "pokemon_cnn.pt", map_location="cpu")
    model = build_model(arch, len(classes), pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    torch.onnx.export(model, torch.randn(1, 3, img_size, img_size), MODELS / "pokemon_cnn.onnx",
                      input_names=["input"], output_names=["logits"], opset_version=17,
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}, dynamo=False)
    (MODELS / "labels.json").write_text(json.dumps({"img_size": img_size, "arch": arch, "classes": classes}))
    print(f"best epoch {ckpt['epoch']}: val {ckpt['val_acc']:.3f}, hard {ckpt['hard_acc']:.3f}, "
          f"30%-visible {ckpt['partial_acc']:.3f}; exported ONNX")


if __name__ == "__main__":
    main()
