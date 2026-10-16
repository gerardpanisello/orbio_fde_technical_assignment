"""Spec 010 T4: the .ics endpoint (AC-5), the booking in the chat API, the WhatsApp link."""

import pytest
from httpx import AsyncClient

from sazon_screening.api.service import ScreeningService
from sazon_screening.vocab import Status
from tests.api.conftest import HAPPY_PATH
from tests.scheduling.test_ics import parse, unescape

pytestmark = pytest.mark.anyio


async def chat(client: AsyncClient, messages: list[str], language: str = "es") -> str:
    created = await client.post("/api/conversations", json={"language": language})
    conversation_id: str = created.json()["id"]
    for text in messages:
        response = await client.post(
            f"/api/conversations/{conversation_id}/messages", json={"text": text}
        )
        assert response.status_code == 200
    return conversation_id


@pytest.mark.ac("010:AC-5")
async def test_booked_conversation_serves_a_valid_invite(client: AsyncClient) -> None:
    conversation_id = await chat(client, HAPPY_PATH)
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    booking = conversation["booking"]
    assert booking["slot_id"] == "madrid:2026-10-13T10:00"
    assert booking["local_start"] == "2026-10-13T10:00"
    assert booking["timezone"] == "Europe/Madrid"
    assert booking["status"] == "booked"
    assert booking["ics_url"] == f"/api/interviews/{conversation_id}.ics"

    response = await client.get(booking["ics_url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "attachment" in response.headers["content-disposition"]
    event = dict(parse(response.text))
    assert event["DTSTART"] == "20261013T080000Z"  # 10:00 in Madrid (CEST)
    assert event["DTEND"] == "20261013T083000Z"
    assert event["UID"] == f"interview-{booking['id']}@gruposazon.example"
    assert unescape(event["SUMMARY"]) == "Entrevista Grupo Sazón — repartidor/a"
    assert unescape(event["LOCATION"]) == booking["place"]


@pytest.mark.ac("010:AC-5")
async def test_the_uid_is_stable_for_one_booking(client: AsyncClient) -> None:
    conversation_id = await chat(client, HAPPY_PATH)
    first = (await client.get(f"/api/interviews/{conversation_id}.ics")).text
    second = (await client.get(f"/api/interviews/{conversation_id}.ics")).text
    assert first == second


async def test_english_candidates_get_an_english_invite(client: AsyncClient) -> None:
    english = [
        "Yes, I agree",
        "My name is Emma Wilson",
        "I'm 30 years old",
        "motorbike",
        "yes",
        "I live in Coyoacán, CDMX",
        "full time",
        "mornings",
        "4 years with Uber Eats",
        "in 1 week",
        "yes",
        "1",
    ]
    conversation_id = await chat(client, english, language="en")
    event = dict(parse((await client.get(f"/api/interviews/{conversation_id}.ics")).text))
    assert unescape(event["SUMMARY"]) == "Grupo Sazón interview — delivery driver"
    assert event["DTSTART"] == "20261013T160000Z"  # 10:00 in Mexico City (UTC-6)


async def test_no_booking_is_a_404(client: AsyncClient) -> None:
    conversation_id = await chat(client, HAPPY_PATH[:3])
    assert (await client.get(f"/api/interviews/{conversation_id}.ics")).status_code == 404
    assert (await client.get(f"/api/conversations/{conversation_id}")).json()["booking"] is None
    assert (await client.get("/api/interviews/nope.ics")).status_code == 404


@pytest.mark.parametrize(
    ("channel", "base_url", "linked"),
    [
        ("whatsapp", "https://sazon.example/", True),
        ("web", "https://sazon.example", False),  # the web chat shows its own button
        ("whatsapp", None, False),  # not reachable from outside: no link
    ],
)
async def test_the_confirmation_links_the_invite_on_whatsapp_only(
    service: ScreeningService, channel: str, base_url: str | None, linked: bool
) -> None:
    configured = ScreeningService(
        service._agent,
        service._sessions,
        service.slots,
        service._clock,
        public_base_url=base_url,
    )
    conversation_id = await configured.start_conversation(channel=channel)  # type: ignore[arg-type]
    for text in HAPPY_PATH:
        outcome = await configured.send_message(conversation_id, text)
    assert outcome.status is Status.interview_scheduled
    reply = outcome.result.reply
    assert reply is not None
    link = f"https://sazon.example/api/interviews/{conversation_id}.ics"
    assert (link in reply.text) is linked
    if linked:
        assert reply.text.endswith(f"Añádela a tu calendario: {link}")
