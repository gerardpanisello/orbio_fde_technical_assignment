"""Outbound payload shapes and WhatsApp's limits (spec 016 FR-5, AC-5)."""

import pytest

from sazon_screening.llm.phrasing.quick_replies import QuickReply
from sazon_screening.whatsapp.client import as_json
from sazon_screening.whatsapp.payloads import (
    BUTTON_BODY_MAX,
    BUTTON_TITLE_MAX,
    LIST_BUTTON_MAX,
    ROW_DESCRIPTION_MAX,
    ROW_TITLE_MAX,
    TEXT_MAX,
    buttons_message,
    list_message,
    outbound_payload,
    read_receipt,
    template_message,
    text_message,
    truncate,
)

TO = "34600000001"


def options(*labels: str) -> list[QuickReply]:
    return [QuickReply(id=f"opt_{n}", label=label) for n, label in enumerate(labels)]


def test_text_message_has_previews_off() -> None:
    assert as_json(text_message(TO, "Hola")) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TO,
        "type": "text",
        "text": {"body": "Hola", "preview_url": False},
    }


def test_text_body_is_capped() -> None:
    body = as_json(text_message(TO, "x" * (TEXT_MAX + 50)))["text"]["body"]
    assert len(body) == TEXT_MAX
    assert body.endswith("…")


@pytest.mark.ac("016:AC-5")
def test_up_to_three_options_are_reply_buttons() -> None:
    payload = as_json(outbound_payload(TO, "¿Empezamos?", options("Sí", "No"), list_button="Ver"))
    assert payload["type"] == "interactive"
    interactive = payload["interactive"]
    assert interactive["type"] == "button"
    assert interactive["body"] == {"text": "¿Empezamos?"}
    assert interactive["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "opt_0", "title": "Sí"}},
        {"type": "reply", "reply": {"id": "opt_1", "title": "No"}},
    ]


@pytest.mark.ac("016:AC-5")
def test_more_than_three_options_are_a_list() -> None:
    labels = ("Mañanas", "Tardes", "Noches", "Fines de semana")
    payload = as_json(
        outbound_payload(TO, "¿Cuándo?", options(*labels), list_button="Ver opciones")
    )
    interactive = payload["interactive"]
    assert interactive["type"] == "list"
    assert interactive["action"]["button"] == "Ver opciones"
    rows = interactive["action"]["sections"][0]["rows"]
    assert [row["title"] for row in rows] == list(labels)
    assert all("description" not in row for row in rows)  # nothing was cut


@pytest.mark.ac("016:AC-5")
def test_titles_are_truncated_within_limits() -> None:
    long = "Lunes 13 de octubre a las 10:00 en la oficina de Chamberí"
    buttons = as_json(buttons_message(TO, "¿Cuál?", options(long, "Ninguna")))
    title = buttons["interactive"]["action"]["buttons"][0]["reply"]["title"]
    assert len(title) <= BUTTON_TITLE_MAX
    assert title.endswith("…")
    assert title.startswith("Lunes 13")

    listed = as_json(list_message(TO, "¿Cuál?", options(*[long] * 5), "x" * 40))
    row = listed["interactive"]["action"]["sections"][0]["rows"][0]
    assert len(row["title"]) <= ROW_TITLE_MAX
    assert len(row["description"]) <= ROW_DESCRIPTION_MAX  # the whole label, as far as it fits
    assert row["description"].startswith("Lunes 13 de octubre a las 10:00")
    assert len(listed["interactive"]["action"]["button"]) <= LIST_BUTTON_MAX


@pytest.mark.ac("016:AC-5")
def test_buttons_whose_titles_collide_after_truncation_become_a_list() -> None:
    same_start = options("Martes 14 de octubre a las 10:00", "Martes 14 de octubre a las 12:00")
    payload = as_json(outbound_payload(TO, "¿Cuál?", same_start, list_button="Ver"))
    assert payload["interactive"]["type"] == "list"


def test_a_body_too_long_for_buttons_becomes_a_list() -> None:
    payload = as_json(
        outbound_payload(TO, "a" * (BUTTON_BODY_MAX + 1), options("Sí", "No"), list_button="Ver")
    )
    assert payload["interactive"]["type"] == "list"


def test_more_than_ten_options_are_numbered_in_the_text() -> None:
    labels = [f"Opción {n}" for n in range(1, 13)]
    payload = as_json(outbound_payload(TO, "Elige:", options(*labels), list_button="Ver"))
    assert payload["type"] == "text"
    assert "1. Opción 1" in payload["text"]["body"]
    assert "12. Opción 12" in payload["text"]["body"]


def test_builders_reject_counts_whatsapp_rejects() -> None:
    with pytest.raises(ValueError, match="1 to 3"):
        buttons_message(TO, "x", options("a", "b", "c", "d"))
    with pytest.raises(ValueError, match="1 to 10"):
        list_message(TO, "x", options(*"abcdefghijk"), "Ver")


def test_template_and_read_receipt_shapes() -> None:
    assert as_json(template_message(TO, "hello_world", "en_US")) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": TO,
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }
    assert as_json(read_receipt("wamid.1")) == {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": "wamid.1",
        "typing_indicator": {"type": "text"},
    }
    assert "typing_indicator" not in as_json(read_receipt("wamid.1", typing=False))


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("Sí", 20, "Sí"),
        ("  Tiempo   completo ", 20, "Tiempo completo"),
        ("Fines de semana y festivos", 20, "Fines de semana y…"),
        ("Supercalifragilisticoespialidoso", 20, "Supercalifragilisti…"),
    ],
)
def test_truncate(text: str, limit: int, expected: str) -> None:
    assert truncate(text, limit) == expected
    assert len(truncate(text, limit)) <= limit
