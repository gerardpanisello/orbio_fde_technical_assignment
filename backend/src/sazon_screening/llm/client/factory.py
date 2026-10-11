"""Pick the LLM client from the settings, failing fast (FR-24).

There is never a silent switch to the fake: `anthropic` without a key fails at startup
(`load_settings`), and the Anthropic SDK is imported only in anthropic mode, so the
offline demo and the tests never need it configured (NFR-7).
"""

from sazon_screening.config import EngineConfig
from sazon_screening.llm.client.base import LLMClient
from sazon_screening.llm.client.fake import FakeLLMClient
from sazon_screening.llm.settings import Settings, SettingsError


def make_client(settings: Settings, *, engine_config: EngineConfig) -> LLMClient:
    if settings.llm_mode == "fake":
        return FakeLLMClient(mode="rules", engine_config=engine_config)
    if settings.anthropic_api_key is None:  # load_settings already refuses this
        raise SettingsError("LLM_MODE=anthropic requires ANTHROPIC_API_KEY")
    # Imported here so fake mode never loads the SDK (NFR-7).
    from sazon_screening.llm.client.anthropic_client import AnthropicClient

    return AnthropicClient(settings.anthropic_api_key)
