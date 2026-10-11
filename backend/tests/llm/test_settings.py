"""T5: environment settings and `llm.yaml` (FR-24, FR-25, AC-22, AC-24)."""

import shutil
from pathlib import Path

import pytest
import yaml

from sazon_screening.config import ConfigError
from sazon_screening.llm.client.base import Effort, Role
from sazon_screening.llm.settings import (
    LLMConfig,
    SettingsError,
    load_llm_config,
    load_settings,
)
from sazon_screening.vocab import Language
from tests.paths import FIXTURE_CONFIG_DIR, SHIPPED_CONFIG_DIR


class TestSettings:
    def test_default_mode_is_fake(self) -> None:
        settings = load_settings({})
        assert settings.llm_mode == "fake"
        assert settings.anthropic_api_key is None

    @pytest.mark.ac("003:AC-22")
    def test_anthropic_without_a_key_names_the_variable(self) -> None:
        with pytest.raises(SettingsError, match="ANTHROPIC_API_KEY"):
            load_settings({"LLM_MODE": "anthropic", "ANTHROPIC_API_KEY": "  "})

    @pytest.mark.ac("003:AC-22")
    def test_unknown_mode_names_the_allowed_values(self) -> None:
        with pytest.raises(SettingsError, match=r"'fake' or 'anthropic', got 'foo'"):
            load_settings({"LLM_MODE": "foo"})

    def test_anthropic_with_a_key_keeps_it_secret(self) -> None:
        settings = load_settings({"LLM_MODE": "anthropic", "ANTHROPIC_API_KEY": "sk-test"})
        assert settings.llm_mode == "anthropic"
        assert settings.anthropic_api_key is not None
        assert settings.anthropic_api_key.get_secret_value() == "sk-test"
        assert "sk-test" not in repr(settings)

    def test_config_dir_defaults_to_the_repo_config(self) -> None:
        assert load_settings({}).config_dir == SHIPPED_CONFIG_DIR


def copy_config(tmp_path: Path, source: Path = SHIPPED_CONFIG_DIR) -> Path:
    shutil.copy(source / "llm.yaml", tmp_path / "llm.yaml")
    return tmp_path


def edit_yaml(config_dir: Path, change: dict[str, object]) -> None:
    path = config_dir / "llm.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.update(change)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


class TestLLMConfig:
    def test_shipped_config_loads_with_the_adr_0001_models(self) -> None:
        config = load_llm_config(SHIPPED_CONFIG_DIR)
        assert config.roles[Role.extraction].model == "claude-haiku-5-5"
        assert config.roles[Role.phrasing].model == "claude-sonnet-5-5"
        assert config.roles[Role.judge].effort is Effort.medium
        assert config.turn_budget_s == 15
        assert (config.length_caps.default, config.length_caps.long) == (300, 600)
        assert config.summary_default_language is Language.es

    def test_fixture_config_loads(self) -> None:
        assert isinstance(load_llm_config(FIXTURE_CONFIG_DIR), LLMConfig)

    def test_missing_role_is_named(self, tmp_path: Path) -> None:
        config_dir = copy_config(tmp_path)
        roles = load_llm_config(config_dir).model_dump(mode="json")["roles"]
        del roles["summary"]
        edit_yaml(config_dir, {"roles": roles})
        with pytest.raises(ConfigError, match=r"llm\.yaml: roles: .*summary"):
            load_llm_config(config_dir)

    def test_model_without_a_price_is_named(self, tmp_path: Path) -> None:
        config_dir = copy_config(tmp_path)
        prices = load_llm_config(config_dir).model_dump(mode="json")["prices"]
        del prices["claude-opus-5-5"]
        edit_yaml(config_dir, {"prices": prices})
        with pytest.raises(ConfigError, match=r"llm\.yaml: .*claude-opus-5-5"):
            load_llm_config(config_dir)

    def test_missing_file_is_a_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match=r"llm\.yaml: file not found"):
            load_llm_config(tmp_path)

    @pytest.mark.ac("003:AC-24")
    def test_changing_the_yaml_changes_the_model(self, tmp_path: Path) -> None:
        config_dir = copy_config(tmp_path)
        data = load_llm_config(config_dir).model_dump(mode="json")
        data["roles"]["extraction"]["model"] = "claude-sonnet-5-5"
        edit_yaml(config_dir, {"roles": data["roles"]})
        assert load_llm_config(config_dir).roles[Role.extraction].model == "claude-sonnet-5-5"
