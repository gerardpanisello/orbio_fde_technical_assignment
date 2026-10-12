"""Typed request bodies for the Cloud API `/{phone_number_id}/messages` endpoint (FR-5).

Shapes and limits from Meta's WhatsApp Cloud API reference (checked 2026-10-13):

- text: body <= 4096 chars; `preview_url: false` (no link previews).
- interactive `button`: <= 3 reply buttons, title <= 20 chars and unique, id <= 256,
  body <= 1024.
- interactive `list`: <= 10 rows in total, row title <= 24, row id <= 200, row
  description <= 72, button text <= 20, body <= 4096.
- template: name + language code (approved in WhatsApp Manager).
- read receipt + typing indicator: one request, `status: read` + `message_id` +
  `typing_indicator: {type: text}` (dismissed on reply or after 25 s).

`outbound_payload` picks the shape for one agent reply; the channel never builds JSON
by hand.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.llm.phrasing.quick_replies import QuickReply

TEXT_MAX = 4096
BUTTONS_MAX = 3
BUTTON_TITLE_MAX = 20
BUTTON_ID_MAX = 256
BUTTON_BODY_MAX = 1024
LIST_ROWS_MAX = 10
ROW_TITLE_MAX = 24
ROW_ID_MAX = 200
ROW_DESCRIPTION_MAX = 72
LIST_BUTTON_MAX = 20
LIST_BODY_MAX = 4096
ELLIPSIS = "…"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- shapes ------------------------------------------------------------------------------


class TextBody(_Payload):
    body: str
    preview_url: bool = False


class TextMessage(_Payload):
    messaging_product: Literal["whatsapp"] = "whatsapp"
    recipient_type: Literal["individual"] = "individual"
    to: str
    type: Literal["text"] = "text"
    text: TextBody


class BodyText(_Payload):
    text: str


class Reply(_Payload):
    id: str
    title: str


class ReplyButton(_Payload):
    type: Literal["reply"] = "reply"
    reply: Reply


class ButtonAction(_Payload):
    buttons: list[ReplyButton]


class ButtonInteractive(_Payload):
    type: Literal["button"] = "button"
    body: BodyText
    action: ButtonAction


class Row(_Payload):
    id: str
    title: str
    description: str | None = None


class Section(_Payload):
    rows: list[Row]


class ListAction(_Payload):
    button: str
    sections: list[Section]


class ListInteractive(_Payload):
    type: Literal["list"] = "list"
    body: BodyText
    action: ListAction


class InteractiveMessage(_Payload):
    messaging_product: Literal["whatsapp"] = "whatsapp"
    recipient_type: Literal["individual"] = "individual"
    to: str
    type: Literal["interactive"] = "interactive"
    interactive: ButtonInteractive | ListInteractive


class TemplateLanguage(_Payload):
    code: str


class Template(_Payload):
    name: str
    language: TemplateLanguage


class TemplateMessage(_Payload):
    messaging_product: Literal["whatsapp"] = "whatsapp"
    recipient_type: Literal["individual"] = "individual"
    to: str
    type: Literal["template"] = "template"
    template: Template


class TypingIndicator(_Payload):
    type: Literal["text"] = "text"


class ReadReceipt(_Payload):
    """Marks an inbound message as read (blue ticks) and shows "typing…"."""

    messaging_product: Literal["whatsapp"] = "whatsapp"
    status: Literal["read"] = "read"
    message_id: str
    typing_indicator: TypingIndicator | None = TypingIndicator()


SendPayload = TextMessage | InteractiveMessage | TemplateMessage
Payload = SendPayload | ReadReceipt


# --- builders ----------------------------------------------------------------------------


def truncate(text: str, limit: int) -> str:
    """Fit `text` in `limit` chars: cut at a word boundary when that keeps most of it,
    and end with '…' so the cut is visible."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ELLIPSIS)]
    space = cut.rfind(" ")
    if space >= limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,.;:") + ELLIPSIS


def text_message(to: str, body: str) -> TextMessage:
    return TextMessage(to=to, text=TextBody(body=truncate_body(body, TEXT_MAX)))


def buttons_message(to: str, body: str, options: list[QuickReply]) -> InteractiveMessage:
    if not 1 <= len(options) <= BUTTONS_MAX:
        raise ValueError(f"reply buttons take 1 to {BUTTONS_MAX} options, got {len(options)}")
    buttons = [
        ReplyButton(
            reply=Reply(
                id=option.id[:BUTTON_ID_MAX], title=truncate(option.label, BUTTON_TITLE_MAX)
            )
        )
        for option in options
    ]
    interactive = ButtonInteractive(
        body=BodyText(text=truncate_body(body, BUTTON_BODY_MAX)),
        action=ButtonAction(buttons=buttons),
    )
    return InteractiveMessage(to=to, interactive=interactive)


def list_message(to: str, body: str, options: list[QuickReply], button: str) -> InteractiveMessage:
    if not 1 <= len(options) <= LIST_ROWS_MAX:
        raise ValueError(f"a list takes 1 to {LIST_ROWS_MAX} options, got {len(options)}")
    rows = []
    for option in options:
        title = truncate(option.label, ROW_TITLE_MAX)
        full = " ".join(option.label.split())
        # A cut title: the description (72 chars) shows the whole label.
        description = truncate(full, ROW_DESCRIPTION_MAX) if title != full else None
        rows.append(Row(id=option.id[:ROW_ID_MAX], title=title, description=description))
    interactive = ListInteractive(
        body=BodyText(text=truncate_body(body, LIST_BODY_MAX)),
        action=ListAction(button=truncate(button, LIST_BUTTON_MAX), sections=[Section(rows=rows)]),
    )
    return InteractiveMessage(to=to, interactive=interactive)


def numbered_text(to: str, body: str, options: list[QuickReply]) -> TextMessage:
    """More options than a list holds: a plain text with the options numbered."""
    lines = [body, "", *(f"{n}. {option.label}" for n, option in enumerate(options, 1))]
    return text_message(to, "\n".join(lines))


def template_message(to: str, name: str, language: str) -> TemplateMessage:
    return TemplateMessage(
        to=to, template=Template(name=name, language=TemplateLanguage(code=language))
    )


def read_receipt(message_id: str, *, typing: bool = True) -> ReadReceipt:
    return ReadReceipt(
        message_id=message_id, typing_indicator=TypingIndicator() if typing else None
    )


def outbound_payload(
    to: str, text: str, options: list[QuickReply], *, list_button: str
) -> SendPayload:
    """One agent reply -> the best shape WhatsApp offers for it (FR-5):

    - no options: plain text;
    - 1-3 options whose titles stay distinct within 20 chars, and a body within 1024:
      reply buttons;
    - up to 10 options: a list message (also the fallback when buttons do not fit);
    - more than 10: text with numbered options (the candidate types the answer).
    """
    if not options:
        return text_message(to, text)
    if len(options) <= BUTTONS_MAX and len(text) <= BUTTON_BODY_MAX:
        titles = {truncate(option.label, BUTTON_TITLE_MAX).casefold() for option in options}
        if len(titles) == len(options):  # WhatsApp rejects duplicate button titles
            return buttons_message(to, text, options)
    if len(options) <= LIST_ROWS_MAX:
        return list_message(to, text, options, list_button)
    return numbered_text(to, text, options)


def truncate_body(text: str, limit: int) -> str:
    """Bodies keep their line breaks (truncate() folds whitespace, fine for titles only)."""
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS
