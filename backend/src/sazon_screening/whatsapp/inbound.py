"""Webhook side (spec 016 FR-1, FR-4): signature check and inbound message mapping.

Payload shape (Meta Cloud API webhooks, field `messages`):

    {"object": "whatsapp_business_account",
     "entry": [{"id": "...", "changes": [{"field": "messages", "value": {
         "messaging_product": "whatsapp",
         "metadata": {"display_phone_number": "...", "phone_number_id": "..."},
         "contacts": [{"wa_id": "34600000001", "profile": {"name": "..."}}],
         "messages": [{"from": "34600000001", "id": "wamid...", "timestamp": "...",
                       "type": "text", "text": {"body": "Hola"}}],
         "statuses": [...]}}]}]}

Delivery `statuses` (sent/delivered/read/failed) arrive on the same field and are
ignored here. The models are lenient (`extra="ignore"`): Meta adds fields over time.
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SIGNATURE_HEADER = "X-Hub-Signature-256"
MEDIA_TYPES = frozenset({"audio", "image", "sticker", "video", "document"})


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """`X-Hub-Signature-256: sha256=<hex HMAC-SHA256 of the raw body, key = app secret>`.
    Compared in constant time. The raw bytes matter: re-serialised JSON would not match."""
    if not header or not header.startswith("sha256=") or not app_secret:
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def sign(raw_body: bytes, app_secret: str) -> str:
    """The header value Meta would send (for tests and local tools)."""
    return "sha256=" + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class TextPart(_Lenient):
    body: str = ""


class ReplyPart(_Lenient):
    id: str
    title: str = ""


class InteractivePart(_Lenient):
    type: str
    button_reply: ReplyPart | None = None
    list_reply: ReplyPart | None = None


class TemplateButtonPart(_Lenient):
    """A tap on a template's quick-reply button (e.g. on a re-engagement template)."""

    text: str = ""
    payload: str | None = None


class WebhookMessage(_Lenient):
    sender: str = Field(alias="from")
    id: str
    type: str
    text: TextPart | None = None
    interactive: InteractivePart | None = None
    button: TemplateButtonPart | None = None


class ChangeValue(_Lenient):
    messages: list[WebhookMessage] = []


class Change(_Lenient):
    field: str
    value: ChangeValue


class Entry(_Lenient):
    changes: list[Change] = []


class WebhookPayload(_Lenient):
    object: str = ""
    entry: list[Entry] = []


InboundKind = Literal["text", "choice", "media", "ignored"]


@dataclass(frozen=True)
class Inbound:
    """One candidate message, channel-neutral. `wa_id` must never reach a log line."""

    message_id: str
    wa_id: str
    kind: InboundKind
    text: str  # the text, the tapped option's title, or a media placeholder like "[audio]"
    type: str  # WhatsApp's type, for logs
    choice_id: str | None = None  # the button/row id we sent (a quick reply id)


def inbound_messages(payload: WebhookPayload) -> list[Inbound]:
    return [
        to_inbound(message)
        for entry in payload.entry
        for change in entry.changes
        if change.field == "messages"
        for message in change.value.messages
    ]


def to_inbound(message: WebhookMessage) -> Inbound:
    """FR-4: text -> text; a tapped button or list row -> the option; audio, image,
    sticker (and video, document) -> media; anything else (reaction, location, contacts,
    unsupported...) -> ignored."""

    def make(kind: InboundKind, text: str, choice_id: str | None = None) -> Inbound:
        return Inbound(message.id, message.sender, kind, text, message.type, choice_id)

    match message.type:
        case "text" if message.text is not None and message.text.body.strip():
            return make("text", message.text.body)
        case "interactive" if message.interactive is not None:
            reply = message.interactive.button_reply or message.interactive.list_reply
            if reply is not None:
                return make("choice", reply.title, reply.id)
        case "button" if message.button is not None and message.button.text.strip():
            return make("text", message.button.text)
        case kind if kind in MEDIA_TYPES:
            return make("media", f"[{kind}]")
    return make("ignored", "")
