"""WhatsApp settings (spec 016 FR-7): secrets from the environment, the rest from YAML.

Off by default: the app, the tests and the demo run without any Meta credentials. When
`WHATSAPP_ENABLED=true`, every secret must be set or the API refuses to start, naming
the missing variable (a webhook that silently rejects everything is worse).
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from sazon_screening.config import load_yaml_model
from sazon_screening.llm.settings import SettingsError
from sazon_screening.vocab import Country, Language

WHATSAPP_FILE = "whatsapp.yaml"
DEFAULT_API_VERSION = "v25.0"  # Graph API version used in Meta's Cloud API docs (2026-10)
_TRUE = {"true", "on", "1", "yes"}
_FALSE = {"false", "off", "0", "no", ""}


class WhatsAppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    token: SecretStr = SecretStr("")
    phone_number_id: str = ""
    verify_token: SecretStr = SecretStr("")
    app_secret: SecretStr = SecretStr("")
    api_version: str = DEFAULT_API_VERSION

    @model_validator(mode="after")
    def _complete_when_enabled(self) -> Self:
        if not self.enabled:
            return self
        missing = [
            name
            for name, value in (
                ("WHATSAPP_TOKEN", self.token.get_secret_value()),
                ("WHATSAPP_PHONE_NUMBER_ID", self.phone_number_id),
                ("WHATSAPP_VERIFY_TOKEN", self.verify_token.get_secret_value()),
                ("WHATSAPP_APP_SECRET", self.app_secret.get_secret_value()),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"WHATSAPP_ENABLED=true needs {', '.join(missing)}")
        return self

    @property
    def messages_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"


def load_whatsapp_settings(environ: Mapping[str, str] = os.environ) -> WhatsAppSettings:
    """Read WHATSAPP_ENABLED (true/false), _TOKEN, _PHONE_NUMBER_ID, _VERIFY_TOKEN,
    _APP_SECRET and _API_VERSION."""
    raw = environ.get("WHATSAPP_ENABLED", "").strip().lower()
    if raw not in _TRUE | _FALSE:
        raise SettingsError(f"WHATSAPP_ENABLED must be 'true' or 'false', got {raw!r}")
    try:
        return WhatsAppSettings(
            enabled=raw in _TRUE,
            token=SecretStr(environ.get("WHATSAPP_TOKEN", "").strip()),
            phone_number_id=environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            verify_token=SecretStr(environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()),
            app_secret=SecretStr(environ.get("WHATSAPP_APP_SECRET", "").strip()),
            api_version=environ.get("WHATSAPP_API_VERSION", "").strip() or DEFAULT_API_VERSION,
        )
    except ValidationError as error:
        problems = "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in error.errors())
        raise SettingsError(problems) from None


# --- config/whatsapp.yaml ----------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TemplateRef(_Strict):
    """A Meta-approved message template: sendable outside the 24 h window."""

    name: str = Field(min_length=1)
    language: str = Field(min_length=2)  # Meta's code, e.g. "es_ES", "es_MX", "en_US"
    placeholder: bool = False  # true: not a real reminder (hello_world): warn on every send


class WhatsAppConfig(_Strict):
    version: str
    follow_up_template: TemplateRef
    # Spec 010 FR-6: the interview reminder outside the 24 h window; unset: the follow-up one.
    reminder_template: TemplateRef | None = None
    list_button: dict[Language, str]
    country_prefixes: dict[str, Country]

    @model_validator(mode="after")
    def _check(self) -> Self:
        missing = [lang.value for lang in Language if lang not in self.list_button]
        if missing:
            raise ValueError(f"list_button: missing {', '.join(missing)}")
        too_long = [t for t in self.list_button.values() if not 0 < len(t) <= 20]
        if too_long:
            raise ValueError(f"list_button: 1 to 20 characters (WhatsApp limit): {too_long}")
        if any(not prefix.isdigit() for prefix in self.country_prefixes):
            raise ValueError("country_prefixes: keys are digits only, e.g. '34'")
        return self

    def country_for(self, wa_id: str) -> Country | None:
        """The longest matching prefix wins (wa_id is digits only, no '+')."""
        for prefix in sorted(self.country_prefixes, key=len, reverse=True):
            if wa_id.startswith(prefix):
                return self.country_prefixes[prefix]
        return None


def load_whatsapp_config(config_dir: Path) -> WhatsAppConfig:
    return load_yaml_model(config_dir / WHATSAPP_FILE, WhatsAppConfig)
