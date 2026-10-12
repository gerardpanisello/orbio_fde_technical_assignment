"""The FAQ knowledge base: `config/faq/faq.yaml`, validated at startup (spec 009 FR-1, AC-6).

The client edits the YAML; a mistake (a duplicate id, a missing language, an answer
that asks something) stops the agent at startup with `faq.yaml: <path>: <problem>`,
never mid-conversation.
"""

from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sazon_screening.config import load_yaml_model
from sazon_screening.vocab import Country, Language, Register

FAQ_DIR = "faq"
FAQ_FILE = "faq.yaml"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RetrievalConfig(_Frozen):
    top_k: int = Field(3, gt=0)
    min_score: float = Field(gt=0)  # below it: "lo consulto con el equipo" (FR-4)
    relative_min: float = Field(0.6, gt=0, le=1)  # extra entries must score this share of the best
    country_boost: float = Field(1.25, ge=1)  # the candidate's country beats "all"
    k1: float = Field(1.2, gt=0)  # BM25 term-frequency saturation
    b: float = Field(0.5, ge=0, le=1)  # BM25 length normalisation


class FaqEntry(_Frozen):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    country: Country | Literal["all"] = "all"
    updated: date
    tags: list[str] = []
    questions: dict[Language, list[str]]
    answer: dict[Register, str]

    @field_validator("questions")
    @classmethod
    def _every_language_asked(
        cls, questions: dict[Language, list[str]]
    ) -> dict[Language, list[str]]:
        missing = [lang.value for lang in Language if not any(questions.get(lang, []))]
        if missing:
            raise ValueError(f"missing question variants for {', '.join(missing)}")
        return questions

    @field_validator("answer")
    @classmethod
    def _required_registers(cls, answer: dict[Register, str]) -> dict[Register, str]:
        missing = [r.value for r in (Register.es_ES, Register.en) if not answer.get(r, "").strip()]
        if missing:
            raise ValueError(f"missing answer for {', '.join(missing)} (es-MX is optional)")
        asking = [r.value for r, text in answer.items() if "?" in text or "¿" in text]
        if asking:
            raise ValueError(f"an answer must not ask anything ({', '.join(asking)})")
        return answer

    def answer_for(self, register: Register) -> str:
        """es-MX falls back to es-ES: Mexico only overrides where the wording differs."""
        return self.answer.get(register) or self.answer[Register.es_ES]

    def first_question(self, language: Language) -> str:
        return self.questions[language][0]

    def applies_to(self, country: Country | None) -> bool:
        """Unknown country: only general entries. Known: general ones and that country's."""
        return self.country == "all" or self.country == country


class FaqBase(_Frozen):
    version: str
    retrieval: RetrievalConfig
    max_answer_chars: int = Field(330, gt=0)
    entries: list[FaqEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids_and_short_answers(self) -> Self:
        counts = Counter(entry.id for entry in self.entries)
        duplicates = sorted(entry_id for entry_id, n in counts.items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate entry id {', '.join(duplicates)}")
        too_long = [
            f"{entry.id} ({register.value}: {len(text)} chars)"
            for entry in self.entries
            for register, text in entry.answer.items()
            if len(text) > self.max_answer_chars
        ]
        if too_long:
            raise ValueError(f"answers longer than {self.max_answer_chars}: {', '.join(too_long)}")
        return self

    def entry(self, entry_id: str) -> FaqEntry:
        return next(e for e in self.entries if e.id == entry_id)


def load_faq(config_dir: Path) -> FaqBase:
    """Load `config/faq/faq.yaml`; raises `ConfigError("faq.yaml: <path>: <problem>")`."""
    return load_yaml_model(config_dir / FAQ_DIR / FAQ_FILE, FaqBase)
