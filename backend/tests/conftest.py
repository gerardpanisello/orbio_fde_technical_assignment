"""Suite-wide test setup: the network guard and the `live` marker (spec 003 NFR-6)."""

import os

import pytest
from hypothesis import settings

from tests import network_guard

# Property tests: a quick, deterministic run by default; CI sets HYPOTHESIS_PROFILE=thorough.
# Both are derandomized, so a failure always reproduces with the same examples.
settings.register_profile("fast", max_examples=60, derandomize=True)
settings.register_profile("thorough", max_examples=300, derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "fast"))


@pytest.fixture(autouse=True)
def _block_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs offline, except those marked `live` (they call the real API)."""
    if request.node.get_closest_marker("live") is None:
        network_guard.install(monkeypatch)


def live_enabled() -> bool:
    """Live tests need BOTH the key and an explicit opt-in, so a stray key never costs money."""
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("LLM_MODE") == "anthropic"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if live_enabled():
        return
    skip = pytest.mark.skip(reason="live: set ANTHROPIC_API_KEY and LLM_MODE=anthropic")
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip)
