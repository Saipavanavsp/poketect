"""ORM tables: Pokémon, moves, evolutions, encounters, trainer, and map places."""
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Pokemon(Base):
    __tablename__ = "pokemon"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    genus: Mapped[str] = mapped_column(String(64), default="")
    generation: Mapped[int] = mapped_column(Integer, index=True)
    types: Mapped[list] = mapped_column(JSON)
    height: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    base_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abilities: Mapped[list] = mapped_column(JSON)
    stats: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    habitat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_legendary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mythical: Mapped[bool] = mapped_column(Boolean, default=False)
    capture_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evolution_chain_id: Mapped[int | None] = mapped_column(ForeignKey("evolution_chains.id"), nullable=True)
    evolves_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    images: Mapped[dict] = mapped_column(JSON)
    go: Mapped[list | None] = mapped_column(JSON, nullable=True)  # Pokémon GO forms, from pokemondb.net

    moves: Mapped[list["PokemonMove"]] = relationship(back_populates="pokemon", cascade="all, delete-orphan")


class Move(Base):
    __tablename__ = "moves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))
    power: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    damage_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effect: Mapped[str] = mapped_column(Text, default="")
    generation: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PokemonMove(Base):
    __tablename__ = "pokemon_moves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), index=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=0)

    pokemon: Mapped[Pokemon] = relationship(back_populates="moves")
    move: Mapped[Move] = relationship()


class Ability(Base):
    __tablename__ = "abilities"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64))
    effect: Mapped[str] = mapped_column(Text, default="")


class EvolutionChain(Base):
    __tablename__ = "evolution_chains"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[dict] = mapped_column(JSON)


class Encounter(Base):
    __tablename__ = "encounters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), index=True)
    location_area: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(128), index=True)
    location_display: Mapped[str] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    versions: Mapped[list] = mapped_column(JSON)
    methods: Mapped[list] = mapped_column(JSON)
    min_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_chance: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Place(Base):
    """A town, city, route marker or landmark on one of the custom region maps."""
    __tablename__ = "places"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))  # town | city | route | landmark
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")


class Gym(Base):
    __tablename__ = "gyms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    city: Mapped[str] = mapped_column(String(64))
    leader: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))
    badge: Mapped[str] = mapped_column(String(32))
    order: Mapped[int] = mapped_column(Integer)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)


class PokemonCenter(Base):
    __tablename__ = "pokemon_centers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)


class Trainer(Base):
    __tablename__ = "trainers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    height_ft: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    hometown: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32))
    bio: Mapped[str] = mapped_column(Text, default="")

    badges: Mapped[list["Badge"]] = relationship(back_populates="trainer", cascade="all, delete-orphan",
                                                 order_by="Badge.order")
    team: Mapped[list["TeamMember"]] = relationship(back_populates="trainer", cascade="all, delete-orphan",
                                                    order_by="TeamMember.slot")


class Badge(Base):
    __tablename__ = "badges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id"))
    name: Mapped[str] = mapped_column(String(32))
    region: Mapped[str] = mapped_column(String(32))
    gym_leader: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))
    order: Mapped[int] = mapped_column(Integer)
    earned: Mapped[bool] = mapped_column(Boolean, default=False)

    trainer: Mapped[Trainer] = relationship(back_populates="badges")


class TeamMember(Base):
    __tablename__ = "team_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trainer_id: Mapped[int] = mapped_column(ForeignKey("trainers.id"))
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"))
    slot: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer, default=50)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    top_moves: Mapped[list] = mapped_column(JSON, default=list)

    trainer: Mapped[Trainer] = relationship(back_populates="team")
    pokemon: Mapped[Pokemon] = relationship()
