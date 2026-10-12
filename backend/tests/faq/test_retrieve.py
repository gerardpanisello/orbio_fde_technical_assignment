"""T2: BM25 over the shipped FAQ (FR-2, AC-1..AC-3). No model involved."""

import pytest

from sazon_screening.faq import FaqRetriever, answer_question, load_faq
from sazon_screening.faq.retrieve import fold, stem, tokens
from sazon_screening.vocab import Country, Language, Register
from tests.paths import SHIPPED_CONFIG_DIR


@pytest.fixture(scope="module")
def retriever() -> FaqRetriever:
    return FaqRetriever(load_faq(SHIPPED_CONFIG_DIR))


def best(retriever: FaqRetriever, question: str, country: Country | None = None) -> str | None:
    confident = retriever.confident(retriever.search(question, country))
    return confident[0].entry_id if confident else None


def test_normalisation_ignores_accents_case_and_endings() -> None:
    assert fold("¿CUÁNTO?") == "¿cuanto?"
    assert {stem("pagan"), stem("paga"), stem("pago"), stem("pagamos")} == {"pag"}
    assert stem("bikes") == stem("bike")
    assert tokens("¿Cuál es la capital?") == ["capital"]  # stopwords out


AC1_QUESTIONS = ["¿cuánto se cobra?", "how much do you pay?", "cuánto pagan la hora"]


@pytest.mark.ac("009:AC-1")
@pytest.mark.parametrize("question", AC1_QUESTIONS)
@pytest.mark.parametrize("country", [None, Country.ES, Country.MX])
def test_pay_questions_retrieve_the_pay_entry_first(
    retriever: FaqRetriever, question: str, country: Country | None
) -> None:
    top = best(retriever, question, country)
    assert top is not None
    assert top.startswith("pay-")


@pytest.mark.ac("009:AC-1")
def test_accents_and_case_do_not_matter(retriever: FaqRetriever) -> None:
    assert retriever.search("CUANTO PAGAN LA HORA", None) == retriever.search(
        "¿Cuánto pagan la hora?", None
    )


@pytest.mark.parametrize(
    ("question", "entry"),
    [
        ("do I need my own bike?", "vehicle-own"),
        ("¿necesito moto propia?", "vehicle-own"),
        ("¿qué horario hay?", "schedule-shifts"),
        ("¿me quedo las propinas?", "tips"),
        ("when do I get paid?", "payment-frequency"),
        ("¿cuándo se cobra?", "payment-frequency"),
        ("¿hay que trabajar los findes?", "weekends"),
        ("¿quién paga la gasolina?", "fuel-maintenance"),
        ("¿puedo trabajar en glovo también?", "multiple-apps"),
        ("¿cuánto dura la entrevista?", "interview-format"),
        ("¿qué papeles necesito?", "documents"),
        ("¿cuántas horas a la semana?", "minimum-hours"),
    ],
)
def test_other_topics_find_their_entry(retriever: FaqRetriever, question: str, entry: str) -> None:
    assert best(retriever, question, Country.ES) == entry


@pytest.mark.ac("009:AC-2")
@pytest.mark.parametrize(
    ("country", "register", "entry", "currency"),
    [
        (Country.MX, Register.es_MX, "pay-mx", "MXN"),
        (Country.ES, Register.es_ES, "pay-es", "€"),
        (Country.MX, Register.en, "pay-mx", "MXN"),
    ],
)
def test_the_pay_answer_follows_the_country(
    retriever: FaqRetriever, country: Country, register: Register, entry: str, currency: str
) -> None:
    trace, grounding = answer_question(
        retriever, "¿cuánto se paga?", country=country, register=register, language=Language.es
    )
    assert trace.outcome == "answered"
    assert trace.entry_ids == [entry]  # the other country's entry is never shown
    assert grounding is not None
    assert currency in grounding.answer
    other = "€" if currency == "MXN" else "MXN"
    assert all(other not in text for text in grounding.approved)


@pytest.mark.ac("009:AC-2")
def test_unknown_country_gets_the_general_answer_without_amounts(
    retriever: FaqRetriever,
) -> None:
    trace, grounding = answer_question(
        retriever, "¿cuánto se paga?", country=None, register=Register.es_ES, language=Language.es
    )
    assert trace.entry_ids == ["pay-general"]
    assert grounding is not None
    assert "Depende del país y de la ciudad" in grounding.answer
    assert "€" not in grounding.answer
    assert "MXN" not in grounding.answer


@pytest.mark.ac("009:AC-3")
@pytest.mark.parametrize(
    "question", ["¿cuál es la capital de Francia?", "what's the weather like?", "hola que tal"]
)
def test_an_unrelated_question_is_below_the_threshold(
    retriever: FaqRetriever, question: str
) -> None:
    trace, grounding = answer_question(
        retriever, question, country=Country.ES, register=Register.es_ES, language=Language.es
    )
    assert grounding is None
    assert trace.outcome == "unanswered"
    assert all(hit.score < retriever.base.retrieval.min_score for hit in trace.hits)


def test_hits_are_top_k_with_scores_best_first(retriever: FaqRetriever) -> None:
    hits = retriever.search("¿cuánto pagan la hora?", Country.ES)
    assert len(hits) == retriever.base.retrieval.top_k
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_close_seconds_are_kept_for_the_model(retriever: FaqRetriever) -> None:
    """A question about two topics gives the model both approved texts."""
    trace, grounding = answer_question(
        retriever,
        "¿tengo seguro? ¿y uniforme?",
        country=Country.ES,
        register=Register.es_ES,
        language=Language.es,
    )
    assert grounding is not None
    assert set(trace.entry_ids) == {"insurance", "uniform-equipment"}
    assert len(grounding.approved) == 2
