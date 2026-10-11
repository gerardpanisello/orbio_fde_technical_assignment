"""T25: the client factory and build_agent (FR-24, AC-22)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.llm.client.factory import make_client
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.pipeline import ScreeningAgent, build_agent
from sazon_screening.llm.settings import Settings, SettingsError, load_settings


def test_fake_rules_by_default(engine_config: EngineConfig) -> None:
    client = make_client(load_settings({}), engine_config=engine_config)
    assert isinstance(client, FakeLLMClient)
    assert client.name == "fake-rules"


@pytest.mark.ac("003:AC-22")
def test_anthropic_without_a_key_fails_at_startup() -> None:
    with pytest.raises(SettingsError, match="ANTHROPIC_API_KEY"):
        build_agent(load_settings({"LLM_MODE": "anthropic"}))


@pytest.mark.ac("003:AC-22")
def test_a_settings_object_without_a_key_is_refused_too(engine_config: EngineConfig) -> None:
    with pytest.raises(SettingsError, match="ANTHROPIC_API_KEY"):
        make_client(Settings(llm_mode="anthropic"), engine_config=engine_config)


def test_build_agent_wires_the_shipped_config() -> None:
    assert isinstance(build_agent(load_settings({})), ScreeningAgent)
