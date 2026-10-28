# Improving identification accuracy

The model is trained on official artwork and in-game sprites from PokéAPI (about 10 images per
Pokémon). It scores very well on held-out sprites, but photos of toys, cards, fan art or screenshots
look different. These steps help, roughly in order of payoff.

## 1. Add a Kaggle image dataset (biggest win)

Kaggle needs a free account, so this is a manual download:

1. Sign in at kaggle.com and open a Pokémon image dataset, for example
   "Pokemon Images and Types" or "7,000 Labeled Pokemon" (search "pokemon images").
   Check each dataset's licence before using it.
2. Click **Download**, unzip, and arrange it as one folder per Pokémon:
   `data/kaggle/pikachu/*.jpg`, `data/kaggle/charizard/*.png`, ...
   Folder names are matched to PokéAPI names (lower case, spaces become `-`, apostrophes and dots
   removed, so `Mr. Mime` becomes `mr-mime`).
3. Retrain with the extra images:

```powershell
.\.venv\Scripts\python.exe scripts\train.py --extra-dir data\kaggle
.\.venv\Scripts\python.exe scripts\evaluate.py
```

## 2. Other levers

- **Bigger input / backbone**: `--img-size 224`, or swap MobileNetV2 for ResNet50 or EfficientNet in
  `build_model()`. More accurate, slower, and a larger file for the browser.
- **More epochs** with stronger augmentation (random erasing, perspective) once extra data is in.
- **Test-time augmentation**: average predictions over the image and its horizontal flip.
- **Hard-example review**: `docs/results/confusion_matrix.png` shows which look-alikes get mixed up
  (often regional forms and evolution relatives). Add images for those classes first.
- **Background removal** before inference for busy photos.

## CPU-only training

```powershell
.\.venv\Scripts\python.exe scripts\train.py --cpu            # 128 px, 8 epochs
.\.venv\Scripts\python.exe scripts\train.py --cpu --epochs 4  # quicker smoke run
```
