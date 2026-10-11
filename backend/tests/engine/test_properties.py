"""T29: invariants that must hold for ANY input sequence (NFR-1, NFR-5, plan §7.4)."""

import json
from itertools import pairwise

from hypothesis import HealthCheck, given, settings

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import EngineAction, register_for
from sazon_screening.engine.enums import Flag, Status
from sazon_screening.engine.inputs import TurnInput
from sazon_screening.engine.record import build_record
from sazon_screening.engine.state import ConversationState, Profile
from sazon_screening.engine.turn import start, step_unchecked
from tests.engine.conftest import TODAY
from tests.engine.privacy import leaked_record, leaked_state
from tests.engine.strategies import conversations

S = Status
_FROM_IN_PROGRESS = {
    S.opted_out,
    S.disqualified,
    S.needs_review,
    S.abandoned,
    S.qualified_unscheduled,
    S.interview_scheduled,
}
# Plan §4.2. A turn after silence resumes AND is evaluated in the same step, so an
# abandoned conversation can reach whatever a candidate turn can (not a slot booking:
# slot events on an abandoned conversation are ignored).
ALLOWED = (
    {(S.in_progress, target) for target in _FROM_IN_PROGRESS}
    | {(S.abandoned, target) for target in _FROM_IN_PROGRESS - {S.interview_scheduled}}
    | {(S.abandoned, S.in_progress)}
    | {(S.disqualified, S.needs_review)}
    | {(closed, S.opted_out) for closed in Status if closed is not S.opted_out}
)


def run(
    config: EngineConfig, turns: list[TurnInput]
) -> list[tuple[ConversationState, EngineAction]]:
    state, action = start(config)
    history = [(state, action)]
    for turn in turns:
        before = state.model_dump()
        state, action = step_unchecked(state, turn, config, TODAY)
        assert history[-1][0].model_dump() == before, "step mutated its input state"
        history.append((state, action))
    return history


@settings(
    max_examples=300,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(turns=conversations())
def test_engine_invariants(config: EngineConfig, turns: list[TurnInput]) -> None:
    history = run(config, turns)
    limit = config.thresholds.max_reasks + 1
    for (before, _), (state, action) in pairwise(history):
        _check_action(config, state, action)
        if before.status is not state.status:
            assert (before.status, state.status) in ALLOWED, (before.status, state.status)
        if state.status is Status.opted_out:
            assert state.profile == Profile()
            assert state.flags == [Flag.do_not_contact]
            assert leaked_state(state) == {}
            assert leaked_record(build_record(state, config), config) == {}
        assert all(count <= limit for count in state.reasks.values()), state.reasks
        record = build_record(state, config)
        json.dumps(record.model_dump(mode="json"))
    _check_deterministic(config, turns, history)


def _check_action(config: EngineConfig, state: ConversationState, action: EngineAction) -> None:
    assert action.primary.type  # exactly one primary action, always typed
    assert action.language is state.language
    location = state.profile.location.value
    expected = register_for(
        state.language,
        location.country if location is not None else None,
        state.country_hint,
        default_country=config.screening.default_country,
    )
    assert action.register is expected


def _check_deterministic(
    config: EngineConfig,
    turns: list[TurnInput],
    history: list[tuple[ConversationState, EngineAction]],
) -> None:
    again = run(config, turns)
    first = [(s.model_dump_json(), a.model_dump_json()) for s, a in history]
    second = [(s.model_dump_json(), a.model_dump_json()) for s, a in again]
    assert first == second
