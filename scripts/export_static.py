"""Export the SQLite data + trained model as static files for the serverless (GitHub Pages / Vercel) build.

    .\\.venv\\Scripts\\python.exe scripts\\export_static.py

Writes frontend/public/data/*.json (same shapes the API returns) and frontend/public/model/.
"""
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import geo, models, services  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seed_data import REGIONS  # noqa: E402

OUT = ROOT / "frontend" / "public" / "data"
MODEL_OUT = ROOT / "frontend" / "public" / "model"


def dump(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    db = SessionLocal()
    if OUT.exists():
        shutil.rmtree(OUT)

    index = services.list_pokemon(db)
    dump(OUT / "index.json", index)

    moves = {m.name: {"display_name": m.display_name, "type": m.type, "power": m.power, "accuracy": m.accuracy,
                      "pp": m.pp, "damage_class": m.damage_class, "effect": m.effect}
             for m in db.query(models.Move)}
    dump(OUT / "moves.json", moves)

    place_pokemon = defaultdict(lambda: defaultdict(set))
    for p in db.query(models.Pokemon).order_by(models.Pokemon.id):
        d = services.detail(db, p)
        d["moves"] = [[m["name"], m["method"], m["level"]] for m in d["moves"]]  # expanded client-side via moves.json
        for e in d["encounters"]:
            e.pop("area", None)
            if e["map_place"]:
                place_pokemon[e["region"]][e["map_place"]].add(p.id)
        dump(OUT / "pokemon" / f"{p.id}.json", d)

    geometry = geo.region_geometry()
    dump(OUT / "map.json", {region: {**geometry[region], "places": services.places(db, region),
                                     "gyms": services.gyms(db, region), "centers": services.centers(db, region),
                                     "place_pokemon": {k: sorted(v) for k, v in place_pokemon[region].items()}}
                            for region in REGIONS})
    dump(OUT / "trainer.json", services.trainer_profile(db))

    MODEL_OUT.mkdir(parents=True, exist_ok=True)
    for name in ("pokemon_cnn.onnx", "labels.json"):
        src = ROOT / "models" / name
        if src.exists():
            shutil.copy2(src, MODEL_OUT / name)
        else:
            print(f"  (skipped {name}: train the model first)")
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"Exported {len(index)} Pokémon, {len(moves)} moves to frontend/public/data ({size:.1f} MB)")
    db.close()


if __name__ == "__main__":
    main()
