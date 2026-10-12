"""Candidate chat (FR-1..4): start a conversation, send a message, reload the transcript."""

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.deps import ServiceDep, SessionDep
from sazon_screening.api.schemas import (
    ConversationOut,
    CreateConversationIn,
    MessageOut,
    SendMessageIn,
    TurnOut,
)
from sazon_screening.api.service import ConversationNotFound
from sazon_screening.vocab import Language, Status

router = APIRouter(prefix="/api/conversations", tags=["candidate chat"])


@router.post("", status_code=201)
async def create_conversation(
    service: ServiceDep, session: SessionDep, body: CreateConversationIn | None = None
) -> ConversationOut:
    body = body or CreateConversationIn()
    conversation_id = await service.start_conversation(body.language, body.country_hint)
    return await conversation_out(session, conversation_id)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str, body: SendMessageIn, service: ServiceDep, background: BackgroundTasks
) -> TurnOut:
    outcome = await service.send_message(conversation_id, body.text)
    if outcome.result.summary_due:  # FR-14: after the reply, never on the candidate's clock
        background.add_task(service.write_summary, conversation_id)
    return TurnOut.of(outcome)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, session: SessionDep) -> ConversationOut:
    return await conversation_out(session, conversation_id)


async def conversation_out(session: AsyncSession, conversation_id: str) -> ConversationOut:
    row = await repo.get_conversation(session, conversation_id)
    if row is None:
        raise ConversationNotFound(conversation_id)
    messages = await repo.list_messages(session, conversation_id)
    return ConversationOut(
        id=row.id,
        status=Status(row.status),
        language=Language(row.language),
        messages=[MessageOut.of(m) for m in messages],
    )
