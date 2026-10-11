"""T27: whole conversations through the offline (rules) agent, network blocked (AC-21)."""

import pytest

from sazon_screening.vocab import Language, Status
from tests.llm.chat import SPANISH_SCRIPT, Chat


@pytest.mark.anyio
@pytest.mark.ac("003:AC-21")
async def test_spanish_conversation_from_greeting_to_interview(chat: Chat) -> None:
    greeting = await chat.start()
    assert greeting.reply is not None
    assert "Sofi" in greeting.reply.text
    for text in SPANISH_SCRIPT:
        await chat.say(text)
    assert chat.state is not None
    assert chat.state.status is Status.interview_scheduled
    assert chat.state.selected_slot_id == "s1"
    location = chat.state.profile.location.value
    assert location is not None
    assert location.zone == "cdmx-coyoacan"
    replies = [r.reply for r in chat.results if r.reply is not None]
    assert all(reply.register == "es-MX" for reply in replies[1:])  # Mexican phone and city
    assert "licencia de manejo" in " ".join(reply.text for reply in replies)


@pytest.mark.anyio
@pytest.mark.ac("003:AC-21")
async def test_english_conversation_switching_to_spanish(chat: Chat) -> None:
    await chat.start()
    english = await chat.say("Yes, I agree")
    assert english.reply is not None
    assert english.reply.language is Language.en
    await chat.say("My name is John Smith")
    await chat.say("I'm 30 years old")
    switched = await chat.say("tengo moto")
    assert switched.reply is not None
    assert switched.reply.language is Language.es
    after = await chat.say("sí")
    assert after.reply is not None
    assert after.reply.language is Language.es
    assert chat.state is not None
    assert chat.state.status is Status.in_progress
