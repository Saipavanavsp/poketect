"""Scrape Pokémon GO data and extra image styles from Pokémon Database (https://pokemondb.net/go/pokedex).

    .\\.venv\\Scripts\\python.exe scripts\\fetch_pokemondb.py                 # data + images
    .\\.venv\\Scripts\\python.exe scripts\\fetch_pokemondb.py --skip-images

Run after scripts/fetch_data.py (labels come from data/processed/pokemon.json, matched by National Dex number).

Outputs
  data/processed/go_pokedex.json     one record per GO form: stats, catch/flee rate, fast and charge moves
  data/images/<pokemon>/pdb_*.png    GO, HOME, Scarlet/Violet, BDSP, Sword/Shield sprites and large artwork,
                                     picked up by scripts/prepare_dataset.py as extra training styles.
                                     Alternate forms (Alolan, Mega, costumes ...) are saved as pdbform_<form>_*
                                     and labelled with their species.

Polite crawling: the page itself is fetched once and cached (robots.txt asks for a 2 s crawl delay), images are
rate-limited and cached, and 404s are remembered in data/raw/pokemondb/missing.txt so re-runs never repeat them.
"""
import argparse
import html
import json
import re
import sys
import threading
from pathlib import Path

from fetch_data import RateLimiter, make_session, parallel

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "pokemondb"
PROCESSED = ROOT / "data" / "processed"
IMAGES = ROOT / "data" / "images"
PAGE = "https://pokemondb.net/go/pokedex"
IMG = "https://img.pokemondb.net"

# style -> URL template; {slug} is the pokemondb image name, e.g. "bulbasaur" or "rattata-alolan".
STYLES = {
    "go": "/sprites/go/normal/{slug}.png",
    "go_shiny": "/sprites/go/shiny/{slug}.png",
    "home": "/sprites/home/normal/{slug}.png",
    "home_shiny": "/sprites/home/shiny/{slug}.png",
    "sv": "/sprites/scarlet-violet/normal/{slug}.png",
    "swsh": "/sprites/sword-shield/normal/{slug}.png",
    "bdsp": "/sprites/brilliant-diamond-shining-pearl/normal/{slug}.png",
    "artwork": "/artwork/large/{slug}.jpg",
    "icon": "/sprites/scarlet-violet/icon/{slug}.png",
}
FORM_STYLES = ["go", "go_shiny", "home", "artwork"]  # fewer per alternate form: it shares most features

SESSION = make_session()
LIMITER = RateLimiter(per_second=4)
MISSING_LOCK = threading.Lock()


def text(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def lines(cell: str) -> list[str]:
    """'<td>Tackle<br>Vine Whip<br></td>' -> ['Tackle', 'Vine Whip']."""
    return [t for t in (text(part) for part in re.split(r"<br\s*/?>", cell)) if t]


def percent(cell: str) -> int | None:
    m = re.search(r"(\d+)%", cell)
    return int(m.group(1)) if m else None


def parse_moves(cell: str) -> list[dict]:
    """Moves in grey text are special: 'Frenzy Plant (Community Day)', 'Return (Purified)'."""
    out = []
    for part in re.split(r"<br\s*/?>", cell):
        name = text(part)
        if not name:
            continue
        m = re.match(r"(.+?)\s*\(([^)]+)\)$", name)
        out.append({"name": m.group(1) if m else name, "special": m.group(2) if m else None})
    return out


def parse_go_page(page: str) -> list[dict]:
    body = page[page.index('<table id="pokedex"'):]
    body = body[body.index("<tbody>"):body.index("</tbody>")]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) != 10:
            continue
        icon = re.search(r'<img[^>]+src="([^"]+)"', cells[0])
        icon_url = icon.group(1) if icon else ""
        form = re.search(r"<small[^>]*>(.*?)</small>", cells[1], re.S)
        rows.append({
            "id": int(re.search(r'data-sort-value="(\d+)"', tr).group(1)),
            "name": text(re.search(r'<a class="ent-name"[^>]*>(.*?)</a>', cells[1], re.S).group(1)),
            "form": text(form.group(1)) if form else None,
            "slug": Path(icon_url).stem if icon_url.endswith(".png") and "/icon/" in icon_url else None,
            "types": [t.lower() for t in re.findall(r'class="type-icon[^"]*"[^>]*>([^<]+)</a>', cells[2])],
            "attack": int(text(cells[3])), "defense": int(text(cells[4])), "stamina": int(text(cells[5])),
            "catch_rate": percent(cells[6]), "flee_rate": percent(cells[7]),
            "fast_moves": parse_moves(cells[8]), "charge_moves": parse_moves(cells[9]),
        })
    return rows


def load_missing() -> set[str]:
    path = RAW / "missing.txt"
    return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()


def download(url: str, dest: Path, missing: set[str]) -> str:
    if url in missing:
        return "missing"
    if dest.exists() and dest.stat().st_size > 0:
        return "cached"
    LIMITER.wait()
    resp = SESSION.get(url, timeout=30)
    if resp.status_code == 404:
        with MISSING_LOCK:
            missing.add(url)
            with open(RAW / "missing.txt", "a", encoding="utf-8") as f:
                f.write(url + "\n")
        return "missing"
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return "new"


def image_jobs(go_rows: list[dict], species: dict[int, str]) -> list[tuple[str, Path]]:
    """Base form of every species (also those not in GO, by PokéAPI name) plus GO's alternate forms."""
    jobs, base_slug = [], {}
    for row in go_rows:
        if row["id"] in species and row["slug"] and not row["form"]:
            base_slug.setdefault(row["id"], row["slug"])
    for dex, label in species.items():
        slug = base_slug.get(dex, label)
        jobs += [(IMG + tpl.format(slug=slug), IMAGES / label / f"pdb_{style}{Path(tpl).suffix}")
                 for style, tpl in STYLES.items()]
    for row in go_rows:
        if row["id"] in species and row["slug"] and row["form"]:
            label = species[row["id"]]
            jobs += [(IMG + STYLES[s].format(slug=row["slug"]),
                      IMAGES / label / f"pdbform_{row['slug']}_{s}{Path(STYLES[s]).suffix}") for s in FORM_STYLES]
    return list(dict.fromkeys(jobs))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    cache = RAW / "go_pokedex.html"
    if not cache.exists():
        resp = SESSION.get(PAGE, timeout=30)
        resp.raise_for_status()
        cache.write_text(resp.text, encoding="utf-8")
    go_rows = parse_go_page(cache.read_text(encoding="utf-8"))

    species = {p["id"]: p["name"] for p in json.loads((PROCESSED / "pokemon.json").read_text(encoding="utf-8"))}
    for row in go_rows:
        row["species"] = species.get(row["id"])
    (PROCESSED / "go_pokedex.json").write_text(json.dumps(go_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote data/processed/go_pokedex.json: {len(go_rows)} GO entries, "
          f"{len({r['id'] for r in go_rows})} species, {sum(bool(r['form']) for r in go_rows)} alternate forms")

    if args.skip_images:
        return
    missing = load_missing()
    jobs = image_jobs(go_rows, species)
    results, errors = parallel(lambda job: download(*job, missing), jobs, "images", args.workers)
    counts = {k: list(results.values()).count(k) for k in ("new", "cached", "missing")}
    print(f"images: {counts}, errors: {len(errors)}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
