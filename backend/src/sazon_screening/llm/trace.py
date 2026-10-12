"""What one turn returns: new state, the reply, and a trace of how we got there (FR-1).

The trace is what 004 stores next to each message and what 011 aggregates: the engine
input and action, how extraction and phrasing went, every LLM call's telemetry, and the
prompt and model versions. It never contains the candidate's text in telemetry (NFR-5).
"""

from pydantic import BaseModel, ConfigDict

from sazon_screening.engine import ConversationState, EngineAction, TurnInput
from sazon_screening.faq import FaqTrace
from sazon_screening.llm.client.base import Role
from sazon_screening.llm.extraction.extractor import ExtractionTrace
from sazon_screening.llm.phrasing.phraser import OutboundMessage, PhrasingTrace
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.llm.telemetry import CallTelemetry
from sazon_screening.vocab import Country


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TurnContextIn(_Frozen):
    """What the caller knows about this turn that the candidate did not say."""

    country_hint: Country | None = None  # e.g. from the phone prefix
    slots: list[SlotDisplay] | None = None  # interview slots on offer (010; the demo for now)
    zone_full: bool = False  # the candidate's area is fully staffed (spec 015; from 004)

    def slot_map(self) -> dict[str, SlotDisplay]:
        return {slot.id: slot for slot in self.slots or []}


class TurnTrace(_Frozen):
    turn_input: TurnInput | None  # None when the engine did not run (media)
    action: EngineAction | None
    extraction: ExtractionTrace
    phrasing: PhrasingTrace
    faq: FaqTrace | None = None  # 009: the turn asked a question (None: it did not)
    calls: list[CallTelemetry]
    prompts: dict[Role, str]  # role -> "extraction.v1@<sha>"
    models: dict[Role, str]
    client: str  # "anthropic" | "fake-rules" | "fake-scripted"
    cost_usd: float
    latency_ms: int


class TurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ConversationState
    reply: OutboundMessage | None  # None: send nothing (no_message)
    trace: TurnTrace
    summary_due: bool  # the status became terminal (again): 004 calls summarise() (FR-18)
