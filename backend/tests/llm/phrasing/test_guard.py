"""T19: deterministic checks on every phrased reply before it is sent (FR-15, ADR 0006)."""

import pytest

from sazon_screening.engine import (
    AnswerFaq,
    AskField,
    ClosedAck,
    CloseDisqualified,
    Preface,
    PrimaryAction,
    ShowRecap,
)
from sazon_screening.engine.state import Profile
from sazon_screening.llm.phrasing.guard import Violation, check
from sazon_screening.llm.settings import LengthCaps
from sazon_screening.vocab import DisqualificationReason, FieldName
from tests.llm.builders import action, ctx

CAPS = LengthCaps()
ASK_AGE = AskField(field=FieldName.age)


def violations(
    text: str,
    primary: PrimaryAction = ASK_AGE,
    *,
    prefaces: tuple[Preface, ...] = (),
    faq_answer: str | None = None,
) -> list[Violation]:
    return check(text, action(primary, *prefaces), ctx(faq_answer=faq_answer), CAPS)


def test_a_good_reply_passes() -> None:
    assert violations("¡Genial, Ana! ¿Cuántos años tienes? 🙂") == []


def test_empty() -> None:
    assert Violation.empty in violations("   ")


@pytest.mark.ac("003:AC-12")
def test_too_long() -> None:
    text = "¿Cuántos años tienes?" + "a" * 280
    assert len(text) == 301
    assert Violation.too_long in violations(text)


def test_recap_may_use_the_long_cap() -> None:
    text = "Repasemos:\n" + "x" * 570 + "\n¿Está todo bien?"
    assert len(text) <= 600
    assert violations(text, ShowRecap(profile=Profile())) == []


def test_faq_answer_may_use_the_long_cap() -> None:
    faq = "Pagamos por pedido. " * 15
    text = f"{faq}¿Cuántos años tienes?"
    assert violations(text, prefaces=(AnswerFaq(),), faq_answer=faq) == []


@pytest.mark.ac("003:AC-12")
def test_two_questions() -> None:
    assert Violation.question_count in violations("¿Cómo te llamas? ¿Y cuántos años tienes?")


def test_a_question_in_a_close() -> None:
    assert Violation.question_count in violations("Gracias. ¿Algo más?", ClosedAck())


def test_an_ask_without_a_question() -> None:
    assert Violation.question_count in violations("Dime tu edad.")


@pytest.mark.ac("003:AC-12")
@pytest.mark.parametrize(
    "text",
    [
        "Se cobra 15 €/hora. ¿Cuántos años tienes?",
        "Son $200 pesos. ¿Cuántos años tienes?",
        "Unos 20 euros. ¿Cuántos años tienes?",
        "Ganas 12 por hora. ¿Cuántos años tienes?",
    ],
)
def test_pay_or_currency(text: str) -> None:
    assert Violation.pay_or_currency in violations(text)


def test_pay_from_the_approved_faq_answer_is_allowed() -> None:
    faq = "El pago es de 3 € por pedido."
    text = f"{faq} ¿Cuántos años tienes?"
    assert violations(text, prefaces=(AnswerFaq(),), faq_answer=faq) == []


def test_two_emoji() -> None:
    assert Violation.emoji in violations("¡Genial! 🎉 ¿Cuántos años tienes? 🙂")


def test_any_emoji_in_a_disqualification() -> None:
    close = CloseDisqualified(reason=DisqualificationReason.no_license)
    assert Violation.emoji in violations("Lo siento, no podemos seguir 🙏", close)


@pytest.mark.ac("003:AC-12")
def test_english_reply_for_a_spanish_action() -> None:
    assert Violation.wrong_language in violations("Great, thanks! How old are you?")


def test_short_spanish_with_an_english_brand_is_fine() -> None:
    assert violations("¡Perfecto! ¿Cuántos años llevas con Uber Eats?") == []


def test_language_check_can_be_switched_off() -> None:
    act = action(AskField(field=FieldName.age))
    english = "Great, thanks! How old are you?"
    assert check(english, act, ctx(), CAPS, language_check=False) == []


@pytest.mark.parametrize(
    "text",
    [
        "¡Hola! Soy Sofi, de Grupo Sazón. Vamos allá: ¿cómo te llamas?",
        "¡Buenas tardes, Pedro! ¿Cuántos años tienes?",
        "Buenos días, Ana. ¿Cuántos años tienes?",
        "Hello again! How old are you?",
        "Genial, ya sabes que soy Sofi. ¿Cuántos años tienes?",
    ],
)
def test_greeting_again_after_the_greeting(text: str) -> None:
    """Found by the sample conversations: Sofi said hello again mid-conversation, and read
    the shift answer "tardes" as a greeting ("¡Buenas tardes, Pedro!")."""
    assert Violation.repeated_greeting in violations(text)


@pytest.mark.parametrize(
    "text",
    [
        "¡Genial, Ana! ¿Cuántos años tienes?",
        "Perfecto, tardes anotadas. ¿Cuántos años tienes?",
        "¡Buenas noticias, Ana! ¿Cuántos años tienes?",
        "Thanks, Hilda! How old are you?",
    ],
)
def test_no_greeting_passes(text: str) -> None:
    assert Violation.repeated_greeting not in violations(text)


def test_the_greeting_itself_may_say_hello() -> None:
    text = "¡Hola! Soy Sofi, la asistente automática. ¿Aceptas?"
    consent = AskField(field=FieldName.consent)
    found = check(text, action(consent), ctx(is_greeting=True), CAPS)
    assert Violation.repeated_greeting not in found


@pytest.mark.parametrize(
    "text",
    ["¡Encantado, Ana! ¿Cuántos años tienes?", "Estoy contento de ayudarte. ¿Cuántos años tienes?"],
)
def test_sofi_speaks_of_herself_in_the_feminine(text: str) -> None:
    """Eval 2026-10-12: "¡Encantado!" appeared; Sofi is female."""
    assert Violation.masculine_form in violations(text)


@pytest.mark.parametrize(
    "text", ["¡Encantada, Ana! ¿Cuántos años tienes?", "Delighted! How old are you?"]
)
def test_feminine_or_english_passes(text: str) -> None:
    assert Violation.masculine_form not in violations(text)


RECENT = ("¡Gracias, Ana! ¿Cuántos años tienes?",)


def test_the_name_twice_in_a_row_is_rejected() -> None:
    """Eval 2026-10-12: the name in every message (tone 3.1/5)."""
    found = check(
        "¡Genial, Ana! ¿Con qué vehículo repartirías?",
        action(ASK_AGE),
        ctx(first_name="Ana", recent_agent_messages=RECENT),
        CAPS,
    )
    assert Violation.name_overused in found


def test_the_name_after_a_gap_passes() -> None:
    recent = ("¿Cuántos años tienes?", "Vale. ¿Con qué vehículo repartirías?")
    context = ctx(first_name="Ana", recent_agent_messages=recent)
    assert check("¡Gracias, Ana! ¿Cuántos años tienes?", action(ASK_AGE), context, CAPS) == []


def test_name_inside_another_word_is_not_the_name() -> None:
    context = ctx(first_name="Ana", recent_agent_messages=RECENT)
    text = "Vale. ¿Tienes alguna semana libre?"  # "semana" contains "ana"
    assert Violation.name_overused not in check(text, action(ASK_AGE), context, CAPS)


def test_the_name_inside_the_reference_message_is_allowed() -> None:
    """The recap's "Nombre completo: Ana López" line is not the name used as address."""
    context = ctx(first_name="Ana", recent_agent_messages=RECENT)
    recap = "Repasemos tus datos:\n• Nombre completo: Ana López\n¿Está todo bien?"
    act = action(ShowRecap(profile=Profile()))
    assert Violation.name_overused not in check(recap, act, context, CAPS, reference=recap)
    again = "Vale, Ana. " + recap
    assert Violation.name_overused in check(again, act, context, CAPS, reference=recap)
