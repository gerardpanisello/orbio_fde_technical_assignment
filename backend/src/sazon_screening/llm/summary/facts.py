"""The record facts of a recruiter summary, rendered by code (FR-19, FR-20, FR-21).

The record is the source of truth, so its facts are never written by the model: they
are looked up, value by value, in the recruiter's language. The model only adds a
short narrative next to them (summarizer.py).
"""

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateRecord, Profile
from sazon_screening.llm.phrasing.catalog import MessageCatalog, SummaryLabels
from sazon_screening.llm.phrasing.labels import field_values
from sazon_screening.vocab import Flag, Language, Status

TOP_FACTORS = 3


class SummaryFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str  # stable id for the dashboard, e.g. "status" or "field.location"
    label: str  # in the recruiter's language
    value: str


def render_facts(
    record: CandidateRecord, language: Language, catalog: MessageCatalog, config: EngineConfig
) -> list[SummaryFact]:
    """Facts in a fixed order. Opted-out: only what we may keep (no name, no answers)."""
    words = catalog.summary_labels(language)
    if record.status is Status.opted_out:
        return _opted_out(record, words, catalog, language)
    facts = [_fact("status", words, words.status[record.status])]
    if record.disqualification_reason is not None:
        reason = words.disqualification[record.disqualification_reason]
        facts.append(_fact("disqualification_reason", words, reason))
    if record.needs_review_reasons:
        reasons = ", ".join(words.review[r] for r in record.needs_review_reasons)
        facts.append(_fact("review_reasons", words, reasons))
    if record.score is not None:
        score = record.score
        facts.append(_fact("score", words, f"{score.score}/{score.max_score}"))
        facts.append(_fact("bucket", words, words.buckets[score.bucket]))
        top = sorted(score.factors, key=lambda f: f.points, reverse=True)[:TOP_FACTORS]
        factors = ", ".join(f"{words.factor_reasons[f.reason_code]} (+{f.points})" for f in top)
        facts.append(_fact("top_factors", words, factors))
    facts += _field_facts(record, language, catalog, config)
    if record.flags:
        facts.append(_fact("flags", words, ", ".join(words.flags[f] for f in record.flags)))
    facts.append(_fact("candidate_language", words, words.languages[record.language]))
    if record.drop_off_stage is not None:
        facts.append(_fact("drop_off_stage", words, words.stages[record.drop_off_stage]))
    if record.selected_slot_id is not None:
        facts.append(_fact("selected_slot", words, record.selected_slot_id))
    return facts


def _fact(key: str, words: SummaryLabels, value: str) -> SummaryFact:
    return SummaryFact(key=key, label=words.facts[key], value=value)


def _field_facts(
    record: CandidateRecord, language: Language, catalog: MessageCatalog, config: EngineConfig
) -> list[SummaryFact]:
    """The candidate's answers, worded exactly as the recap showed them."""
    labels = catalog.for_language(language).labels
    profile = Profile.model_validate(record.fields.model_dump())
    return [
        SummaryFact(key=f"field.{name.value}", label=labels.fields[name].capitalize(), value=value)
        for name, value in field_values(profile, config, language, labels).items()
    ]


def _opted_out(
    record: CandidateRecord, words: SummaryLabels, catalog: MessageCatalog, language: Language
) -> list[SummaryFact]:
    """FR-21: status, where it ended and do-not-contact. Nothing about the person."""
    facts = [_fact("status", words, words.status[record.status])]
    if record.drop_off_stage is not None:
        facts.append(_fact("drop_off_stage", words, words.stages[record.drop_off_stage]))
    yes_no = catalog.for_language(language).labels.yes_no
    do_not_contact = yes_no["yes" if Flag.do_not_contact in record.flags else "no"]
    facts.append(_fact("do_not_contact", words, do_not_contact))
    return facts
