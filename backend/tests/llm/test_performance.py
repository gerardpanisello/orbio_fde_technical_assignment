"""T27: the offline agent is fast enough for tests and the demo (NFR-1: < 50 ms per turn)."""

import time

import pytest

from tests.llm.chat import SPANISH_SCRIPT, Chat

RUNS = 20


@pytest.mark.anyio
async def test_mean_turn_time_in_fake_mode(chat: Chat) -> None:
    turns, started = 0, time.perf_counter()
    for _ in range(RUNS):
        chat.state, chat.history, chat.results = None, [], []
        await chat.start()
        for text in SPANISH_SCRIPT:
            await chat.say(text)
        turns += 1 + len(SPANISH_SCRIPT)
    mean_ms = (time.perf_counter() - started) * 1000 / turns
    assert mean_ms < 50, f"{mean_ms:.1f} ms per turn"
