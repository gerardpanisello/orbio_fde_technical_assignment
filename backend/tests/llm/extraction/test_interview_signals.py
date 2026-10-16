"""Spec 010 T3: the extractor's side of moving or cancelling an interview."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateTurn, Signals, SlotSelected, TurnContext
from sazon_screening.llm.client.fake_rules import RuleExtractor
from sazon_screening.llm.extraction.mapping import to_turn_input
from sazon_screening.llm.extraction.pending import pending_view
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.vocab import Language, PendingKind, Status
from tests.engine.builders import Convo
from tests.llm.builders import out, pending

SLOTS = {"s1": SlotDisplay(id="s1", labels={Language.es: "martes 13/10, 10:00"})}


def test_both_signals_are_on_the_wire_required_and_plain() -> None:
    schema = ExtractionOutput.model_json_schema()
    for name in ("reschedule_interview", "cancel_interview"):
        assert name in schema["required"]
        assert schema["properties"][name]["type"] == "boolean"


@pytest.mark.ac("010:AC-3")
def test_the_signals_reach_the_engine() -> None:
    mapped = to_turn_input(
        out(reschedule_interview=True), pending(PendingKind.slot, options=("s1",)), TurnContext()
    )
    assert isinstance(mapped.turn_input, CandidateTurn)
    assert mapped.turn_input.signals == Signals(reschedule_interview=True)
    cancel = to_turn_input(out(cancel_interview=True), pending(), TurnContext())
    assert isinstance(cancel.turn_input, CandidateTurn)
    assert cancel.turn_input.signals.cancel_interview is True


def test_a_pick_together_with_a_request_is_not_a_pick() -> None:
    mapped = to_turn_input(
        out(chosen_option_id="s1", reschedule_interview=True),
        pending(PendingKind.slot, options=("s1",)),
        TurnContext(),
    )
    assert not isinstance(mapped.turn_input, SlotSelected)


def test_a_booked_conversation_shows_its_interview_and_nothing_to_pick(
    engine_config: EngineConfig, catalog: MessageCatalog
) -> None:
    c = Convo(engine_config).advance_to_status(Status.interview_scheduled)  # slot s1
    view = pending_view(c.state, engine_config, catalog, SLOTS)
    assert view.booked_interview == "martes 13/10, 10:00"
    assert view.options == []  # an old option id must not book again
    fresh = pending_view(Convo(engine_config).state, engine_config, catalog, SLOTS)
    assert fresh.booked_interview is None


@pytest.mark.parametrize(
    ("text", "reschedule", "cancel"),
    [
        ("¿Puedo cambiar la entrevista?", True, False),
        ("no puedo el martes, ¿hay otro día?", True, False),
        ("quiero una cita", True, False),
        ("Can I reschedule?", True, False),
        ("cancela la cita", False, True),
        ("Anula la entrevista, gracias", False, True),
        ("please cancel my interview", False, True),
        ("sí", False, False),
    ],
)
def test_offline_rules_read_the_requests(
    engine_config: EngineConfig, text: str, reschedule: bool, cancel: bool
) -> None:
    extracted = RuleExtractor(engine_config).extract(text, pending(PendingKind.slot))
    assert (extracted.reschedule_interview, extracted.cancel_interview) == (reschedule, cancel)
    assert extracted.opt_out is False
