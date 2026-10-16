"""A calendar invite for one interview (spec 010 FR-5): iCalendar, RFC 5545, by hand.

No dependency: one VEVENT is a dozen lines, and the rules that matter are few and tested:
- every line ends in CRLF, and lines longer than 75 octets are folded (CRLF + one space),
  never inside a UTF-8 character;
- TEXT values escape backslash, semicolon, comma and newlines;
- times are UTC with a trailing `Z` (valid everywhere and needs no VTIMEZONE block); the
  calendar app shows them in the candidate's own timezone;
- `UID` is stable per booking, so importing the same invite twice updates one event.
`METHOD:PUBLISH`: an invite to add, not a meeting request that expects a reply.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

PRODID = "-//Grupo Sazon//Screening agent//ES"
FOLD_AT = 75  # octets per line, CRLF excluded (RFC 5545 §3.1)


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    starts_at: datetime  # aware
    ends_at: datetime  # aware
    stamp: datetime  # aware: when this invite was created (DTSTAMP)
    summary: str
    location: str
    description: str


def build_ics(event: CalendarEvent) -> str:
    """The whole .ics file, CRLF line endings included."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{escape_text(event.uid)}",
        f"DTSTAMP:{utc_stamp(event.stamp)}",
        f"DTSTART:{utc_stamp(event.starts_at)}",
        f"DTEND:{utc_stamp(event.ends_at)}",
        f"SUMMARY:{escape_text(event.summary)}",
        f"LOCATION:{escape_text(event.location)}",
        f"DESCRIPTION:{escape_text(event.description)}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "".join(fold(line) + "\r\n" for line in lines)


def utc_stamp(moment: datetime) -> str:
    """20261020T080000Z"""
    if moment.tzinfo is None:
        raise ValueError("calendar times must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def escape_text(value: str) -> str:
    """RFC 5545 §3.3.11: backslash first, then ; and , and line breaks as \\n."""
    escaped = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return escaped.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def fold(line: str) -> str:
    """Split a content line into physical lines of at most 75 octets (continuations start
    with a space, which counts), never splitting a multi-byte character."""
    parts: list[str] = []
    current, size, limit = "", 0, FOLD_AT
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            parts.append(current)
            current, size, limit = "", 0, FOLD_AT - 1
        current += char
        size += width
    parts.append(current)
    return "\r\n ".join(parts)
