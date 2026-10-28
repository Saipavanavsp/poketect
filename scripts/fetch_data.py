"""Download Pokémon data and images from PokéAPI (https://pokeapi.co).

Every HTTP response is cached under data/raw/, so re-running is fast and only
fetches what is missing. Processed JSON lands in data/processed/ and is then
loaded into SQLite by scripts/load_db.py.

Usage (PowerShell, from the project root):
    .\\.venv\\Scripts\\python.exe scripts\\fetch_data.py               # all 1025 Pokémon
    .\\.venv\\Scripts\\python.exe scripts\\fetch_data.py --max-id 649  # Gen 1-5 only
    .\\.venv\\Scripts\\python.exe scripts\\fetch_data.py --skip-images
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
IMAGES = ROOT / "data" / "images"
API = "https://pokeapi.co/api/v2"

# Team members that must always be present, whatever --max-id says.
REQUIRED = ["charizard", "infernape", "sceptile", "goodra", "snorlax", "lycanroc", "sirfetchd"]

GENERATIONS = {
    "generation-i": 1, "generation-ii": 2, "generation-iii": 3, "generation-iv": 4,
    "generation-v": 5, "generation-vi": 6, "generation-vii": 7, "generation-viii": 8,
    "generation-ix": 9,
}


class RateLimiter:
    """Global minimum interval between requests, shared by all worker threads."""

    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=6, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = "pokedex-ai-fan-project/1.0 (educational)"
    return session


SESSION = make_session()
LIMITER = RateLimiter(per_second=20)


def get_json(path: str) -> dict:
    """GET an API path (e.g. 'pokemon/25'), cached to data/raw/<path>.json."""
    path = path.replace(API + "/", "").strip("/")
    cache = RAW / (re.sub(r'[?&=<>:"|*]', "_", path) + ".json")  # Windows-safe filename
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    LIMITER.wait()
    resp = SESSION.get(f"{API}/{path}", timeout=30)
    resp.raise_for_status()
    data = resp.json()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    LIMITER.wait()
    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! image failed {url}: {exc}", file=sys.stderr)
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return True


def parallel(fn, items, desc: str, workers: int = 12):
    results, errors = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, item): item for item in items}
        for i, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            try:
                results[item] = fut.result()
            except Exception as exc:  # keep going, report at the end
                errors.append((item, exc))
            if i % 100 == 0 or i == len(items):
                print(f"  {desc}: {i}/{len(items)}")
    for item, exc in errors:
        print(f"  ! {desc} failed for {item}: {exc}", file=sys.stderr)
    return results, errors


def id_from_url(url: str) -> int:
    return int(url.rstrip("/").split("/")[-1])


def english(entries: list, key: str = "name") -> str | None:
    for entry in entries:
        if entry["language"]["name"] == "en":
            return entry[key]
    return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\f", " ").replace("­", "")).strip()


# --------------------------------------------------------------------------- parsing

def pick_description(species: dict) -> str:
    entries = [e for e in species["flavor_text_entries"] if e["language"]["name"] == "en"]
    if not entries:
        return ""
    # Prefer the newest game's entry, which tends to be the best written.
    return clean_text(entries[-1]["flavor_text"])


def image_urls(sprites: dict) -> dict[str, str]:
    other = sprites.get("other") or {}
    versions = sprites.get("versions") or {}
    candidates = {
        "artwork": (other.get("official-artwork") or {}).get("front_default"),
        "artwork_shiny": (other.get("official-artwork") or {}).get("front_shiny"),
        "home": (other.get("home") or {}).get("front_default"),
        "home_shiny": (other.get("home") or {}).get("front_shiny"),
        "sprite": sprites.get("front_default"),
        "sprite_shiny": sprites.get("front_shiny"),
        "sprite_back": sprites.get("back_default"),
        "bw": ((versions.get("generation-v") or {}).get("black-white") or {}).get("front_default"),
        "platinum": ((versions.get("generation-iv") or {}).get("platinum") or {}).get("front_default"),
        "emerald": ((versions.get("generation-iii") or {}).get("emerald") or {}).get("front_default"),
        "crystal": ((versions.get("generation-ii") or {}).get("crystal") or {}).get("front_transparent"),
        "usum": ((versions.get("generation-vii") or {}).get("ultra-sun-ultra-moon") or {}).get("front_default"),
        "xy": ((versions.get("generation-vi") or {}).get("x-y") or {}).get("front_default"),
    }
    return {k: v for k, v in candidates.items() if v and v.endswith(".png")}


def parse_pokemon(species: dict, pokemon: dict) -> dict:
    stats = {s["stat"]["name"]: s["base_stat"] for s in pokemon["stats"]}
    moves = []
    for m in pokemon["moves"]:
        # Use the most recent game the move appears in for learn method/level.
        detail = max(m["version_group_details"], key=lambda d: id_from_url(d["version_group"]["url"]))
        moves.append({
            "move": m["move"]["name"],
            "method": detail["move_learn_method"]["name"],
            "level": detail["level_learned_at"],
        })
    return {
        "id": species["id"],
        "name": species["name"],
        "display_name": english(species["names"]) or species["name"].title(),
        "variety": pokemon["name"],
        "genus": english(species["genera"], "genus") or "",
        "generation": GENERATIONS[species["generation"]["name"]],
        "types": [t["type"]["name"] for t in sorted(pokemon["types"], key=lambda t: t["slot"])],
        "height": pokemon["height"] / 10,  # metres
        "weight": pokemon["weight"] / 10,  # kilograms
        "base_experience": pokemon.get("base_experience"),
        "abilities": [{"name": a["ability"]["name"], "hidden": a["is_hidden"]} for a in pokemon["abilities"]],
        "stats": {
            "hp": stats.get("hp"), "attack": stats.get("attack"), "defense": stats.get("defense"),
            "sp_attack": stats.get("special-attack"), "sp_defense": stats.get("special-defense"),
            "speed": stats.get("speed"),
        },
        "description": pick_description(species),
        "color": species["color"]["name"] if species.get("color") else None,
        "habitat": species["habitat"]["name"] if species.get("habitat") else None,
        "is_legendary": species["is_legendary"],
        "is_mythical": species["is_mythical"],
        "capture_rate": species["capture_rate"],
        "evolution_chain_id": id_from_url(species["evolution_chain"]["url"]) if species.get("evolution_chain") else None,
        "evolves_from": species["evolves_from_species"]["name"] if species.get("evolves_from_species") else None,
        "images": image_urls(pokemon["sprites"]),
        "moves": moves,
    }


def describe_condition(details: list) -> str:
    """Turn PokéAPI evolution_details into short human text like 'Level 36'."""
    if not details:
        return ""
    parts = []
    d = details[-1]
    trigger = d["trigger"]["name"]
    if d.get("min_level"):
        parts.append(f"Level {d['min_level']}")
    elif trigger == "level-up":
        parts.append("Level up")
    if trigger == "trade":
        parts.append("Trade")
    if trigger == "use-item" and d.get("item"):
        parts.append("Use " + d["item"]["name"].replace("-", " ").title())
    if d.get("held_item"):
        parts.append("holding " + d["held_item"]["name"].replace("-", " ").title())
    if d.get("trade_species"):
        parts.append("for " + d["trade_species"]["name"].title())
    if d.get("min_happiness"):
        parts.append("high friendship")
    if d.get("min_affection"):
        parts.append("high affection")
    if d.get("min_beauty"):
        parts.append("high beauty")
    if d.get("known_move"):
        parts.append("knowing " + d["known_move"]["name"].replace("-", " ").title())
    if d.get("known_move_type"):
        parts.append("knowing a " + d["known_move_type"]["name"].title() + "-type move")
    if d.get("location"):
        parts.append("at " + d["location"]["name"].replace("-", " ").title())
    if d.get("time_of_day"):
        parts.append(f"({d['time_of_day']})")
    if d.get("gender") is not None:
        parts.append("(female)" if d["gender"] == 1 else "(male)")
    if d.get("needs_overworld_rain"):
        parts.append("while raining")
    if d.get("turn_upside_down"):
        parts.append("with device upside down")
    if trigger not in ("level-up", "trade", "use-item") and not parts:
        parts.append(trigger.replace("-", " ").title())
    return " ".join(parts) or trigger.replace("-", " ").title()


def parse_chain(chain: dict) -> dict:
    def walk(node):
        return {
            "species": node["species"]["name"],
            "condition": describe_condition(node["evolution_details"]),
            "evolves_to": [walk(child) for child in node["evolves_to"]],
        }
    return {"id": chain["id"], "chain": walk(chain["chain"])}


def parse_move(move: dict) -> dict:
    effect = english(move.get("effect_entries") or [], "short_effect") or ""
    if move.get("effect_chance") is not None:
        effect = effect.replace("$effect_chance", str(move["effect_chance"]))
    return {
        "id": move["id"],
        "name": move["name"],
        "display_name": english(move["names"]) or move["name"].replace("-", " ").title(),
        "type": move["type"]["name"],
        "power": move["power"],
        "accuracy": move["accuracy"],
        "pp": move["pp"],
        "damage_class": move["damage_class"]["name"] if move.get("damage_class") else None,
        "effect": clean_text(effect),
        "generation": GENERATIONS.get(move["generation"]["name"]),
    }


def parse_encounters(pokemon_id: int, encounters: list, areas: dict, locations: dict) -> list:
    out = []
    for enc in encounters:
        area_name = enc["location_area"]["name"]
        area = areas.get(area_name) or {}
        location_name = area.get("location", {}).get("name") if area else None
        loc = locations.get(location_name) or {}
        versions = [v["version"]["name"] for v in enc["version_details"]]
        details = [d for v in enc["version_details"] for d in v["encounter_details"]]
        out.append({
            "pokemon_id": pokemon_id,
            "location_area": area_name,
            "location": location_name or area_name,
            "location_display": (english(loc.get("names") or []) if loc else None)
                                 or (location_name or area_name).replace("-", " ").title(),
            "region": (loc.get("region") or {}).get("name") if loc else None,
            "versions": versions,
            "methods": sorted({d["method"]["name"] for d in details}),
            "min_level": min((d["min_level"] for d in details), default=None),
            "max_level": max((d["max_level"] for d in details), default=None),
            "max_chance": max((v["max_chance"] for v in enc["version_details"]), default=None),
        })
    return out


# --------------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-id", type=int, default=1025, help="highest National Dex number (1025 = Gen 1-9)")
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    started = time.time()

    print("1/7 Species list")
    species_list = get_json("pokemon-species?limit=2000")
    by_name = {s["name"]: id_from_url(s["url"]) for s in species_list["results"]}
    ids = sorted({i for i in by_name.values() if i <= args.max_id} | {by_name[n] for n in REQUIRED})
    print(f"  {len(ids)} species selected")

    print("2/7 Species + Pokémon + encounters")
    species, _ = parallel(lambda i: get_json(f"pokemon-species/{i}"), ids, "species", args.workers)

    def default_variety(i):
        variety = next(v for v in species[i]["varieties"] if v["is_default"])
        return get_json(f"pokemon/{id_from_url(variety['pokemon']['url'])}")

    pokemon_raw, _ = parallel(default_variety, list(species), "pokemon", args.workers)
    encounters_raw, _ = parallel(lambda i: get_json(f"pokemon/{pokemon_raw[i]['id']}/encounters"),
                                 list(pokemon_raw), "encounters", args.workers)

    print("3/7 Evolution chains")
    chain_ids = sorted({id_from_url(s["evolution_chain"]["url"]) for s in species.values() if s.get("evolution_chain")})
    chains_raw, _ = parallel(lambda c: get_json(f"evolution-chain/{c}"), chain_ids, "chains", args.workers)

    print("4/7 Moves")
    move_names = sorted({m["move"]["name"] for p in pokemon_raw.values() for m in p["moves"]})
    moves_raw, _ = parallel(lambda n: get_json(f"move/{n}"), move_names, "moves", args.workers)

    print("5/7 Abilities + encounter locations")
    ability_names = sorted({a["ability"]["name"] for p in pokemon_raw.values() for a in p["abilities"]})
    abilities_raw, _ = parallel(lambda n: get_json(f"ability/{n}"), ability_names, "abilities", args.workers)
    area_names = sorted({e["location_area"]["name"] for encs in encounters_raw.values() for e in encs})
    areas, _ = parallel(lambda n: get_json(f"location-area/{n}"), area_names, "areas", args.workers)
    location_names = sorted({a["location"]["name"] for a in areas.values() if a.get("location")})
    locations, _ = parallel(lambda n: get_json(f"location/{n}"), location_names, "locations", args.workers)

    print("6/7 Processing")
    pokemon = sorted((parse_pokemon(species[i], pokemon_raw[i]) for i in pokemon_raw), key=lambda p: p["id"])
    chains = [parse_chain(chains_raw[c]) for c in sorted(chains_raw)]
    moves = sorted((parse_move(m) for m in moves_raw.values()), key=lambda m: m["id"])
    abilities = sorted(({
        "name": a["name"],
        "display_name": english(a["names"]) or a["name"].title(),
        "effect": clean_text(english(a.get("effect_entries") or [], "short_effect")
                             or english(a.get("flavor_text_entries") or [], "flavor_text") or ""),
    } for a in abilities_raw.values()), key=lambda a: a["name"])
    encounters = []
    for i in sorted(encounters_raw):
        encounters.extend(parse_encounters(i, encounters_raw[i], areas, locations))

    for name, payload in [("pokemon", pokemon), ("evolution_chains", chains), ("moves", moves),
                          ("abilities", abilities), ("encounters", encounters)]:
        (PROCESSED / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  wrote data/processed/{name}.json ({len(payload)} records)")

    missing = [n for n in REQUIRED if n not in {p["name"] for p in pokemon}]
    if missing:
        sys.exit(f"Required Pokémon missing: {missing}")

    if not args.skip_images:
        print("7/7 Images")
        jobs = [(url, IMAGES / p["name"] / f"{variant}.png") for p in pokemon for variant, url in p["images"].items()]
        results, _ = parallel(lambda job: download(*job), jobs, "images", args.workers)
        print(f"  {sum(results.values())}/{len(jobs)} images saved to data/images/")
    else:
        print("7/7 Images skipped")

    print(f"Done in {time.time() - started:.0f}s. Next: python scripts\\load_db.py")


if __name__ == "__main__":
    main()
