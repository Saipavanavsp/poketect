# Model evaluation

Held-out set: **1025 images**, one unseen image per Pokémon across **1025 classes**.

| Metric | Value |
|---|---|
| Top-1 accuracy | 97.5% |
| Top-3 accuracy | 99.2% |
| Predictions above 50% confidence | 86.3% |
| Accuracy of those confident predictions | 99.7% |

## Different sprite set

300 Pokémon Showdown sprites (first animation frame), a sprite set not in the training folders: **top-1 98.3%, top-3 99.3%**. Many Showdown sprites are animated versions of game sprites the model did see, so this is not a real-world test. Photos, toys, cards and fan art have not been measured and will score lower; see docs/IMPROVING_ACCURACY.md.

## By generation

| Gen | Top-1 |
|---|---|
| 1 | 96.7% |
| 2 | 99.0% |
| 3 | 97.8% |
| 4 | 97.2% |
| 5 | 96.8% |
| 6 | 98.6% |
| 7 | 98.9% |
| 8 | 100.0% |
| 9 | 94.2% |

## By held-out image style

| Style | Images | Top-1 |
|---|---|---|
| artwork_shiny | 116 | 99.1% |
| bw | 131 | 100.0% |
| crystal | 19 | 94.7% |
| emerald | 44 | 100.0% |
| home | 108 | 100.0% |
| home_shiny | 115 | 100.0% |
| platinum | 44 | 100.0% |
| sprite | 141 | 100.0% |
| sprite_back | 120 | 85.0% |
| sprite_shiny | 112 | 100.0% |
| xy | 75 | 92.0% |

![Confusion matrix](confusion_matrix.png)
