"""T9/T14: versioned, static system prompts (FR-26, NFR-4, AC-25)."""

import re
from importlib.resources import files
from pathlib import Path

import pytest

from sazon_screening.config import ConfigError
from sazon_screening.llm.client.base import Role
from sazon_screening.llm.extraction.schema import ExtractionOutput
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import load_llm_config
from tests.paths import SHIPPED_CONFIG_DIR

PROMPT_FILES = sorted(
    entry.name
    for entry in files("sazon_screening.llm.prompts").iterdir()
    if entry.name.endswith(".md")
)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def test_every_prompt_in_the_shipped_config_loads() -> None:
    registry = PromptRegistry()
    for role in load_llm_config(SHIPPED_CONFIG_DIR).roles.values():
        prompt = registry.load(role.prompt)
        assert prompt.id == role.prompt
        assert prompt.text.strip()
        assert re.fullmatch(r"[0-9a-f]{12}", prompt.sha)


def test_the_judge_prompts_exist_too() -> None:
    assert {"judge_phrasing.v1.md", "judge_summary.v1.md"} <= set(PROMPT_FILES)


def test_sha_changes_when_the_text_changes(tmp_path: Path) -> None:
    (tmp_path / "demo.v1.md").write_text("Be brief.", encoding="utf-8")
    before = PromptRegistry(tmp_path).load("demo.v1").sha
    (tmp_path / "demo.v1.md").write_text("Be very brief.", encoding="utf-8")
    after = PromptRegistry(tmp_path).load("demo.v1").sha
    assert before != after


@pytest.mark.parametrize("prompt_id", ["nope.v1", "extraction", "../settings.v1", "a.v1.md"])
def test_unknown_or_malformed_id_is_a_config_error(prompt_id: str) -> None:
    with pytest.raises(ConfigError, match="prompt"):
        PromptRegistry().load(prompt_id)


def test_extraction_prompt_names_every_schema_field() -> None:
    """Guards drift: a schema field the prompt never explains is a field the model guesses.
    Checked on the prompt in use (llm.yaml): older versions predate newer fields."""
    text = _shipped_prompt(Role.extraction)
    missing = [name for name in ExtractionOutput.model_fields if f"`{name}`" not in text]
    assert missing == []


def test_extraction_prompt_treats_candidate_text_as_data() -> None:
    text = PromptRegistry().load("extraction.v1").text
    for tag in ("<candidate_message>", "<pending_ask>", "<recent_messages>"):
        assert tag in text


@pytest.mark.ac("003:AC-25")
@pytest.mark.parametrize("name", PROMPT_FILES)
def test_prompts_are_static(name: str) -> None:
    """No dates or per-request placeholders: the system prompt must be byte-stable to cache."""
    text = files("sazon_screening.llm.prompts").joinpath(name).read_text(encoding="utf-8")
    assert not DATE.search(text), f"{name} contains a date"
    assert not PLACEHOLDER.search(text), f"{name} contains a {{placeholder}}"


def _shipped_prompt(role: Role) -> str:
    return PromptRegistry().load(load_llm_config(SHIPPED_CONFIG_DIR).roles[role].prompt).text


def test_phrasing_prompt_covers_registers_and_length() -> None:
    text = _shipped_prompt(Role.phrasing)
    for register in ("es-ES", "es-MX", "en"):
        assert register in text
    assert "300 characters" in text
    for tag in ("<instruction>", "<reference_message>", "<candidate_last_message>", "<faq_answer>"):
        assert tag in text


def test_phrasing_prompt_forbids_a_second_hello() -> None:
    """Sample conversations: "¡Hola! Soy Sofi" on turn two; "tardes" answered with
    "¡Buenas tardes!"; "una pregunta más" with five questions to go."""
    text = _shipped_prompt(Role.phrasing)
    assert "Never say hello" in text
    assert "answer, not a greeting" in text
    assert "how many questions are left" in text
