"""API tests: Pokémon data, evolutions, trainer edits, map distances, chat tools."""
from app import assistant
from app.database import SessionLocal


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["pokemon"] > 0


def test_list_and_filter(client):
    fire = client.get("/api/pokemon", params={"type": "fire"}).json()
    assert {"charmander", "charizard", "infernape"} <= {p["name"] for p in fire}
    gen1 = client.get("/api/pokemon", params={"generation": 1}).json()
    assert all(p["generation"] == 1 for p in gen1)


def test_detail_has_everything(client):
    p = client.get("/api/pokemon/charizard").json()
    assert p["types"] == ["fire", "flying"]
    assert set(p["stats"]) == {"hp", "attack", "defense", "sp_attack", "sp_defense", "speed"}
    assert p["description"]
    flamethrower = next(m for m in p["moves"] if m["name"] == "flamethrower")
    assert flamethrower["power"] == 90 and flamethrower["pp"] == 15 and flamethrower["type"] == "fire"


def test_name_normalisation(client):
    for key in ["Sirfetch’d", "sirfetch'd", "SIRFETCHD", "865"]:
        assert client.get(f"/api/pokemon/{key}").json()["name"] == "sirfetchd"
    assert client.get("/api/pokemon/missingno").status_code == 404


def test_evolutions(client):
    sceptile = client.get("/api/pokemon/sceptile").json()
    assert sceptile["evolves_from"] == "grovyle"
    chain = sceptile["evolution"]
    assert chain["name"] == "treecko" and chain["evolves_to"][0]["evolves_to"][0]["name"] == "sceptile"
    tauros = client.get("/api/pokemon/tauros").json()
    assert tauros["evolution"]["evolves_to"] == []  # "no evolution" case


def test_trainer_and_edits(client):
    t = client.get("/api/trainer").json()
    assert t["name"] == "Ash Ketchum" and t["height_ft"] == 6.2 and t["weight_kg"] == 79
    assert [m["pokemon"]["name"] for m in t["team"]] == [
        "charizard", "infernape", "sceptile", "goodra", "snorlax", "lycanroc", "sirfetchd"]
    kanto = [b for b in t["badges"] if b["region"] == "kanto"]
    assert len(kanto) == 8 and all(b["earned"] for b in kanto)

    badge = kanto[0]
    after = client.put(f"/api/trainer/badges/{badge['id']}", json={"earned": False}).json()
    assert not next(b for b in after["badges"] if b["id"] == badge["id"])["earned"]

    member = t["team"][0]
    updated = client.put(f"/api/trainer/team/{member['id']}", json={"level": 80}).json()
    assert updated["team"][0]["level"] == 80
    bad = client.put(f"/api/trainer/team/{member['id']}", json={"top_moves": ["surf-board"]})
    assert bad.status_code == 400
    assert client.put("/api/trainer", json={"weight_kg": -1}).status_code == 422


def test_map_nearest(client):
    regions = client.get("/api/map/regions").json()
    assert set(regions) == {"kanto", "johto", "hoenn", "sinnoh"}
    assert len(regions["kanto"]["gyms"]) == 8
    # Standing in Pewter City, Brock's gym and Pewter's Pokémon Center are closest.
    near = client.get("/api/map/nearest", params={"region": "kanto", "x": 230, "y": 200}).json()
    assert near["gyms"][0]["leader"] == "Brock"
    assert near["centers"][0]["city"] == "Pewter City"
    assert near["gyms"][0]["distance_km"] < near["gyms"][1]["distance_km"]


def test_encounters_on_map(client):
    pikachu = client.get("/api/pokemon/pikachu").json()
    assert "viridian-forest" in {e["map_place"] for e in pikachu["encounters"]}
    found = client.get("/api/map/kanto/places/viridian-forest/pokemon").json()
    assert "pikachu" in {p["name"] for p in found}


def test_chat_tools_answer_from_database():
    db = SessionLocal()
    ctx = {"location": {"region": "kanto", "x": 580, "y": 160, "label": "Cerulean City"}}
    assert assistant.run_tool(db, "find_nearest_gym", {}, ctx)["nearest"][0]["leader"] == "Misty"
    assert "Cerulean" in assistant.run_tool(db, "find_nearest_pokemon_center", {}, ctx)["nearest"][0]["city"]
    attacks = assistant.run_tool(db, "get_attacks", {"name": "Charizard"}, ctx)
    assert attacks["top_level_up_moves"]
    assert assistant.run_tool(db, "get_evolutions", {"name": "Sceptile"}, ctx)["evolves_from"] == "grovyle"
    team = assistant.run_tool(db, "get_trainer_profile", {}, ctx)["team"]
    assert len(team) == 7
    assert "error" in assistant.run_tool(db, "identify_last_uploaded_image", {}, {})
    assert "error" in assistant.run_tool(db, "get_pokemon_info", {"name": "notapokemon"}, ctx)
    db.close()


def test_chat_without_key_reports_error(client):
    res = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert res.status_code == 200 and "ANTHROPIC_API_KEY" in res.text
