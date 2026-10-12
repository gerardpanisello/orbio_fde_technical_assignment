"""Persona definitions for the conversation eval, loaded from `personas.yaml`."""

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sazon_screening.vocab import Country, DisqualificationReason, Language, Status

PERSONAS_FILE = Path(__file__).with_name("personas.yaml")

ScoredField = Literal[
    "full_name",
    "age",
    "vehicle_type",
    "has_license",
    "location",
    "availability",
    "schedule",
    "experience",
    "start_date",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TruthLocation(_Strict):
    city: str | None = None
    zone: str | None = None
    out_of_area: bool = False


class TruthExperience(_Strict):
    years: int
    platforms: list[str]


class Truth(_Strict):
    """Ground-truth values, in the record's vocabulary (config ids, enum values)."""

    full_name: str | None = None
    age: int | None = None
    vehicle_type: str | None = None
    has_license: bool | None = None
    location: TruthLocation | None = None
    availability: list[str] | None = None
    schedule: list[str] | None = None
    experience: TruthExperience | None = None
    start_date: tuple[date, date] | None = None


class Expect(_Strict):
    status: Status
    reason: DisqualificationReason | None = None
    fields: list[ScoredField] = Field(default_factory=list)


class Forced(_Strict):
    """A fixed candidate message at a given candidate turn (1-based), bypassing the simulator.

    For the beats an eval must not leave to chance: an injection, an opt-out, a language
    switch. The model plays everything else.
    """

    turn: int = Field(ge=1)
    text: str


class Persona(_Strict):
    id: str
    title: str
    language: Language = Language.es
    country_hint: Country | None = None
    facts: str
    style: str
    script: str = ""
    forced: list[Forced] = Field(default_factory=list)
    truth: Truth
    expect: Expect


class PersonaFile(_Strict):
    personas: list[Persona]


def load_personas(path: Path = PERSONAS_FILE) -> list[Persona]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    personas = PersonaFile.model_validate(data).personas
    ids = [p.id for p in personas]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name}: duplicate persona ids")
    for persona in personas:
        missing = [f for f in persona.expect.fields if getattr(persona.truth, f) is None]
        if missing:
            raise ValueError(f"{path.name}: {persona.id} scores {missing} without a truth value")
        turns = [f.turn for f in persona.forced]
        if len(turns) != len(set(turns)):
            raise ValueError(f"{path.name}: {persona.id} forces the same turn twice")
    return personas


def select(personas: list[Persona], spec: str) -> list[Persona]:
    """`all`, or a comma-separated list of persona ids."""
    if spec == "all":
        return personas
    wanted = [s.strip() for s in spec.split(",") if s.strip()]
    known = {p.id: p for p in personas}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise SystemExit(f"unknown persona(s): {', '.join(unknown)}; known: {', '.join(known)}")
    return [known[w] for w in wanted]
