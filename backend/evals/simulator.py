"""The simulated candidate: a small Claude model playing a persona, or a rule-based fake.

The LLM simulator sees only Sofi's messages (and their buttons) plus its persona, never
the engine state. The fake reads the engine's pending ask instead: it exists only to
smoke-test the harness offline (`--mode fake`), not to measure anything.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from evals.llm import END_TOKEN, cost_of, text_of
from evals.personas import Persona
from sazon_screening.engine import ConversationState
from sazon_screening.llm.settings import ModelPrice
from sazon_screening.vocab import FieldName, Language, PendingKind, Status

PROMPT_FILE = Path(__file__).with_name("simulator.v1.md")
SIMULATOR_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class Line:
    """One chat message as the candidate's phone shows it."""

    speaker: str  # "sofi" | "candidate"
    text: str
    buttons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimReply:
    text: str
    ended: bool
    cost_usd: float = 0.0
    latency_ms: int = 0


class Simulator(Protocol):
    async def reply(
        self, persona: Persona, chat: list[Line], state: ConversationState
    ) -> SimReply: ...


def render_sofi(line: Line) -> str:
    if not line.buttons:
        return line.text
    return f"{line.text}\n\n[Buttons: {' | '.join(line.buttons)}]"


def to_messages(chat: list[Line]) -> list[MessageParam]:
    """Sofi is the user, the candidate is the assistant; the list ends on Sofi's turn."""
    messages: list[MessageParam] = []
    for line in chat:
        if line.speaker == "sofi":
            messages.append({"role": "user", "content": render_sofi(line)})
        else:
            messages.append({"role": "assistant", "content": line.text})
    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": "(Sofi has not replied.)"})
    return messages


class LLMSimulator:
    def __init__(self, sdk: AsyncAnthropic, price: ModelPrice | None) -> None:
        self._sdk, self._price = sdk, price
        self._template = PROMPT_FILE.read_text(encoding="utf-8")

    async def reply(self, persona: Persona, chat: list[Line], state: ConversationState) -> SimReply:
        system = self._template.format(
            facts=persona.facts.strip(),
            style=persona.style.strip(),
            script=persona.script.strip() or "(nothing special)",
        )
        started = time.perf_counter()
        response = await self._sdk.messages.create(
            model=SIMULATOR_MODEL,
            max_tokens=1024,
            system=system,
            messages=to_messages(chat),
            output_config={"effort": "low"},
        )
        latency = round((time.perf_counter() - started) * 1000)
        cost = cost_of(response.usage, self._price)
        text = text_of(response)
        if response.stop_reason not in ("end_turn", "stop_sequence") or not text:
            # a refusal or truncation: end the conversation rather than send junk
            return SimReply(text="", ended=True, cost_usd=cost, latency_ms=latency)
        ended = text.strip() == END_TOKEN
        return SimReply(
            text=text.replace(END_TOKEN, "").strip(), ended=ended, cost_usd=cost, latency_ms=latency
        )


_VEHICLE_WORDS = {
    "motorbike": ("moto", "motorbike"),
    "car": ("coche", "car"),
    "bicycle": ("bici", "bike"),
    "e_bike": ("bici eléctrica", "e-bike"),
    "none": ("no tengo vehículo", "no vehicle"),
}
_AVAILABILITY_WORDS = {
    "full_time": ("jornada completa", "full time"),
    "part_time": ("media jornada", "part time"),
    "weekends": ("fines de semana", "weekends"),
}
_SCHEDULE_WORDS = {
    "morning": ("mañanas", "mornings"),
    "afternoon": ("tardes", "afternoons"),
    "evening": ("noches", "evenings"),
    "flexible": ("me da igual, flexible", "flexible"),
}


class FakeSimulator:
    """Answers the engine's pending ask from the persona's truth, in plain words."""

    async def reply(self, persona: Persona, chat: list[Line], state: ConversationState) -> SimReply:
        if state.status is not Status.in_progress:
            return SimReply(text="", ended=True)
        en = state.language is Language.en
        pending = state.pending
        if pending.kind is PendingKind.slot:
            buttons = chat[-1].buttons if chat else ()
            return SimReply(text=buttons[0] if buttons else "1", ended=False)
        if persona.expect.status is Status.opted_out and pending.field is FieldName.vehicle_type:
            return SimReply(
                text="not interested anymore" if en else "ya no me interesa", ended=False
            )
        if pending.kind is not PendingKind.ask or pending.field is None:
            return SimReply(text="yes" if en else "sí", ended=False)
        return SimReply(text=self._answer(persona, pending.field, en), ended=False)

    @staticmethod
    def _answer(persona: Persona, field: FieldName, en: bool) -> str:
        t, i = persona.truth, int(en)
        yes, no = ("yes", "no") if en else ("sí", "no")
        if field is FieldName.full_name and t.full_name:
            return t.full_name
        if field is FieldName.age and t.age is not None:
            return str(t.age)
        if field is FieldName.vehicle_type and t.vehicle_type:
            return _VEHICLE_WORDS[t.vehicle_type][i]
        if field is FieldName.has_license and t.has_license is not None:
            return yes if t.has_license else no
        if field is FieldName.location and t.location:
            if t.location.out_of_area:
                return "Bilbao"
            zone = (t.location.zone or "").split("-", 1)[-1].replace("-", " ")
            return f"{zone}, {t.location.city}"
        if field is FieldName.availability and t.availability:
            return ", ".join(_AVAILABILITY_WORDS[a][i] for a in t.availability)
        if field is FieldName.schedule and t.schedule:
            return ", ".join(_SCHEDULE_WORDS[s][i] for s in t.schedule)
        if field is FieldName.experience and t.experience:
            platforms = " ".join(t.experience.platforms)
            return f"{t.experience.years} años {platforms}".strip()
        if field is FieldName.start_date:
            return "tomorrow" if en else "mañana"
        return yes
