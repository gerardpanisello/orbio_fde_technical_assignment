"""Meta WhatsApp Cloud API webhook (spec 016 FR-1, FR-2).

- `GET  /api/whatsapp/webhook`: Meta's one-time verification (`hub.*` query params).
- `POST /api/whatsapp/webhook`: messages. Signature checked on the raw body (401 if
  wrong), each message id claimed once in the database (redeliveries are dropped), then
  200 straight away; the turns run as background tasks.

Background tasks vs a queue: a task runs in this process right after the response, so
Meta gets its 200 in milliseconds (it retries slow or failed deliveries). But a task
lost in a crash or restart is not retried: the id is already claimed, so that message
gets no answer until the candidate writes again (at-most-once). Production: put the
inbound message on a durable queue (and claim it there), deployment design (014).

Both answer 404 while `WHATSAPP_ENABLED` is false.
"""

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from sazon_screening.api.deps import ServiceDep
from sazon_screening.whatsapp.channel import WhatsAppChannel
from sazon_screening.whatsapp.inbound import (
    SIGNATURE_HEADER,
    WebhookPayload,
    inbound_messages,
    verify_signature,
)
from sazon_screening.whatsapp.settings import WhatsAppSettings

logger = logging.getLogger("sazon_screening.whatsapp")
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def get_channel(request: Request) -> WhatsAppChannel:
    channel: WhatsAppChannel | None = getattr(request.app.state, "whatsapp", None)
    if channel is None:
        raise HTTPException(status_code=404, detail="WhatsApp channel is disabled")
    return channel


def get_whatsapp_settings(request: Request) -> WhatsAppSettings:
    settings: WhatsAppSettings = request.app.state.settings.whatsapp
    return settings


ChannelDep = Annotated[WhatsAppChannel, Depends(get_channel)]
WhatsAppSettingsDep = Annotated[WhatsAppSettings, Depends(get_whatsapp_settings)]


class WebhookAck(BaseModel):
    received: int  # messages in the payload (statuses are not counted)
    accepted: int  # new ones, queued for processing (the rest were redeliveries)


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    _channel: ChannelDep,
    settings: WhatsAppSettingsDep,
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
) -> str:
    """AC-1: echo `hub.challenge` when the verify token matches; 403 otherwise."""
    expected = settings.verify_token.get_secret_value()
    if mode != "subscribe" or not hmac.compare_digest(token.encode(), expected.encode()):
        logger.warning("WhatsApp webhook verification refused (mode=%r)", mode)
        raise HTTPException(status_code=403, detail="Verification failed")
    return challenge


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    channel: ChannelDep,
    settings: WhatsAppSettingsDep,
    service: ServiceDep,
    background: BackgroundTasks,
) -> WebhookAck:
    raw = await request.body()  # the exact bytes Meta signed
    secret = settings.app_secret.get_secret_value()
    if not verify_signature(raw, request.headers.get(SIGNATURE_HEADER), secret):
        logger.warning("WhatsApp webhook with a missing or invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = WebhookPayload.model_validate_json(raw)
    except ValidationError:
        # Signed by Meta but not a shape we know: a 200, or Meta retries it for days.
        logger.warning("WhatsApp webhook payload not understood; ignored")
        return WebhookAck(received=0, accepted=0)
    messages = inbound_messages(payload)
    accepted = 0
    for inbound in messages:
        if not await service.claim_inbound(inbound.message_id):
            logger.info("WhatsApp message %s already processed: skipped", inbound.message_id)
            continue
        background.add_task(channel.handle, inbound)
        accepted += 1
    return WebhookAck(received=len(messages), accepted=accepted)
