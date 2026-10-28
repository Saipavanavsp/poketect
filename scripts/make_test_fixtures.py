"""Cut a small, committed subset of data/processed for the API tests (CI has no PokéAPI cache)."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed"
OUT = ROOT / "backend" / "tests" / "fixtures"
SPECIES = {"charizard", "infernape", "sceptile", "goodra", "snorlax", "lycanroc", "sirfetchd", "pikachu", "tauros"}


def load(name):
    return json.loads((SRC / f"{name}.json").read_text(encoding="utf-8"))


def main():
    pokemon = load("pokemon")
    chain_ids = {p["evolution_chain_id"] for p in pokemon if p["name"] in SPECIES}
    keep = [p for p in pokemon if p["evolution_chain_id"] in chain_ids]
    ids = {p["id"] for p in keep}
    move_names = {m["move"] for p in keep for m in p["moves"]}
    ability_names = {a["name"] for p in keep for a in p["abilities"]}
    subsets = {
        "pokemon": keep,
        "evolution_chains": [c for c in load("evolution_chains") if c["id"] in chain_ids],
        "moves": [m for m in load("moves") if m["name"] in move_names],
        "abilities": [a for a in load("abilities") if a["name"] in ability_names],
        "encounters": [e for e in load("encounters") if e["pokemon_id"] in ids],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in subsets.items():
        (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {len(rows)}")
    shutil.copy2(ROOT / "data" / "images" / "pikachu" / "artwork.png", OUT / "pikachu.png")


if __name__ == "__main__":
    main()
