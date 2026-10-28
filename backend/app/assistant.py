"""Live Pokédex assistant: Claude with tool calling over our own database, streamed as SSE."""
import json

from sqlalchemy.orm import Session

from . import geo, services
from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL

SYSTEM_PROMPT = """You are Dexter, a friendly talking Pokédex. Replies are spoken aloud, so keep them short \
(1-3 sentences), conversational, and free of markdown, lists, or emoji.
Answer facts about Pokémon, moves, evolutions, gyms, Pokémon Centers, and the trainer only from tool results - \
call a tool before answering any such question. If a tool returns nothing, say you don't have that entry.
Pokémon Centers are what the trainer means by "hospital". Distances are approximate map distances in km.
The trainer's current location and any last identified image are provided by the tools."""

_POKEMON_ARG = {"type": "object", "properties": {"name": {"type": "string", "description": "Pokémon name or Pokédex number"}},
                "required": ["name"], "additionalProperties": False}
_LOCATION_ARG = {"type": "object", "properties": {
    "region": {"type": "string", "description": "kanto, johto, hoenn or sinnoh; omit to use the trainer's current location"},
    "place": {"type": "string", "description": "town or city to measure from; omit to use the current location"}},
    "additionalProperties": False}

TOOLS = [
    {"name": "get_pokemon_info", "description": "Pokédex entry: types, stats, height, weight, abilities, description.",
     "input_schema": _POKEMON_ARG},
    {"name": "get_attacks", "description": "Moves a Pokémon can learn, strongest level-up moves first, with type, power, accuracy, PP.",
     "input_schema": _POKEMON_ARG},
    {"name": "get_evolutions", "description": "Full evolution chain and what the Pokémon evolves from / into, with conditions.",
     "input_schema": _POKEMON_ARG},
    {"name": "find_nearest_gym", "description": "Nearest gyms to the trainer (leader, type, badge, distance).",
     "input_schema": _LOCATION_ARG},
    {"name": "find_nearest_pokemon_center", "description": "Nearest Pokémon Centers (hospitals) to the trainer.",
     "input_schema": _LOCATION_ARG},
    {"name": "get_trainer_profile", "description": "The trainer's profile, badges and Pokémon team.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "identify_last_uploaded_image", "description": "Result of the image the trainer most recently scanned.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]
for _tool in TOOLS:
    _tool["eager_input_streaming"] = True

DEFAULT_LOCATION = {"region": "kanto", "x": 230, "y": 580, "label": "Pallet Town"}


def _origin(db: Session, args: dict, context: dict) -> dict:
    loc = {**DEFAULT_LOCATION, **(context.get("location") or {})}
    region = (args.get("region") or loc["region"]).lower()
    if args.get("place"):
        place = services.place_by_name(db, region, args["place"])
        if place:
            return {"region": region, "x": place["x"], "y": place["y"], "label": place["name"]}
    if region != loc["region"]:
        # No position in that region yet: measure from its first town.
        first = services.places(db, region)[:1]
        if first:
            return {"region": region, "x": first[0]["x"], "y": first[0]["y"], "label": first[0]["name"]}
    return {**loc, "region": region}


def run_tool(db: Session, name: str, args: dict, context: dict):
    if name in ("get_pokemon_info", "get_attacks", "get_evolutions"):
        p = services.find_pokemon(db, str(args.get("name", "")))
        if not p:
            return {"error": f"No Pokédex entry for '{args.get('name')}'."}
        if name == "get_pokemon_info":
            d = services.detail(db, p)
            return {k: d[k] for k in ("id", "display_name", "genus", "types", "height", "weight", "stats",
                                      "description", "generation", "evolves_from")} | {
                "abilities": [a["display_name"] for a in d["abilities"]]}
        if name == "get_attacks":
            moves = services.moves_for(db, p)
            level_up = sorted((m for m in moves if m["method"] == "level-up" and m["power"]),
                              key=lambda m: -(m["power"] or 0))
            return {"pokemon": p.display_name, "total_moves": len(moves),
                    "top_level_up_moves": [{k: m[k] for k in ("display_name", "type", "power", "accuracy", "pp", "level")}
                                           for m in level_up[:8]]}
        chain = services.evolution_for(db, p)
        return {"pokemon": p.display_name, "evolves_from": p.evolves_from, "chain": chain,
                "has_evolutions": bool(chain and chain["evolves_to"])}
    if name in ("find_nearest_gym", "find_nearest_pokemon_center"):
        origin = _origin(db, args, context)
        items = services.gyms(db, origin["region"]) if name == "find_nearest_gym" else services.centers(db, origin["region"])
        return {"from": origin["label"], "region": origin["region"], "nearest": geo.nearest(items, origin["x"], origin["y"])}
    if name == "get_trainer_profile":
        profile = services.trainer_profile(db)
        if not profile:
            return {"error": "No trainer profile saved."}
        profile["badges_earned"] = [b["name"] for b in profile.pop("badges") if b["earned"]]
        profile["team"] = [{"pokemon": m["pokemon"]["display_name"], "types": m["pokemon"]["types"], "level": m["level"],
                            "top_moves": [mv["display_name"] for mv in m["top_moves"]]} for m in profile["team"]]
        return profile
    if name == "identify_last_uploaded_image":
        last = context.get("last_identification")
        return last or {"error": "No image has been scanned yet in this session."}
    return {"error": f"Unknown tool {name}"}


def _valid(args) -> bool:
    return isinstance(args, dict) and all(isinstance(v, str) for v in args.values())


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_chat(db: Session, history: list[dict], context: dict):
    """Generator of SSE strings: 'text' deltas, 'tool' notices, then 'done' (or 'error')."""
    if not ANTHROPIC_API_KEY:
        yield sse("error", {"message": "ANTHROPIC_API_KEY is not set on the server."})
        return
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-20:]
                if m.get("role") in ("user", "assistant") and m.get("content")]
    try:
        for _ in range(6):  # bound the tool loop
            with client.beta.messages.stream(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        yield sse("text", {"delta": event.text})
                response = stream.get_final_message()

            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "refusal" or not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                yield sse("error", {"message": "Reply was cut off."})
                break
            results = []
            for block in tool_uses:
                yield sse("tool", {"name": block.name, "input": block.input})
                if not _valid(block.input):
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": json.dumps({"INVALID_JSON": json.dumps(block.input)})})
                    continue
                result = run_tool(db, block.name, block.input, context)
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(result, default=str)[:12000]})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})
    except ValueError:
        yield sse("error", {"message": "Could not read a tool call - please ask again."})
    except anthropic.AuthenticationError:
        yield sse("error", {"message": "The Claude API key was rejected."})
    except anthropic.RateLimitError:
        yield sse("error", {"message": "Claude is rate-limited right now - try again in a moment."})
    except anthropic.APIStatusError as exc:
        yield sse("error", {"message": f"Claude API error {exc.status_code}."})
    except anthropic.APIConnectionError:
        yield sse("error", {"message": "Could not reach the Claude API."})
    yield sse("done", {})
