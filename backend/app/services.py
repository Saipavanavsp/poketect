"""Query + serialisation helpers shared by the REST routes and the Claude chat tools."""
import difflib
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import geo, models

METHOD_ORDER = {"level-up": 0, "machine": 1, "egg": 2, "tutor": 3}


def normalize(name: str) -> str:
    """'Sirfetch’d' -> 'sirfetchd', 'Mr. Mime' -> 'mr-mime', 'Flabébé' -> 'flabebe'."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().strip()
    text = re.sub(r"['’.:]", "", text)
    return re.sub(r"[\s_]+", "-", text)


def artwork(p: models.Pokemon) -> str | None:
    return p.images.get("artwork") or p.images.get("home") or p.images.get("sprite")


def summary(p: models.Pokemon) -> dict:
    return {
        "id": p.id, "name": p.name, "display_name": p.display_name, "types": p.types,
        "generation": p.generation, "image": artwork(p), "sprite": p.images.get("sprite"),
        "stats_total": sum(v or 0 for v in p.stats.values()),
    }


def find_pokemon(db: Session, query: str | int) -> models.Pokemon | None:
    if isinstance(query, int) or str(query).isdigit():
        return db.get(models.Pokemon, int(query))
    key = normalize(str(query))
    hit = db.scalar(select(models.Pokemon).where(models.Pokemon.name == key))
    if hit:
        return hit
    names = list(db.scalars(select(models.Pokemon.name)))
    close = difflib.get_close_matches(key, names, n=1, cutoff=0.75)
    return db.scalar(select(models.Pokemon).where(models.Pokemon.name == close[0])) if close else None


def list_pokemon(db: Session, q: str | None = None, type_: str | None = None, generation: int | None = None,
                 limit: int = 2000, offset: int = 0) -> list[dict]:
    stmt = select(models.Pokemon).order_by(models.Pokemon.id)
    if generation:
        stmt = stmt.where(models.Pokemon.generation == generation)
    rows = db.scalars(stmt).all()
    if type_:
        rows = [p for p in rows if type_ in p.types]
    if q:
        key = normalize(q)
        rows = [p for p in rows if key in p.name or key == str(p.id)]
    return [summary(p) for p in rows[offset: offset + limit]]


def moves_for(db: Session, p: models.Pokemon) -> list[dict]:
    rows = db.scalars(select(models.PokemonMove).where(models.PokemonMove.pokemon_id == p.id)
                      .options(selectinload(models.PokemonMove.move))).all()
    out = [{
        "name": r.move.name, "display_name": r.move.display_name, "type": r.move.type,
        "power": r.move.power, "accuracy": r.move.accuracy, "pp": r.move.pp,
        "damage_class": r.move.damage_class, "effect": r.move.effect,
        "method": r.method, "level": r.level,
    } for r in rows]
    return sorted(out, key=lambda m: (METHOD_ORDER.get(m["method"], 9), m["level"], m["display_name"]))


def pick_top_moves(p: models.Pokemon, wanted: list[str]) -> list[str]:
    """Keep the requested moves the Pokémon can learn; top up to 4 with its strongest same-type moves."""
    learnable = {pm.move.name: pm.move for pm in p.moves}
    chosen = [m for m in wanted if m in learnable]
    if len(chosen) < 4:
        extras = sorted((m for m in learnable.values() if m.power and m.name not in chosen),
                        key=lambda m: (m.type in p.types, m.power), reverse=True)
        chosen += [m.name for m in extras[: 4 - len(chosen)]]
    return chosen


def evolution_for(db: Session, p: models.Pokemon) -> dict | None:
    if not p.evolution_chain_id:
        return None
    chain = db.get(models.EvolutionChain, p.evolution_chain_id).chain
    names = set()

    def collect(node):
        names.add(node["species"])
        for child in node["evolves_to"]:
            collect(child)
    collect(chain)
    lookup = {row.name: row for row in db.scalars(select(models.Pokemon).where(models.Pokemon.name.in_(names)))}

    def enrich(node):
        row = lookup.get(node["species"])
        return {
            "name": node["species"], "id": row.id if row else None,
            "display_name": row.display_name if row else node["species"].title(),
            "image": artwork(row) if row else None, "types": row.types if row else [],
            "condition": node["condition"], "evolves_to": [enrich(c) for c in node["evolves_to"]],
        }
    return enrich(chain)


def encounters_for(db: Session, p: models.Pokemon) -> list[dict]:
    rows = db.scalars(select(models.Encounter).where(models.Encounter.pokemon_id == p.id)).all()
    return [{
        "location": r.location, "location_display": r.location_display, "area": r.location_area,
        "region": r.region, "versions": r.versions, "methods": r.methods,
        "min_level": r.min_level, "max_level": r.max_level, "chance": r.max_chance,
        "map_place": geo.map_location(r.region, r.location),
    } for r in rows]


def detail(db: Session, p: models.Pokemon) -> dict:
    abilities = {a.name: a for a in db.scalars(select(models.Ability).where(
        models.Ability.name.in_([a["name"] for a in p.abilities])))}
    return {
        **summary(p),
        "genus": p.genus, "height": p.height, "weight": p.weight, "base_experience": p.base_experience,
        "abilities": [{**a, "display_name": abilities[a["name"]].display_name if a["name"] in abilities else a["name"],
                       "effect": abilities[a["name"]].effect if a["name"] in abilities else ""} for a in p.abilities],
        "stats": p.stats, "description": p.description, "color": p.color, "habitat": p.habitat,
        "is_legendary": p.is_legendary, "is_mythical": p.is_mythical, "capture_rate": p.capture_rate,
        "evolves_from": p.evolves_from, "images": p.images,
        "moves": moves_for(db, p),
        "evolution": evolution_for(db, p),
        "encounters": encounters_for(db, p),
    }


def trainer_profile(db: Session, trainer_id: int = 1) -> dict | None:
    t = db.get(models.Trainer, trainer_id)
    if not t:
        return None
    moves = {m.name: m for m in db.scalars(select(models.Move).where(
        models.Move.name.in_([n for member in t.team for n in member.top_moves])))}
    return {
        "id": t.id, "name": t.name, "height_ft": t.height_ft, "weight_kg": t.weight_kg,
        "hometown": t.hometown, "region": t.region, "bio": t.bio,
        "badges": [{"id": b.id, "name": b.name, "region": b.region, "gym_leader": b.gym_leader,
                    "type": b.type, "order": b.order, "earned": b.earned} for b in t.badges],
        "team": [{
            "id": m.id, "slot": m.slot, "level": m.level, "nickname": m.nickname,
            "pokemon": summary(m.pokemon),
            "top_moves": [{"name": n, "display_name": moves[n].display_name, "type": moves[n].type,
                           "power": moves[n].power, "accuracy": moves[n].accuracy, "pp": moves[n].pp}
                          for n in m.top_moves if n in moves],
        } for m in t.team],
    }


def _rows(objs, fields):
    return [{f: getattr(o, f) for f in fields} for o in objs]


def gyms(db: Session, region: str | None = None) -> list[dict]:
    stmt = select(models.Gym).order_by(models.Gym.region, models.Gym.order)
    if region:
        stmt = stmt.where(models.Gym.region == region)
    return _rows(db.scalars(stmt), ["id", "region", "city", "leader", "type", "badge", "order", "x", "y"])


def centers(db: Session, region: str | None = None) -> list[dict]:
    stmt = select(models.PokemonCenter).order_by(models.PokemonCenter.id)
    if region:
        stmt = stmt.where(models.PokemonCenter.region == region)
    return _rows(db.scalars(stmt), ["id", "region", "name", "city", "x", "y"])


def places(db: Session, region: str | None = None) -> list[dict]:
    stmt = select(models.Place).order_by(models.Place.id)
    if region:
        stmt = stmt.where(models.Place.region == region)
    return _rows(db.scalars(stmt), ["id", "slug", "region", "name", "kind", "x", "y"])


def place_by_name(db: Session, region: str, name: str) -> dict | None:
    key = normalize(name)
    for place in places(db, region):
        if key in (place["slug"], normalize(place["name"])) or place["slug"].startswith(key):
            return place
    return None


def pokemon_at_place(db: Session, region: str, slug: str) -> list[dict]:
    rows = db.scalars(select(models.Encounter).where(models.Encounter.region == region)).all()
    ids = sorted({r.pokemon_id for r in rows if geo.map_location(region, r.location) == slug})
    if not ids:
        return []
    found = db.scalars(select(models.Pokemon).where(models.Pokemon.id.in_(ids)).order_by(models.Pokemon.id))
    return [summary(p) for p in found]
