"""FastAPI entry point: REST API for Pokémon data, trainer, map, image identification and chat."""
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import assistant, geo, identifier, models, services
from .config import CORS_ORIGINS, UPLOAD_DIR
from .database import Base, engine, get_db
from .seed_data import REGIONS

Base.metadata.create_all(engine)

app = FastAPI(title="Poketect API", version="1.0.0",
              description="Fan project, not for commercial use. Data from PokéAPI (https://pokeapi.co).")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "pokemon": db.query(models.Pokemon).count(),
            "model_ready": identifier.MODEL_PATH.exists()}


# ----------------------------------------------------------------------------- Pokémon

@app.get("/api/pokemon")
def list_pokemon(q: str | None = None, type: str | None = None, generation: int | None = None,
                 limit: int = 2000, offset: int = 0, db: Session = Depends(get_db)):
    return services.list_pokemon(db, q, type, generation, limit, offset)


@app.get("/api/pokemon/{key}")
def get_pokemon(key: str, db: Session = Depends(get_db)):
    p = services.find_pokemon(db, key)
    if not p:
        raise HTTPException(404, f"No Pokémon called '{key}'")
    return services.detail(db, p)


@app.get("/api/types")
def list_types(db: Session = Depends(get_db)):
    return sorted({t for types in db.scalars(select(models.Pokemon.types)) for t in types})


# ----------------------------------------------------------------------------- Identify

@app.post("/api/identify")
async def identify(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image is larger than 8 MB")
    try:
        result = identifier.identify(data)
    except identifier.ModelNotReady as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / "last_upload.bin").write_bytes(data)
    for pred in result["predictions"]:
        p = services.find_pokemon(db, pred["name"])
        pred.update(services.summary(p) if p else {})
    return result


# ----------------------------------------------------------------------------- Trainer

class TrainerUpdate(BaseModel):
    name: str | None = Field(None, max_length=64)
    height_ft: float | None = Field(None, gt=0, lt=20)
    weight_kg: float | None = Field(None, gt=0, lt=500)
    hometown: str | None = Field(None, max_length=64)
    region: str | None = Field(None, max_length=32)
    bio: str | None = Field(None, max_length=1000)


class BadgeUpdate(BaseModel):
    earned: bool


class TeamMemberUpdate(BaseModel):
    level: int | None = Field(None, ge=1, le=100)
    nickname: str | None = Field(None, max_length=64)
    pokemon: str | None = None
    top_moves: list[str] | None = Field(None, max_length=4)


def _trainer(db: Session, trainer_id: int = 1) -> models.Trainer:
    t = db.get(models.Trainer, trainer_id)
    if not t:
        raise HTTPException(404, "Trainer not found - run scripts/load_db.py")
    return t


@app.get("/api/trainer")
def get_trainer(db: Session = Depends(get_db)):
    _trainer(db)
    return services.trainer_profile(db)


@app.put("/api/trainer")
def update_trainer(body: TrainerUpdate, db: Session = Depends(get_db)):
    t = _trainer(db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    db.commit()
    return services.trainer_profile(db)


@app.put("/api/trainer/badges/{badge_id}")
def update_badge(badge_id: int, body: BadgeUpdate, db: Session = Depends(get_db)):
    badge = db.get(models.Badge, badge_id)
    if not badge:
        raise HTTPException(404, "Badge not found")
    badge.earned = body.earned
    db.commit()
    return services.trainer_profile(db)


@app.put("/api/trainer/team/{member_id}")
def update_team_member(member_id: int, body: TeamMemberUpdate, db: Session = Depends(get_db)):
    member = db.get(models.TeamMember, member_id)
    if not member:
        raise HTTPException(404, "Team member not found")
    if body.pokemon:
        p = services.find_pokemon(db, body.pokemon)
        if not p:
            raise HTTPException(404, f"No Pokémon called '{body.pokemon}'")
        member.pokemon_id = p.id
        db.flush()
        db.refresh(member)
        if body.top_moves is None:
            member.top_moves = services.pick_top_moves(member.pokemon, [])
    if body.level is not None:
        member.level = body.level
    if body.nickname is not None:
        member.nickname = body.nickname or None
    if body.top_moves is not None:
        learnable = {m["name"] for m in services.moves_for(db, member.pokemon)}
        bad = [m for m in body.top_moves if m not in learnable]
        if bad:
            raise HTTPException(400, f"{member.pokemon.display_name} cannot learn: {', '.join(bad)}")
        member.top_moves = body.top_moves
    db.commit()
    return services.trainer_profile(db)


# ----------------------------------------------------------------------------- Map

@app.get("/api/map/regions")
def map_regions(db: Session = Depends(get_db)):
    geometry = geo.region_geometry()
    return {region: {**geometry[region], "places": services.places(db, region), "gyms": services.gyms(db, region),
                     "centers": services.centers(db, region)} for region in REGIONS}


@app.get("/api/map/nearest")
def map_nearest(region: str, x: float, y: float, limit: int = 3, db: Session = Depends(get_db)):
    if region not in REGIONS:
        raise HTTPException(404, f"Unknown region '{region}'")
    return {"gyms": geo.nearest(services.gyms(db, region), x, y, limit),
            "centers": geo.nearest(services.centers(db, region), x, y, limit)}


@app.get("/api/map/{region}/places/{slug}/pokemon")
def map_place_pokemon(region: str, slug: str, db: Session = Depends(get_db)):
    return services.pokemon_at_place(db, region, slug)


# ----------------------------------------------------------------------------- Chat

class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., max_length=60)
    context: dict = Field(default_factory=dict)


@app.post("/api/chat")
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    return StreamingResponse(assistant.stream_chat(db, body.messages, body.context), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
