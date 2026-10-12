"""The message catalog: every candidate-facing template and label, per register (ADR 0006).

`config/messages/<register>.yaml` holds the product text Sofi falls back to (and speaks
in fake mode), plus the labels for enum values and the recruiter-summary labels. Ops
can fix a word without a deploy, so the loader is strict and fails at startup, naming
the file and the key, rather than mid-conversation:
- all three registers present;
- every engine action and preface has a template (checked against the engine's unions,
  so a new action type breaks the load, not a conversation);
- every field ask, re-ask reason and disqualification reason is covered;
- every enum value has a label;
- placeholders come from a per-template whitelist.
"""

import string
import warnings
from collections.abc import Iterator, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Self, get_args

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sazon_screening.config import ConfigError, load_yaml_model
from sazon_screening.engine import Preface, PrimaryAction
from sazon_screening.vocab import (
    Availability,
    Bucket,
    DisqualificationReason,
    FactorReason,
    FieldName,
    Flag,
    Language,
    ReaskReason,
    Register,
    ReviewReason,
    ScheduleSlot,
    Stage,
    Status,
    VehicleType,
)

# Template group -> the placeholders it may use. Anything else is a typo or a leak.
PLACEHOLDERS: dict[str, frozenset[str]] = {
    "greeting": frozenset({"privacy_url"}),
    "reask_field": frozenset({"field", "options"}),
    "confirm_ambiguous": frozenset({"options"}),
    "confirm_value": frozenset({"years"}),
    "show_recap": frozenset({"recap"}),
    "offer_slots": frozenset({"slots"}),
    "confirm_interview": frozenset({"slot"}),
    "prefaces": frozenset({"fields"}),
}
# Facts the recruiter summary renders (T22); each needs a label in every summary section.
FACT_KEYS = (
    "status",
    "disqualification_reason",
    "review_reasons",
    "score",
    "bucket",
    "top_factors",
    "flags",
    "candidate_language",
    "drop_off_stage",
    "selected_slot",
    "do_not_contact",
    "none",
    "overview",
    "sentiment",
    "observations",
)
SENTIMENTS = ("positive", "neutral", "negative")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _complete[E: StrEnum](labels: Mapping[E, str], enum: type[E]) -> Mapping[E, str]:
    missing = [member.value for member in enum if not labels.get(member)]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    return labels


class Labels(_Strict):
    yes_no: dict[str, str]
    vehicle_type: dict[VehicleType, str]
    availability: dict[Availability, str]
    schedule: dict[ScheduleSlot, str]
    fields: dict[FieldName, str]
    adult: dict[str, str]  # yes/no: "Mayor de edad" / "Menor de edad", for "I'm over 18"
    birth_year: str  # "año de nacimiento": shown next to a year instead of an age
    year: str  # "año", after exactly one year of experience
    years: str  # "años", after any other number of years of experience
    less_than_a_year: str  # "menos de 1 año": some experience, but under a year
    no_experience: str  # "Sin experiencia": no delivery experience at all

    @model_validator(mode="after")
    def _every_value(self) -> Self:
        for name, enum in (
            ("vehicle_type", VehicleType),
            ("availability", Availability),
            ("schedule", ScheduleSlot),
            ("fields", FieldName),
        ):
            try:
                _complete(getattr(self, name), enum)
            except ValueError as error:
                raise ValueError(f"labels.{name}: {error}") from None
        for name in ("yes_no", "adult"):
            if set(getattr(self, name)) != {"yes", "no"}:
                raise ValueError(f"labels.{name}: needs exactly 'yes' and 'no'")
        return self

    def group(self, name: str) -> Mapping[str, str]:
        """Labels by group name, as used by `EnumLabel` (yes_no, vehicle_type, ...)."""
        labels: Mapping[str, str] = getattr(self, name)
        return labels


class Prefaces(_Strict):
    redirect_off_topic: str
    redirect_abuse: str
    ack_correction: str
    faq_holding: str  # "Lo consulto con el equipo." when 009 has no answer (FR-17)


class Templates(_Strict):
    greeting: str
    ask_field: dict[FieldName, str]
    reask_field: dict[ReaskReason, str]
    confirm_ambiguous: str
    confirm_value: str
    ask_correction_field: str
    show_recap: str
    offer_slots: str
    confirm_interview: str
    close_disqualified: dict[DisqualificationReason, str]
    close_needs_review: str
    close_opted_out: str
    close_qualified_unscheduled: str
    handoff_to_human: str
    closed_ack: str
    prefaces: Prefaces
    media_not_supported: str

    @field_validator("ask_field")
    @classmethod
    def _every_field(cls, value: dict[FieldName, str]) -> dict[FieldName, str]:
        return dict(_complete(value, FieldName))

    @field_validator("reask_field")
    @classmethod
    def _every_reason(cls, value: dict[ReaskReason, str]) -> dict[ReaskReason, str]:
        return dict(_complete(value, ReaskReason))

    @field_validator("close_disqualified")
    @classmethod
    def _every_disqualification(
        cls, value: dict[DisqualificationReason, str]
    ) -> dict[DisqualificationReason, str]:
        return dict(_complete(value, DisqualificationReason))

    @model_validator(mode="after")
    def _known_placeholders(self) -> Self:
        for path, text in self.texts():
            allowed = PLACEHOLDERS.get(path.split(".")[0], frozenset())
            for name in placeholders_in(text):
                if name not in allowed:
                    raise ValueError(f"{path}: unknown placeholder {{{name}}}")
        return self

    def texts(self) -> Iterator[tuple[str, str]]:
        """Every template as (dotted.key, text), for validation and tests."""
        for key, value in self.model_dump(mode="json").items():
            if isinstance(value, dict):
                for sub_key, text in value.items():
                    yield f"{key}.{sub_key}", text
            else:
                yield key, value


class SummaryLabels(_Strict):
    """Recruiter-facing labels for the summary facts (FR-19); needed for es and en."""

    facts: dict[str, str]
    status: dict[Status, str]
    disqualification: dict[DisqualificationReason, str]
    review: dict[ReviewReason, str]
    flags: dict[Flag, str]
    stages: dict[Stage, str]
    buckets: dict[Bucket, str]
    factor_reasons: dict[FactorReason, str]
    languages: dict[Language, str]
    sentiments: dict[str, str]

    @model_validator(mode="after")
    def _every_value(self) -> Self:
        if set(self.sentiments) != set(SENTIMENTS):
            raise ValueError(f"summary.sentiments: needs exactly {', '.join(SENTIMENTS)}")
        missing_facts = [key for key in FACT_KEYS if not self.facts.get(key)]
        if missing_facts:
            raise ValueError(f"summary.facts: missing {', '.join(missing_facts)}")
        enums: dict[str, type[StrEnum]] = {
            "status": Status,
            "disqualification": DisqualificationReason,
            "review": ReviewReason,
            "flags": Flag,
            "stages": Stage,
            "buckets": Bucket,
            "factor_reasons": FactorReason,
            "languages": Language,
        }
        for name, enum in enums.items():
            try:
                _complete(getattr(self, name), enum)
            except ValueError as error:
                raise ValueError(f"summary.{name}: {error}") from None
        return self


# `register` is the contract name (ADR 0005); see engine/actions.py for why the warning is safe.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='Field name "register"', category=UserWarning)

    class RegisterCatalog(_Strict):
        version: str
        register: Register
        labels: Labels
        templates: Templates
        summary: SummaryLabels | None = None


class MessageCatalog(_Strict):
    registers: dict[Register, RegisterCatalog]

    def for_register(self, register: Register) -> RegisterCatalog:
        return self.registers[register]

    def for_language(self, language: Language) -> RegisterCatalog:
        """Where only the language is known (extraction labels, summaries): es means es-ES."""
        return self.registers[Register.en if language is Language.en else Register.es_ES]

    def label(self, group: str, value: str, language: Language) -> str:
        """An `EnumLabel` for the extractor's pending view."""
        return self.for_language(language).labels.group(group).get(value, value)

    def summary_labels(self, language: Language) -> SummaryLabels:
        labels = self.for_language(language).summary
        assert labels is not None, "checked by load_catalog"
        return labels


def placeholders_in(text: str) -> list[str]:
    return [name for _, name, _, _ in string.Formatter().parse(text) if name is not None]


def action_types(union: Any) -> set[str]:
    """The `type` literal of every model in an engine action union."""
    members = get_args(get_args(union)[0])
    return {member.model_fields["type"].default for member in members}


# Engine action type -> the catalog template that renders it (prefaces: the group).
_COVERED = set(Templates.model_fields) | {"no_message", "answer_faq", "ack_correction", "redirect"}


def load_catalog(directory: Path) -> MessageCatalog:
    """Load `<register>.yaml` for every register; raises ConfigError naming file and key."""
    uncovered = (action_types(PrimaryAction) | action_types(Preface)) - _COVERED
    if uncovered:  # a new engine action without a template: fail at startup, not mid-chat
        raise ConfigError(f"messages: no template for action(s) {', '.join(sorted(uncovered))}")
    registers: dict[Register, RegisterCatalog] = {}
    for register in Register:
        file_name = f"{register.value}.yaml"
        catalog = load_yaml_model(directory / file_name, RegisterCatalog)
        if catalog.register is not register:
            raise ConfigError(f"{file_name}: register: expected {register.value}")
        needs_summary = register in (Register.es_ES, Register.en)
        if needs_summary and catalog.summary is None:
            raise ConfigError(f"{file_name}: summary: missing (recruiter labels for es/en)")
        registers[register] = catalog
    return MessageCatalog(registers=registers)
