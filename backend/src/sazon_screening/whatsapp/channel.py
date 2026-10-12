"""The WhatsApp channel adapter (spec 016, ADR 0005): inbound turns and outbound sends.

Inbound (`handle`), one webhook message at a time per number:
  do-not-contact? -> drop | ignored type? -> log | mark read + typing -> find or start the
  conversation -> one turn through the service (the engine decides) -> send the reply.

Outbound (`deliver`, the service's `Delivery` hook): re-engagement reminders, as free text
inside the 24 h window and as the configured approved template outside it.

Every Graph API call is retried with backoff when the error is transient and logged
with the conversation id when it finally fails. Nothing here raises: the turn is
already stored when a send fails, so the conversation is never lost, and the candidate's
next message continues it. Phone numbers appear in logs only as `phone_ref` hashes.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from sazon_screening.api.service import Outbound, ScreeningService
from sazon_screening.llm.phrasing.phraser import OutboundMessage
from sazon_screening.vocab import Language
from sazon_screening.whatsapp.client import GraphError, WhatsAppClient
from sazon_screening.whatsapp.inbound import Inbound
from sazon_screening.whatsapp.payloads import (
    SendPayload,
    outbound_payload,
    read_receipt,
    template_message,
)
from sazon_screening.whatsapp.phone import normalise, phone_hash, phone_ref
from sazon_screening.whatsapp.settings import WhatsAppConfig

logger = logging.getLogger("sazon_screening.whatsapp")

ATTEMPTS = 3  # first try + 2 retries
BACKOFF_S = 0.5  # 0.5 s, then 1 s


class WhatsAppChannel:
    def __init__(
        self,
        service: ScreeningService,
        client: WhatsAppClient,
        config: WhatsAppConfig,
        *,
        attempts: int = ATTEMPTS,
        backoff_s: float = BACKOFF_S,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._service = service
        self._client = client
        self._config = config
        self._attempts = attempts
        self._backoff_s = backoff_s
        self._sleep = sleep
        # One message at a time per number: keeps their order, and two quick first
        # messages cannot open two conversations.
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        if config.follow_up_template.placeholder:
            logger.warning(
                "WhatsApp follow-up template '%s' is a placeholder: reminders outside the "
                "24 h window need a real approved template (config/whatsapp.yaml)",
                config.follow_up_template.name,
            )

    # --- inbound -------------------------------------------------------------------------

    async def handle(self, inbound: Inbound) -> None:
        """Process one webhook message. Never raises (it runs after the 200 was sent)."""
        wa_id = normalise(inbound.wa_id)
        async with self._locks[phone_hash(wa_id)]:
            try:
                await self._handle(inbound, wa_id)
            except Exception:
                logger.exception(
                    "WhatsApp inbound %s failed (%s)", inbound.message_id, phone_ref(wa_id)
                )

    async def _handle(self, inbound: Inbound, wa_id: str) -> None:
        ref = phone_ref(wa_id)
        if await self._service.is_do_not_contact(wa_id):
            logger.info("WhatsApp message from a do-not-contact number dropped (%s)", ref)
            return
        if inbound.kind == "ignored":
            logger.info("WhatsApp %s message ignored (%s)", inbound.type, ref)
            return
        await self._mark_read(inbound.message_id, ref)
        conversation_id = await self._service.conversation_for_phone(wa_id)
        if conversation_id is None:
            conversation_id, reply = await self._service.start_whatsapp(
                wa_id,
                inbound.text,
                language=Language.es,
                country_hint=self._config.country_for(wa_id),
            )
            logger.info("WhatsApp conversation started (conversation %s, %s)", conversation_id, ref)
            summary_due = False
        else:
            text = inbound.text
            if inbound.kind == "choice" and inbound.choice_id is not None:
                label = await self._service.quick_reply_label(conversation_id, inbound.choice_id)
                text = label or inbound.text
            outcome = await self._service.send_message(
                conversation_id, text, kind="media" if inbound.kind == "media" else "text"
            )
            reply, summary_due = outcome.result.reply, outcome.result.summary_due
        if reply is not None:
            # The opt-out confirmation too: it answers their own message, inside the window.
            await self.send_reply(conversation_id, wa_id, reply)
        if summary_due:
            await self._service.write_summary(conversation_id)

    async def _mark_read(self, message_id: str, ref: str) -> None:
        """Blue ticks + "typing…" while the turn runs. Best effort: never retried."""
        try:
            await self._client.send(read_receipt(message_id))
        except GraphError as error:
            logger.warning("WhatsApp read receipt failed (%s): %s", ref, error.detail)

    # --- outbound ------------------------------------------------------------------------

    async def send_reply(self, conversation_id: str, wa_id: str, reply: OutboundMessage) -> bool:
        payload = outbound_payload(
            wa_id,
            reply.text,
            list(reply.quick_replies),
            list_button=self._config.list_button[reply.language],
        )
        return await self._send(payload, conversation_id, wa_id)

    async def deliver(self, outbound: Outbound) -> None:
        """The service's delivery hook (re-engagement, spec 008 + 016 FR-6)."""
        cid, phone = outbound.conversation_id, outbound.phone
        try:
            if phone is None:  # opted out (number erased), or demo data without a number
                logger.info("WhatsApp %s not sent: no number (conversation %s)", outbound.kind, cid)
                return
            if await self._service.is_do_not_contact(phone):
                logger.info(
                    "WhatsApp %s suppressed: do-not-contact (conversation %s)", outbound.kind, cid
                )
                return
            if not outbound.outside_window:
                await self.send_reply(cid, phone, outbound.reply)
                return
            if outbound.kind != "follow_up":
                logger.warning(
                    "WhatsApp %s not sent: outside the 24 h window and only the follow-up "
                    "template is configured (conversation %s)",
                    outbound.kind,
                    cid,
                )
                return
            template = self._config.follow_up_template
            if template.placeholder:
                logger.warning(
                    "WhatsApp follow-up sent as placeholder template '%s': configure a real "
                    "approved template (conversation %s)",
                    template.name,
                    cid,
                )
            await self._send(template_message(phone, template.name, template.language), cid, phone)
        except Exception:
            logger.exception("WhatsApp delivery failed (conversation %s)", cid)

    async def _send(self, payload: SendPayload, conversation_id: str, wa_id: str) -> bool:
        """Send with retry and exponential backoff on transient errors (FR-5, AC-9)."""
        ref = phone_ref(wa_id)
        for attempt in range(1, self._attempts + 1):
            try:
                await self._client.send(payload)
            except GraphError as error:
                last = attempt == self._attempts or not error.retryable
                logger.log(
                    logging.ERROR if last else logging.WARNING,
                    "WhatsApp %s send failed, attempt %d/%d%s (conversation %s, %s): %s",
                    payload.type,
                    attempt,
                    self._attempts,
                    "" if last else ", retrying",
                    conversation_id,
                    ref,
                    error.detail,
                )
                if last:
                    return False
                await self._sleep(self._backoff_s * 2 ** (attempt - 1))
            else:
                return True
        return False  # pragma: no cover - the loop always returns
