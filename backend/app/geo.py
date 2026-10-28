"""Map helpers: expand seed data into rows, compute distances, and place encounters on the map."""
import math
import re

from .seed_data import KM_PER_UNIT, LOCATION_ALIASES, REGIONS


def route_midpoint(path):
    """Point halfway along a polyline, used as the route's marker position."""
    segments = list(zip(path, path[1:]))
    lengths = [math.dist(a, b) for a, b in segments]
    remaining = sum(lengths) / 2
    for (a, b), length in zip(segments, lengths):
        if remaining <= length:
            t = remaining / length if length else 0
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        remaining -= length
    return path[-1]


def build_places():
    rows = []
    for region, spec in REGIONS.items():
        for slug, name, kind, x, y in spec["places"]:
            rows.append({"slug": slug, "region": region, "name": name, "kind": kind, "x": x, "y": y})
        for number, path in spec["routes"]:
            if number is None:
                continue
            x, y = route_midpoint(path)
            rows.append({"slug": f"route-{number}", "region": region, "name": f"Route {number}",
                         "kind": "route", "x": round(x, 1), "y": round(y, 1)})
    return rows


def _place_lookup(region):
    return {slug: (name, x, y) for slug, name, _, x, y in REGIONS[region]["places"]}


def build_gyms():
    rows = []
    for region, spec in REGIONS.items():
        places = _place_lookup(region)
        for order, (city_slug, leader, type_, badge) in enumerate(spec["gyms"], 1):
            city, x, y = places[city_slug]
            rows.append({"region": region, "city": city, "leader": leader, "type": type_, "badge": badge,
                         "order": order, "x": x + 14, "y": y - 12})
    return rows


def build_centers():
    rows = []
    for region, spec in REGIONS.items():
        places = _place_lookup(region)
        for entry in spec["centers"]:
            if isinstance(entry, tuple):
                name, city, x, y = entry
            else:
                city, x, y = places[entry]
                name = f"{city} Pokémon Center"
                x, y = x - 14, y - 12
            rows.append({"region": region, "name": name, "city": city, "x": x, "y": y})
    return rows


def distance_km(x1, y1, x2, y2):
    return round(math.dist((x1, y1), (x2, y2)) * KM_PER_UNIT, 2)


def nearest(items, x, y, limit=3):
    """Sort dict-like rows with x/y by distance from (x, y)."""
    ranked = sorted(({**item, "distance_km": distance_km(x, y, item["x"], item["y"])} for item in items),
                    key=lambda r: r["distance_km"])
    return ranked[:limit]


_ROUTE = re.compile(r"(?:sea-)?route-(\d+)")


def map_location(region, location):
    """Return the place slug on our map for a PokéAPI location name, or None."""
    if region not in REGIONS or not location:
        return None
    name = location.removeprefix(f"{region}-")
    match = _ROUTE.match(name)
    if match:
        slug = f"route-{match.group(1)}"
        numbers = {n for n, _ in REGIONS[region]["routes"] if n is not None}
        return slug if int(match.group(1)) in numbers else None
    slugs = sorted(_place_lookup(region), key=len, reverse=True)
    for slug in slugs:
        if name == slug or name.startswith(slug + "-") or name.startswith(slug):
            return slug
    for alias, target in LOCATION_ALIASES.items():
        if name.startswith(alias) and target in _place_lookup(region):
            return target
    return None


def region_geometry():
    """Land shapes and route polylines for drawing the schematic maps."""
    return {
        region: {
            "label": spec["label"],
            "land": spec["land"],
            "islands": spec["islands"],
            "routes": [{"number": n, "path": path} for n, path in spec["routes"]],
        }
        for region, spec in REGIONS.items()
    }
