"""T29: a turn takes well under 10 ms (NFR-4). A regression guard, not a benchmark."""

import time

from sazon_screening.config import EngineConfig
from sazon_screening.engine.inputs import SlotSelected, TurnInput
from sazon_screening.engine.step import start, step_unchecked
from tests.engine.builders import canonical_turns
from tests.engine.conftest import TODAY

RUNS = 200


def test_mean_turn_time_is_under_10_ms(config: EngineConfig) -> None:
    turns: list[TurnInput] = [*canonical_turns(), SlotSelected(slot_id="s1")]
    began = time.perf_counter()
    for _ in range(RUNS):
        state, _ = start(config)
        for turn in turns:
            state, _ = step_unchecked(state, turn, config, TODAY)
    mean_ms = (time.perf_counter() - began) * 1000 / (RUNS * len(turns))
    assert state.status == "interview_scheduled"
    assert mean_ms < 10, f"{mean_ms:.2f} ms per turn"
