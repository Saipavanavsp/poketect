"""Load data/processed/*.json and the seed data into SQLite (data/pokedex.db).

Run after fetch_data.py:  .\\.venv\\Scripts\\python.exe scripts\\load_db.py
Re-running rebuilds the Pokémon tables but keeps any trainer edits unless --reset-trainer.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import geo, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed_data import REGIONS, TRAINER  # noqa: E402
from app.services import pick_top_moves  # noqa: E402

PROCESSED = ROOT / "data" / "processed"


def load(name, folder=PROCESSED):
    return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))


def seed_trainer(db):
    trainer = models.Trainer(**{k: TRAINER[k] for k in ("id", "name", "height_ft", "weight_kg", "hometown", "region", "bio")})
    for region, spec in REGIONS.items():
        for order, (_, leader, type_, badge) in enumerate(spec["gyms"], 1):
            trainer.badges.append(models.Badge(name=badge, region=region, gym_leader=leader, type=type_,
                                               order=order, earned=region == TRAINER["earned_badges"]))
    db.add(trainer)
    db.flush()
    by_name = {p.name: p for p in db.query(models.Pokemon).filter(
        models.Pokemon.name.in_([t[0] for t in TRAINER["team"]]))}
    for slot, (name, level, wanted) in enumerate(TRAINER["team"], 1):
        pokemon = by_name[name]
        trainer.team.append(models.TeamMember(pokemon_id=pokemon.id, slot=slot, level=level,
                                              top_moves=pick_top_moves(pokemon, wanted)))


def populate(db, folder=PROCESSED, reset_trainer=False):
    """(Re)build every table from processed JSON in `folder`. Trainer edits survive unless reset_trainer."""
    Base.metadata.create_all(db.get_bind())
    keep_trainer = not reset_trainer and db.query(models.Trainer).count() > 0

    for table in [models.Encounter, models.PokemonMove, models.Move, models.Ability, models.Place,
                  models.Gym, models.PokemonCenter]:
        db.query(table).delete()
    if not keep_trainer:
        for table in [models.TeamMember, models.Badge, models.Trainer]:
            db.query(table).delete()
    db.query(models.Pokemon).delete()
    db.query(models.EvolutionChain).delete()
    db.commit()

    db.add_all(models.EvolutionChain(id=c["id"], chain=c["chain"]) for c in load("evolution_chains", folder))
    moves = load("moves", folder)
    db.add_all(models.Move(**m) for m in moves)
    db.add_all(models.Ability(**a) for a in load("abilities", folder))
    db.flush()
    move_ids = {m["name"]: m["id"] for m in moves}

    for p in load("pokemon", folder):
        learnset = p.pop("moves")
        p.pop("variety")
        row = models.Pokemon(**p)
        row.moves = [models.PokemonMove(move_id=move_ids[m["move"]], method=m["method"], level=m["level"])
                     for m in learnset if m["move"] in move_ids]
        db.add(row)
    db.flush()

    db.add_all(models.Encounter(**e) for e in load("encounters", folder))
    db.add_all(models.Place(**p) for p in geo.build_places())
    db.add_all(models.Gym(**g) for g in geo.build_gyms())
    db.add_all(models.PokemonCenter(**c) for c in geo.build_centers())
    if not keep_trainer:
        seed_trainer(db)
    db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-trainer", action="store_true")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    db = SessionLocal()
    populate(db, reset_trainer=args.reset_trainer)
    counts = {t.__tablename__: db.query(t).count() for t in [
        models.Pokemon, models.Move, models.PokemonMove, models.EvolutionChain, models.Encounter,
        models.Place, models.Gym, models.PokemonCenter, models.TeamMember, models.Badge]}
    print("Loaded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    db.close()


if __name__ == "__main__":
    main()
