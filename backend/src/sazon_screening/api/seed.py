"""Demo data (FR-12): simulated candidates talking to the real agent, so the dashboard has
something to show.

Nothing is inserted directly. Each persona is a scripted candidate whose messages go
through the same service, pipeline and engine as a real chat (in fake rules mode the
"LLM" is the keyword extractor and the templates), so stored transcripts, records,
traces and summaries are genuine. Same seed, same conversations; start times are
spread over the 14 days before `now`.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sazon_screening.api.service import ScreeningService, TurnOutcome
from sazon_screening.engine import SilenceExpired
from sazon_screening.vocab import Country, Language

Script = Callable[[random.Random], list[str]]

ES_NAMES = [
    "Lucía Martín",
    "Pablo Ruiz",
    "Marta Gil",
    "Javier Torres",
    "Elena Navarro",
    "Sergio Romero",
    "Carmen Ortiz",
    "Daniel Molina",
    "Laura Castro",
    "Adrián Ramos",
]
MX_NAMES = [
    "Ana López",
    "Luis Pérez",
    "Karla Ríos",
    "Diego Hernández",
    "Fernanda Cruz",
    "Jorge Flores",
    "Mariana Reyes",
    "Ricardo Morales",
]
EN_NAMES = ["John Smith", "Emma Wilson", "Liam Brown", "Olivia Taylor"]
ES_PLACES = [
    "Chamberí, Madrid",
    "Eixample, Barcelona",
    "Ruzafa, Valencia",
    "Triana, Sevilla",
    "Teatinos, Málaga",
]
MX_PLACES = ["Coyoacán, CDMX", "Providencia, Guadalajara", "San Pedro, Monterrey"]
EXPERIENCE = [
    "3 años en Glovo",
    "ninguna",
    "1 año en Uber Eats y Glovo",
    "5 años en Just Eat",
    "2 años de experiencia en Rappi",
]
START = ["el lunes", "en 2 semanas", "ya", "en 3 días", "en 1 semana"]


def _screening(rng: random.Random, *, mexico: bool = False) -> list[str]:
    """A Spanish-speaking candidate who answers everything, up to the recap confirmation."""
    return [
        rng.choice(["sí", "sí, acepto", "vale"]),
        f"Me llamo {rng.choice(MX_NAMES if mexico else ES_NAMES)}",
        f"tengo {rng.randint(19, 48)}",
        rng.choice(["moto", "carro" if mexico else "coche"]),
        "sí",
        rng.choice(MX_PLACES if mexico else ES_PLACES),
        rng.choice(
            ["medio tiempo" if mexico else "media jornada", "tiempo completo", "fines de semana"]
        ),
        rng.choice(["mañanas", "tardes", "noches", "flexible"]),
        rng.choice(EXPERIENCE),
        rng.choice(START),
        "sí",  # the recap is right
    ]


def _english(rng: random.Random) -> list[str]:
    return [
        "Yes, I agree",
        f"My name is {rng.choice(EN_NAMES)}",
        f"I'm {rng.randint(20, 40)} years old",
        "motorbike",
        "yes",
        rng.choice(["I live in Eixample, Barcelona", "I live in Chamberí, Madrid"]),
        rng.choice(["full time", "part time"]),
        rng.choice(["mornings", "evenings", "flexible"]),
        "4 years with Uber Eats",
        "in 1 week",
        "yes",
        str(rng.randint(1, 6)),
    ]


def _first(count: int, mexico: bool = False) -> Script:
    return lambda rng: _screening(rng, mexico=mexico)[:count]


@dataclass(frozen=True)
class Persona:
    key: str
    weight: int
    script: Script
    language: Language = Language.es
    country_hint: Country | None = None
    silent_at_end: bool = False  # goes quiet after the script: silence_expired


PERSONAS = [
    Persona("booked_es", 6, lambda r: [*_screening(r), str(r.randint(1, 6))]),
    Persona(
        "booked_mx", 4, lambda r: [*_screening(r, mexico=True), "el 1"], country_hint=Country.MX
    ),
    Persona("booked_en", 2, _english, language=Language.en),
    Persona("unscheduled", 2, lambda r: [*_screening(r), "ninguna me va bien"]),
    Persona("unscheduled_silent", 1, _first(11), silent_at_end=True),
    Persona("under_age", 2, lambda r: [*_screening(r)[:2], f"tengo {r.choice([16, 17])}"]),
    Persona("no_license", 2, lambda r: [*_screening(r)[:4], "no"]),
    Persona("out_of_area_es", 1, lambda r: [*_screening(r)[:5], "vivo en Zaragoza"]),
    Persona(
        "out_of_area_mx",
        1,
        lambda r: [*_screening(r, mexico=True)[:5], "vivo en Querétaro"],
        country_hint=Country.MX,
    ),
    Persona("abandoned_at_consent", 2, lambda r: [], silent_at_end=True),
    Persona("abandoned_at_vehicle", 1, _first(3), silent_at_end=True),
    Persona("abandoned_at_availability", 2, _first(6), silent_at_end=True),
    Persona(
        "abandoned_at_start_date",
        1,
        _first(9, mexico=True),
        country_hint=Country.MX,
        silent_at_end=True,
    ),
    Persona("needs_review", 2, lambda r: [*_screening(r)[:3], "quiero hablar con una persona"]),
    Persona("opted_out", 2, lambda r: [*_screening(r)[:3], "no me interesa, dame de baja"]),
]


async def seed(service: ScreeningService, n: int, *, seed: int, now: datetime) -> list[str]:
    """Create `n` conversations; every persona appears once before any repeats."""
    rng = random.Random(seed)
    weights = [p.weight for p in PERSONAS]
    chosen = PERSONAS[:n] + rng.choices(PERSONAS, weights=weights, k=max(0, n - len(PERSONAS)))
    return [await _play(service, persona, rng, now) for persona in chosen]


async def _play(
    service: ScreeningService, persona: Persona, rng: random.Random, now: datetime
) -> str:
    at = now - timedelta(seconds=rng.randint(4 * 3600, 14 * 24 * 3600))
    conversation_id = await service.start_conversation(
        persona.language, persona.country_hint, at=at
    )
    for text in persona.script(rng):
        at += timedelta(seconds=rng.randint(15, 180))  # the candidate types
        outcome = await service.send_message(conversation_id, text, at=at)
        await _summarise_if_due(service, conversation_id, outcome, at)
    if persona.silent_at_end:
        at += timedelta(hours=2)  # no answer: the silence timer fires (spec 008 later)
        outcome = await service.send_event(conversation_id, SilenceExpired(), at=at)
        await _summarise_if_due(service, conversation_id, outcome, at)
    return conversation_id


async def _summarise_if_due(
    service: ScreeningService, conversation_id: str, outcome: TurnOutcome, at: datetime
) -> None:
    if outcome.result.summary_due:  # what the API does in a background task
        await service.write_summary(conversation_id, at=at)
