"""Settings for the LLM layer: environment (secrets, mode) and `config/llm.yaml` (FR-24, FR-25).

Two sources on purpose. The environment holds what differs per machine and must never
be committed (the API key, fake vs real). `llm.yaml` holds what ops tune and review in
a PR (models, limits, prices). Both fail fast at startup with a message naming the
cause, and there is never a silent switch to the fake (FR-24).
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    ValidationInfo,
    field_validator,
)

from sazon_screening.config import load_yaml_model
from sazon_screening.llm.client.base import Effort, Role
from sazon_screening.llm.client.retry import RetryPolicy
from sazon_screening.vocab import Language

LLM_CONFIG_FILE = "llm.yaml"
# The client-editable config/ lives at the repo root, not inside the package: ops edit
# it without a release. From a checkout this default finds it (backend/src/sazon_screening/
# llm/settings.py -> four levels up); an installed package sets SAZON_CONFIG_DIR instead.
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"
LLMMode = Literal["fake", "anthropic"]
_MODES: tuple[LLMMode, ...] = ("fake", "anthropic")


class SettingsError(Exception):
    """The environment cannot run the agent (unknown mode, missing key)."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Settings(_Frozen):
    llm_mode: LLMMode = "fake"  # spec 003 decision 9: offline by default
    anthropic_api_key: SecretStr | None = None
    config_dir: Path = DEFAULT_CONFIG_DIR


def load_settings(environ: Mapping[str, str] = os.environ) -> Settings:
    """Read LLM_MODE, ANTHROPIC_API_KEY and SAZON_CONFIG_DIR (`uv run --env-file` loads .env)."""
    mode = environ.get("LLM_MODE", "").strip() or "fake"
    if mode not in _MODES:
        raise SettingsError(f"LLM_MODE must be 'fake' or 'anthropic', got {mode!r}")
    key = environ.get("ANTHROPIC_API_KEY", "").strip()
    if mode == "anthropic" and not key:
        raise SettingsError(
            "LLM_MODE=anthropic requires ANTHROPIC_API_KEY "
            "(put it in .env and run with `uv run --env-file ../.env ...`)"
        )
    config_dir = environ.get("SAZON_CONFIG_DIR", "").strip()
    return Settings(
        llm_mode="anthropic" if mode == "anthropic" else "fake",
        anthropic_api_key=SecretStr(key) if key else None,
        config_dir=Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR,
    )


# --- llm.yaml --------------------------------------------------------------------------


class RoleConfig(_Frozen):
    model: str
    effort: Effort
    max_tokens: int = Field(gt=0)
    timeout_s: float = Field(gt=0)
    prompt: str  # prompt id, e.g. "extraction.v1" -> prompts/extraction.v1.md


class ModelPrice(_Frozen):
    """USD per million tokens. Cache reads and writes are priced apart from plain input."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_read: float = Field(ge=0)
    cache_write: float = Field(ge=0)


class LengthCaps(_Frozen):
    default: int = Field(300, gt=0)
    long: int = Field(600, gt=0)  # show_recap, offer_slots, FAQ answers (decision 5)


class GuardConfig(_Frozen):
    # Plan OQ-5: switch off if live runs show the language check rejecting good replies.
    language_check: bool = True


class LLMConfig(_Frozen):
    version: str
    roles: dict[Role, RoleConfig]
    retry: RetryPolicy = RetryPolicy()
    turn_budget_s: float = Field(15, gt=0)  # NFR-1 hard ceiling per candidate turn
    history_messages: int = Field(6, ge=0)
    max_message_chars: int = Field(2000, gt=0)
    length_caps: LengthCaps = LengthCaps()
    guard: GuardConfig = GuardConfig()
    media_placeholders: list[str] = []
    privacy_url: HttpUrl
    summary_default_language: Language = Language.es
    summary_max_transcript_chars: int = Field(8000, gt=0)
    prices: dict[str, ModelPrice]

    @field_validator("roles")
    @classmethod
    def _every_role(cls, roles: dict[Role, RoleConfig]) -> dict[Role, RoleConfig]:
        """A missing role would only show up when that call is first made."""
        missing = sorted(role.value for role in Role if role not in roles)
        if missing:
            raise ValueError(f"missing {', '.join(missing)}")
        return roles

    @field_validator("prices")
    @classmethod
    def _every_model_priced(
        cls, prices: dict[str, ModelPrice], info: ValidationInfo
    ) -> dict[str, ModelPrice]:
        """Cost telemetry (FR-27) needs a price for each configured model."""
        roles: dict[Role, RoleConfig] = info.data.get("roles", {})
        unpriced = sorted({config.model for config in roles.values()} - set(prices))
        if unpriced:
            raise ValueError(f"no price for {', '.join(unpriced)}")
        return prices


def load_llm_config(config_dir: Path) -> LLMConfig:
    """Load `llm.yaml`; raises `ConfigError("llm.yaml: <path>: <problem>")`."""
    return load_yaml_model(config_dir / LLM_CONFIG_FILE, LLMConfig)
