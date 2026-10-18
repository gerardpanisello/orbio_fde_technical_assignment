"""T22: the record facts of the recruiter summary come from the record, by code (FR-19..21)."""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine import CandidateRecord, Month, Offset
from sazon_screening.llm.phrasing.catalog import MessageCatalog
from sazon_screening.llm.summary.facts import SummaryFact, render_facts
from sazon_screening.vocab import RECRUITER_LANGUAGES, Flag, Language, Stage, Status
from tests.engine.builders import Convo, name, start_date

TERMINAL = [
    Status.interview_scheduled,
    Status.qualified_unscheduled,
    Status.disqualified,
    Status.needs_review,
    Status.abandoned,
]


def record_for(status: Status, config: EngineConfig) -> CandidateRecord:
    return Convo(config).advance_to_status(status).record()


def by_key(facts: list[SummaryFact]) -> dict[str, str]:
    return {fact.key: fact.value for fact in facts}


@pytest.mark.ac("003:AC-17")
@pytest.mark.parametrize("language", RECRUITER_LANGUAGES)
@pytest.mark.parametrize("status", TERMINAL)
def test_facts_equal_the_record(
    catalog: MessageCatalog, engine_config: EngineConfig, status: Status, language: Language
) -> None:
    record = record_for(status, engine_config)
    words = catalog.summary_labels(language)
    facts = by_key(render_facts(record, language, catalog, engine_config))
    assert facts["status"] == words.status[record.status]
    assert facts["candidate_language"] == words.languages[record.language]
    if record.disqualification_reason is not None:
        assert (
            facts["disqualification_reason"]
            == words.disqualification[record.disqualification_reason]
        )
    else:
        assert "disqualification_reason" not in facts
    expected_reasons = ", ".join(words.review[r] for r in record.needs_review_reasons)
    assert facts.get("review_reasons", "") == expected_reasons
    if record.score is not None:
        assert facts["score"] == f"{record.score.score}/{record.score.max_score}"
        assert facts["bucket"] == words.buckets[record.score.bucket]
    else:
        assert "score" not in facts
    assert facts.get("flags", "") == ", ".join(words.flags[f] for f in record.flags)
    if record.drop_off_stage is not None:
        assert facts["drop_off_stage"] == words.stages[record.drop_off_stage]
    assert facts.get("selected_slot") == record.selected_slot_id
    name = record.fields.full_name.value
    if name is not None:
        assert facts["field.full_name"] == name


def test_top_factors_are_the_three_biggest(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    record = record_for(Status.interview_scheduled, engine_config)
    assert record.score is not None
    facts = by_key(render_facts(record, Language.en, catalog, engine_config))
    top = sorted(record.score.factors, key=lambda f: f.points, reverse=True)[:3]
    assert facts["top_factors"].count("(+") == 3
    assert f"(+{top[0].points})" in facts["top_factors"].split(", ")[0]


def test_field_values_use_the_recruiter_language(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    record = record_for(Status.interview_scheduled, engine_config)
    spanish = by_key(render_facts(record, Language.es, catalog, engine_config))
    english = by_key(render_facts(record, Language.en, catalog, engine_config))
    assert spanish["field.vehicle_type"] == "Moto"
    assert english["field.vehicle_type"] == "Motorbike"
    assert english["field.location"] == "Coyoacán (Mexico City)"


@pytest.mark.ac("003:AC-18")
@pytest.mark.parametrize("language", RECRUITER_LANGUAGES)
def test_opted_out_has_no_personal_data(
    catalog: MessageCatalog, engine_config: EngineConfig, language: Language
) -> None:
    convo = Convo(engine_config).advance_to_status(Status.in_progress)
    convo.say(name("Ana López")).say(opt_out=True)
    facts = render_facts(convo.record(), language, catalog, engine_config)
    assert [fact.key for fact in facts] == ["status", "drop_off_stage", "do_not_contact"]
    assert all("Ana" not in fact.value for fact in facts)
    assert facts[-1].value == catalog.for_language(language).labels.yes_no["yes"]


@pytest.mark.parametrize(
    ("language", "expected"),
    [(Language.es, "a partir de noviembre"), (Language.en, "from November")],
)
def test_month_level_start_date_reads_as_the_month(
    catalog: MessageCatalog, engine_config: EngineConfig, language: Language, expected: str
) -> None:
    convo = Convo(engine_config).advance_to(Stage.start_date)
    record = convo.say(start_date(Offset(amount=1, unit="months"))).record()
    assert Flag.start_date_approximate in record.flags
    facts = by_key(render_facts(record, language, catalog, engine_config))
    assert facts["field.start_date"] == expected


def test_exact_start_date_still_reads_as_a_date(
    catalog: MessageCatalog, engine_config: EngineConfig
) -> None:
    convo = Convo(engine_config).advance_to(Stage.start_date)
    convo.say(start_date(Month(month=11)))
    record = convo.say(start_date(Offset(amount=3, unit="days"))).record()
    facts = by_key(render_facts(record, Language.es, catalog, engine_config))
    assert facts["field.start_date"] == "jueves 15/10/2026"
