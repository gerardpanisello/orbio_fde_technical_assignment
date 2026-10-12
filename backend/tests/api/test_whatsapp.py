"""The WhatsApp channel end to end (spec 016 AC-1..AC-9), with a fake Graph API client.

The webhook payloads are the shapes Meta sends; signatures are real HMACs with a test
secret. Nothing leaves the machine: the fake client records what would be posted.
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import timedelta
from itertools import count
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import select

from sazon_screening.api.app import create_app
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import Conversation, DoNotContact, Message
from sazon_screening.api.service import Outbound, ScreeningService
from sazon_screening.api.settings import AppSettings
from sazon_screening.llm.phrasing.phraser import OutboundMessage
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.reengagement.scheduler import ReengagementScheduler
from sazon_screening.vocab import Language, Register, Status
from sazon_screening.whatsapp.channel import WhatsAppChannel
from sazon_screening.whatsapp.client import FakeWhatsAppClient
from sazon_screening.whatsapp.inbound import Inbound, sign
from sazon_screening.whatsapp.phone import phone_hash
from sazon_screening.whatsapp.settings import WhatsAppSettings, load_whatsapp_config
from tests.api.conftest import START, TickingClock
from tests.paths import SHIPPED_CONFIG_DIR

SECRET = "test-app-secret"
VERIFY = "test-verify-token"
ES_PHONE = "34600111222"
MX_PHONE = "5215512345678"
_ids = count(1)


def wa_settings() -> WhatsAppSettings:
    return WhatsAppSettings(
        enabled=True,
        token=SecretStr("test-token"),
        phone_number_id="999",
        verify_token=SecretStr(VERIFY),
        app_secret=SecretStr(SECRET),
    )


@pytest.fixture
def graph() -> FakeWhatsAppClient:
    return FakeWhatsAppClient()


@pytest.fixture
async def wa_app(
    settings: AppSettings, agent: ScreeningAgent, clock: TickingClock, graph: FakeWhatsAppClient
) -> AsyncIterator[FastAPI]:
    enabled = settings.model_copy(update={"whatsapp": wa_settings()})
    app = create_app(enabled, agent=agent, clock=clock, whatsapp_client=graph)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def wa(wa_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=wa_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def wa_sessions(wa_app: FastAPI) -> Sessions:
    sessions: Sessions = wa_app.state.sessions
    return sessions


# --- webhook payloads ----------------------------------------------------------------------


def message(phone: str, kind: str = "text", **part: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"from": phone, "id": f"wamid.in.{next(_ids)}", "type": kind}
    body.update(part)
    return body


def text(phone: str, body: str) -> dict[str, Any]:
    return message(phone, "text", text={"body": body})


def button(phone: str, reply_id: str, title: str) -> dict[str, Any]:
    return message(
        phone,
        "interactive",
        interactive={"type": "button_reply", "button_reply": {"id": reply_id, "title": title}},
    )


def webhook(*messages: dict[str, Any]) -> bytes:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "999",
                            },
                            "contacts": [
                                {"wa_id": m["from"], "profile": {"name": "X"}} for m in messages
                            ],
                            "messages": list(messages),
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode()


async def post(client: AsyncClient, raw: bytes, *, signature: str | None = None) -> Response:
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature or sign(raw, SECRET),
    }
    return await client.post("/api/whatsapp/webhook", content=raw, headers=headers)


async def say(client: AsyncClient, *messages: dict[str, Any]) -> Response:
    response = await post(client, webhook(*messages))
    assert response.status_code == 200, response.text
    return response


async def conversation_of(sessions: Sessions, phone: str) -> Conversation:
    async with sessions() as session:
        return (
            await session.scalars(select(Conversation).where(Conversation.phone == phone))
        ).one()


async def transcript(sessions: Sessions, conversation_id: str) -> list[Message]:
    async with sessions() as session:
        query = (
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
        return list((await session.scalars(query)).all())


def last_body(graph: FakeWhatsAppClient) -> str:
    sent = graph.messages()[-1]
    if sent["type"] == "text":
        return str(sent["text"]["body"])
    return str(sent["interactive"]["body"]["text"])


# --- AC-1 verification ---------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-1")
async def test_verification_echoes_the_challenge_for_the_right_token(wa: AsyncClient) -> None:
    params = {"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"}
    response = await wa.get("/api/whatsapp/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "1158201444"


@pytest.mark.anyio
@pytest.mark.ac("016:AC-1")
@pytest.mark.parametrize(
    "params",
    [
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
        {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY, "hub.challenge": "1"},
        {},
    ],
)
async def test_verification_is_refused_otherwise(wa: AsyncClient, params: dict[str, str]) -> None:
    assert (await wa.get("/api/whatsapp/webhook", params=params)).status_code == 403


@pytest.mark.anyio
async def test_the_webhook_is_off_by_default(client: AsyncClient) -> None:
    """WHATSAPP_ENABLED=false (the default): the app runs, the webhook does not exist."""
    params = {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}
    assert (await client.get("/api/whatsapp/webhook", params=params)).status_code == 404
    raw = webhook(text(ES_PHONE, "Hola"))
    assert (await post(client, raw)).status_code == 404


# --- AC-2 signature and idempotency --------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-2")
async def test_an_invalid_signature_is_rejected(
    wa: AsyncClient, graph: FakeWhatsAppClient, wa_sessions: Sessions
) -> None:
    raw = webhook(text(ES_PHONE, "Hola"))
    assert (await post(wa, raw, signature=sign(raw, "another-secret"))).status_code == 401
    assert (await post(wa, raw, signature="sha256=deadbeef")).status_code == 401
    unsigned = await wa.post("/api/whatsapp/webhook", content=raw)
    assert unsigned.status_code == 401
    tampered = raw.replace(b"Hola", b"Hole")
    assert (await post(wa, tampered, signature=sign(raw, SECRET))).status_code == 401
    assert graph.sent == []
    async with wa_sessions() as session:
        assert (await session.scalars(select(Conversation))).all() == []


@pytest.mark.anyio
@pytest.mark.ac("016:AC-2")
async def test_a_message_delivered_twice_is_processed_once(
    wa: AsyncClient, graph: FakeWhatsAppClient, wa_sessions: Sessions
) -> None:
    raw = webhook(text(ES_PHONE, "Hola"))
    first = await post(wa, raw)
    again = await post(wa, raw)
    assert first.status_code == again.status_code == 200
    assert first.json() == {"received": 1, "accepted": 1}
    assert again.json() == {"received": 1, "accepted": 0}
    assert len(graph.messages()) == 1  # one greeting
    async with wa_sessions() as session:
        assert len((await session.scalars(select(Conversation))).all()) == 1


@pytest.mark.anyio
async def test_status_updates_and_unknown_payloads_get_a_200(wa: AsyncClient) -> None:
    statuses = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {"statuses": [{"id": "x"}]}}]}],
    }
    raw = json.dumps(statuses).encode()
    assert (await post(wa, raw)).json() == {"received": 0, "accepted": 0}
    junk = b'{"entry": "not a list"}'
    assert (await post(wa, junk)).status_code == 200


# --- AC-3 a new number ---------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-3")
async def test_a_new_number_starts_a_whatsapp_conversation_with_the_greeting(
    wa: AsyncClient, graph: FakeWhatsAppClient, wa_sessions: Sessions
) -> None:
    inbound = text(ES_PHONE, "Hola")
    await say(wa, inbound)
    row = await conversation_of(wa_sessions, ES_PHONE)
    assert row.channel == "whatsapp"
    assert row.country == "ES"  # country_hint from +34
    assert row.state_json["country_hint"] == "ES"
    assert row.last_candidate_at is not None  # their "Hola" opened the 24 h window
    messages = await transcript(wa_sessions, row.id)
    assert next((m.role, m.text) for m in messages) == ("candidate", "Hola")
    assert graph.receipts() == [
        {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": inbound["id"],
            "typing_indicator": {"type": "text"},
        }
    ]
    greeting = graph.messages()[0]
    assert greeting["to"] == ES_PHONE
    assert greeting["interactive"]["type"] == "button"
    titles = [b["reply"]["title"] for b in greeting["interactive"]["action"]["buttons"]]
    assert titles == ["Sí", "No"]
    assert greeting["interactive"]["body"]["text"] == messages[1].text


@pytest.mark.anyio
@pytest.mark.ac("016:AC-3")
async def test_a_mexican_number_gets_the_mx_hint_and_its_next_message_continues(
    wa: AsyncClient, wa_sessions: Sessions
) -> None:
    await say(wa, text(MX_PHONE, "Buenas"))
    await say(wa, text(MX_PHONE, "sí"))
    row = await conversation_of(wa_sessions, MX_PHONE)  # .one(): still one conversation
    assert row.country == "MX"
    assert row.stage != "consent"


# --- AC-4 buttons --------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-4")
async def test_a_button_reply_advances_like_typing_its_label(
    wa: AsyncClient, client: AsyncClient, graph: FakeWhatsAppClient, wa_sessions: Sessions
) -> None:
    await say(wa, text(ES_PHONE, "Hola"))
    yes = graph.messages()[0]["interactive"]["action"]["buttons"][0]["reply"]
    await say(wa, button(ES_PHONE, yes["id"], yes["title"]))
    by_button = await conversation_of(wa_sessions, ES_PHONE)

    web = (await client.post("/api/conversations", json={"country_hint": "ES"})).json()
    typed = await client.post(f"/api/conversations/{web['id']}/messages", json={"text": "Sí"})

    messages = await transcript(wa_sessions, by_button.id)
    assert messages[-2].text == "Sí"  # the label went to the pipeline, as typed on the web
    async with wa_sessions() as session:  # both apps share the test database
        by_typing = await session.get(Conversation, web["id"])
    assert by_typing is not None
    assert by_button.stage == by_typing.stage != "consent"
    assert last_body(graph) == typed.json()["reply"]["text"]


@pytest.mark.anyio
@pytest.mark.ac("016:AC-4")
async def test_a_shortened_title_still_sends_the_full_label(
    service: ScreeningService, graph: FakeWhatsAppClient
) -> None:
    channel = WhatsAppChannel(service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR))
    await channel.handle(Inbound("wamid.1", ES_PHONE, "text", "Hola", "text"))
    cid = await service.conversation_for_phone(ES_PHONE)
    assert cid is not None
    label = await service.quick_reply_label(cid, "yes")
    assert label == "Sí"
    await channel.handle(Inbound("wamid.2", ES_PHONE, "choice", "S…", "interactive", "yes"))
    messages = await service_transcript(service, cid)
    assert messages[2] == "Sí"


async def service_transcript(service: ScreeningService, cid: str) -> list[str]:
    async with service._sessions() as session:
        query = select(Message.text).where(Message.conversation_id == cid).order_by(Message.id)
        return list((await session.scalars(query)).all())


# --- AC-5 lists ----------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-5")
async def test_a_question_with_more_than_three_options_goes_as_a_list(
    service: ScreeningService, graph: FakeWhatsAppClient
) -> None:
    channel = WhatsAppChannel(service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR))
    replies = [
        "Hola",
        "sí",
        "Me llamo Lucía Martín",
        "tengo 27",
        "moto",
        "sí",
        "vivo en Chamberí, Madrid",
        "tiempo completo",
    ]
    seen: list[dict[str, Any]] = []
    for n, body in enumerate(replies):
        await channel.handle(Inbound(f"wamid.l{n}", ES_PHONE, "text", body, "text"))
        seen.append(graph.messages()[-1])
    lists = [m for m in seen if m["type"] == "interactive" and m["interactive"]["type"] == "list"]
    assert lists, [m.get("interactive", {}).get("type", m["type"]) for m in seen]
    for listed in lists:
        rows = listed["interactive"]["action"]["sections"][0]["rows"]
        assert 3 < len(rows) <= 10
        assert all(len(row["title"]) <= 24 for row in rows)
        assert listed["interactive"]["action"]["button"] == "Ver opciones"
    for sent in seen:
        if sent["type"] == "interactive" and sent["interactive"]["type"] == "button":
            buttons = sent["interactive"]["action"]["buttons"]
            assert len(buttons) <= 3
            assert all(len(b["reply"]["title"]) <= 20 for b in buttons)


# --- AC-6 media ----------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-6")
async def test_an_audio_message_gets_the_media_reply_and_changes_nothing(
    wa: AsyncClient, graph: FakeWhatsAppClient, wa_sessions: Sessions
) -> None:
    await say(wa, text(ES_PHONE, "Hola"))
    before = await conversation_of(wa_sessions, ES_PHONE)
    voice_note = message(ES_PHONE, "audio", audio={"id": "media-1", "mime_type": "audio/ogg"})
    await say(wa, voice_note)
    after = await conversation_of(wa_sessions, ES_PHONE)
    assert after.state_json == before.state_json
    assert "audios" in last_body(graph)  # media_not_supported: "¿Me lo escribes?"
    messages = await transcript(wa_sessions, after.id)
    assert messages[-2].text == "[audio]"


@pytest.mark.anyio
async def test_other_message_types_are_ignored(
    wa: AsyncClient,
    graph: FakeWhatsAppClient,
    wa_sessions: Sessions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="sazon_screening.whatsapp")
    reaction = message(ES_PHONE, "reaction", reaction={"message_id": "x", "emoji": "👍"})
    await say(wa, reaction)
    assert graph.sent == []
    async with wa_sessions() as session:
        assert (await session.scalars(select(Conversation))).all() == []
    assert "reaction message ignored" in caplog.text


# --- AC-7 opt-out --------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-7")
async def test_opt_out_adds_the_number_to_do_not_contact_and_erases_it(
    wa: AsyncClient,
    wa_app: FastAPI,
    graph: FakeWhatsAppClient,
    wa_sessions: Sessions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)  # (DEBUG: aiosqlite echoes SQL parameters)
    await say(wa, text(ES_PHONE, "Hola"))
    await say(wa, text(ES_PHONE, "sí"))
    await say(wa, text(ES_PHONE, "Me llamo Iván Mora"))
    row = await conversation_of(wa_sessions, ES_PHONE)
    await say(wa, text(ES_PHONE, "no me interesa, dame de baja"))
    sent_at_opt_out = len(graph.messages())

    async with wa_sessions() as session:
        stored = await session.get(Conversation, row.id)
        assert stored is not None
        assert stored.status == Status.opted_out
        assert stored.phone is None  # erased with the rest of the PII
        assert await session.get(DoNotContact, phone_hash(ES_PHONE)) is not None

    # Later messages from the number are dropped; nothing is sent to it again.
    await say(wa, text(ES_PHONE, "hola otra vez"))
    service: ScreeningService = wa_app.state.service
    outcome = await service.reengage(row.id, force=True)
    assert outcome.action == "none"
    assert len(graph.messages()) == sent_at_opt_out

    # The number is nowhere: record, transcript, dashboard, export, logs.
    async with wa_sessions() as session:
        stored = await session.get(Conversation, row.id)
        assert stored is not None
        everything = json.dumps([stored.state_json, stored.record_json, stored.flags_json])
    pages = [
        (await wa.get("/api/candidates")).text,
        (await wa.get(f"/api/candidates/{row.id}")).text,
        (await wa.get("/api/candidates/export.csv")).text,
        (await wa.get(f"/api/conversations/{row.id}")).text,
        (await wa.get("/api/analytics")).text,
    ]
    for blob in [everything, *pages, caplog.text]:
        assert ES_PHONE not in blob
    assert all(ES_PHONE not in m.text for m in await transcript(wa_sessions, row.id))


@pytest.mark.anyio
@pytest.mark.ac("016:AC-7")
async def test_follow_ups_to_a_do_not_contact_number_are_suppressed(
    service: ScreeningService, graph: FakeWhatsAppClient
) -> None:
    """Belt and braces: even a conversation still in progress on a number that opted out
    elsewhere gets no reminder."""
    channel = WhatsAppChannel(service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR))
    service.register_delivery("whatsapp", channel)
    cid, _ = await service.start_whatsapp(ES_PHONE, "Hola", at=START)
    async with service._sessions.begin() as session:
        session.add(DoNotContact(phone_hash=phone_hash(ES_PHONE), created_at=START))
    outcome = await service.reengage(cid, force=True, at=START + timedelta(hours=2))
    assert outcome.action == "follow_up"  # stored for the dashboard...
    assert graph.messages() == []  # ...but never sent


# --- AC-8 re-engagement --------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("016:AC-8")
async def test_reminders_go_through_whatsapp_and_as_a_template_outside_24h(
    service: ScreeningService, graph: FakeWhatsAppClient, caplog: pytest.LogCaptureFixture
) -> None:
    channel = WhatsAppChannel(service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR))
    service.register_delivery("whatsapp", channel)
    cid, _ = await service.start_whatsapp(ES_PHONE, "Hola", at=START)
    web = await service.start_conversation(at=START)
    scheduler = ReengagementScheduler(service, tick_seconds=30)

    # Step 1 (2 h) and step 2 (23 h): inside the window -> free text, as phrased.
    for hours in (2, 23):
        done = await scheduler.tick(START + timedelta(hours=hours, minutes=1))
        assert {o.action for o in done} == {"follow_up"}
        sent = graph.messages()[-1]
        assert sent["type"] == "text"
        assert sent["to"] == ES_PHONE
    assert len(graph.messages()) == 2  # the web conversation's reminders were not pushed

    # Step 3 (72 h): the candidate's last message is 3 days old -> the template.
    caplog.set_level(logging.WARNING, logger="sazon_screening.whatsapp")
    outcome = await service.reengage(cid, force=True, at=START + timedelta(hours=72))
    assert outcome.requires_template
    assert graph.messages()[-1] == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": ES_PHONE,
        "type": "template",
        "template": {"name": "hello_world", "language": {"code": "en_US"}},
    }
    assert "placeholder template 'hello_world'" in caplog.text

    # The abandon's close is outside the window too: not sent (no template for it).
    sent = len(graph.messages())
    outcome = await service.reengage(cid, force=True, at=START + timedelta(hours=97))
    assert outcome.action == "abandon"
    assert outcome.reply is None  # the engine closes silently (no_message)
    assert len(graph.messages()) == sent
    assert web  # web reminders stay in the web chat (it polls)


@pytest.mark.anyio
@pytest.mark.ac("016:AC-8")
async def test_a_close_goes_as_text_inside_the_window_and_is_held_back_outside(
    service: ScreeningService, graph: FakeWhatsAppClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The shipped engine closes an abandoned conversation silently (`no_message`); if a
    close message ever comes, it is text inside the window and never sent outside it."""
    caplog.set_level(logging.WARNING, logger="sazon_screening.whatsapp")
    channel = WhatsAppChannel(service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR))
    cid, _ = await service.start_whatsapp(ES_PHONE, "Hola", at=START)
    reply = OutboundMessage(
        text="Cierro tu candidatura.",
        quick_replies=[],
        language=Language.es,
        register=Register.es_ES,
    )
    close = Outbound(conversation_id=cid, phone=ES_PHONE, reply=reply, kind="close")
    await channel.deliver(close)
    assert graph.messages()[-1]["text"]["body"] == "Cierro tu candidatura."
    await channel.deliver(replace(close, outside_window=True))
    assert len(graph.messages()) == 1
    assert "close not sent: outside the 24 h window" in caplog.text


# --- AC-9 failures -------------------------------------------------------------------------


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.anyio
@pytest.mark.ac("016:AC-9")
async def test_a_transient_graph_failure_is_retried(
    service: ScreeningService, graph: FakeWhatsAppClient
) -> None:
    channel = WhatsAppChannel(
        service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR), sleep=no_sleep
    )
    graph.fail_next(1)  # the read receipt fails: logged, not retried, the turn goes on
    graph.fail_next(2)  # the greeting fails twice, then goes through
    await channel.handle(Inbound("wamid.r1", ES_PHONE, "text", "Hola", "text"))
    assert len(graph.messages()) == 1
    assert graph.attempts == 4


@pytest.mark.anyio
@pytest.mark.ac("016:AC-9")
async def test_a_graph_outage_is_logged_and_the_turn_is_not_lost(
    service: ScreeningService, graph: FakeWhatsAppClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="sazon_screening.whatsapp")
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    channel = WhatsAppChannel(
        service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR), sleep=record_sleep
    )
    graph.fail_next(4)  # read receipt + 3 attempts at the greeting
    await channel.handle(Inbound("wamid.o1", ES_PHONE, "text", "Hola", "text"))
    cid = await service.conversation_for_phone(ES_PHONE)
    assert cid is not None
    assert graph.messages() == []
    assert sleeps == [0.5, 1.0]  # exponential backoff
    assert f"attempt 3/3 (conversation {cid}" in caplog.text
    assert ES_PHONE not in caplog.text

    # The turn was stored: the candidate's next message continues the same conversation.
    await channel.handle(Inbound("wamid.o2", ES_PHONE, "text", "sí", "text"))
    assert await service.conversation_for_phone(ES_PHONE) == cid
    assert len(graph.messages()) == 1
    texts = await service_transcript(service, cid)
    assert texts[0] == "Hola"
    assert texts[2] == "sí"


@pytest.mark.anyio
@pytest.mark.ac("016:AC-9")
async def test_a_permanent_error_is_not_retried(
    service: ScreeningService, graph: FakeWhatsAppClient
) -> None:
    channel = WhatsAppChannel(
        service, graph, load_whatsapp_config(SHIPPED_CONFIG_DIR), sleep=no_sleep
    )
    graph.fail_next(1)  # read receipt
    graph.fail_next(1, retryable=False, status=400)  # e.g. not in the allowed list
    await channel.handle(Inbound("wamid.p1", ES_PHONE, "text", "Hola", "text"))
    assert graph.attempts == 2


@pytest.mark.anyio
@pytest.mark.ac("016:AC-9")
async def test_the_dashboard_shows_and_filters_by_channel(
    wa: AsyncClient, wa_sessions: Sessions
) -> None:
    await say(wa, text(ES_PHONE, "Hola"))
    await wa.post("/api/conversations", json={})
    rows = (await wa.get("/api/candidates")).json()
    assert sorted(r["channel"] for r in rows) == ["web", "whatsapp"]
    only = (await wa.get("/api/candidates", params={"channel": "whatsapp"})).json()
    assert [r["channel"] for r in only] == ["whatsapp"]
    analytics = (await wa.get("/api/analytics")).json()
    assert analytics["by_channel"] == {
        "web": {"in_progress": 1},
        "whatsapp": {"in_progress": 1},
    }
    csv = (await wa.get("/api/candidates/export.csv")).text
    assert "channel" in csv.splitlines()[0]
    assert ES_PHONE not in csv


@pytest.mark.anyio
async def test_demo_seed_has_both_channels_and_no_numbers(client: AsyncClient) -> None:
    await client.post("/api/dev/seed", params={"n": 6})
    rows = (await client.get("/api/candidates")).json()
    assert {r["channel"] for r in rows} == {"web", "whatsapp"}
