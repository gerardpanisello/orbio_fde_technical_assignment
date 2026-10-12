"""T1: the shipped FAQ loads, and a broken one fails at startup with a clear error (AC-6)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from sazon_screening.config import ConfigError
from sazon_screening.faq import FaqBase, load_faq
from sazon_screening.vocab import Country, Language, Register
from tests.paths import SHIPPED_CONFIG_DIR


@pytest.fixture(scope="module")
def shipped() -> FaqBase:
    return load_faq(SHIPPED_CONFIG_DIR)


def shipped_data() -> dict[str, Any]:
    text = (SHIPPED_CONFIG_DIR / "faq" / "faq.yaml").read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(text)
    return data


def write(tmp_path: Path, data: dict[str, Any]) -> Path:
    (tmp_path / "faq").mkdir()
    (tmp_path / "faq" / "faq.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return tmp_path


def test_the_shipped_faq_covers_the_spec_topics(shipped: FaqBase) -> None:
    ids = {entry.id for entry in shipped.entries}
    assert len(shipped.entries) >= 20
    for topic in ("pay-es", "pay-mx", "pay-general", "vehicle-own", "insurance", "tips"):
        assert topic in ids
    for entry in shipped.entries:
        for variants in entry.questions.values():
            assert 3 <= len(variants) <= 5, entry.id


def test_country_specific_pay_uses_the_country_currency(shipped: FaqBase) -> None:
    assert "€" in shipped.entry("pay-es").answer_for(Register.es_ES)
    assert "MXN" in shipped.entry("pay-mx").answer_for(Register.es_MX)
    assert shipped.entry("pay-es").country is Country.ES


def test_es_mx_falls_back_to_es_es(shipped: FaqBase) -> None:
    tips = shipped.entry("tips")
    assert Register.es_MX not in tips.answer
    assert tips.answer_for(Register.es_MX) == tips.answer[Register.es_ES]
    assert tips.first_question(Language.en) == "Do I keep the tips?"


@pytest.mark.ac("009:AC-6")
def test_a_duplicate_id_fails_at_startup(tmp_path: Path) -> None:
    data = shipped_data()
    data["entries"][1]["id"] = data["entries"][0]["id"]
    with pytest.raises(ConfigError, match=r"faq\.yaml: .*duplicate entry id pay-es"):
        load_faq(write(tmp_path, data))


@pytest.mark.ac("009:AC-6")
def test_a_missing_answer_language_fails_at_startup(tmp_path: Path) -> None:
    data = shipped_data()
    del data["entries"][0]["answer"]["en"]
    with pytest.raises(ConfigError, match=r"entries\.0\.answer: .*missing answer for en"):
        load_faq(write(tmp_path, data))


@pytest.mark.ac("009:AC-6")
def test_missing_question_variants_fail_at_startup(tmp_path: Path) -> None:
    data = shipped_data()
    del data["entries"][3]["questions"]["en"]
    with pytest.raises(ConfigError, match=r"entries\.3\.questions: .*variants for en"):
        load_faq(write(tmp_path, data))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda e: e["answer"].update({"en": "Want to know more?"}), "must not ask"),
        (lambda e: e["answer"].update({"en": "x" * 400}), "longer than 330"),
        (lambda e: e.update({"country": "FR"}), "country"),
        (lambda e: e["answer"].update({"fr": "Bonjour"}), "answer"),
    ],
    ids=["asks", "too-long", "unknown-country", "unknown-register"],
)
def test_other_content_mistakes_fail_at_startup(tmp_path: Path, change: Any, message: str) -> None:
    data = shipped_data()
    change(data["entries"][0])
    with pytest.raises(ConfigError, match=message):
        load_faq(write(tmp_path, data))


def test_a_missing_file_names_it(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"faq\.yaml: file not found"):
        load_faq(tmp_path)
