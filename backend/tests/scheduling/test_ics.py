"""Spec 010 T4: the .ics invite is valid iCalendar (AC-5), checked structurally."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sazon_screening.scheduling import SlotTime
from sazon_screening.scheduling.ics import CalendarEvent, build_ics, escape_text, fold

STAMP = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
REQUIRED_EVENT = {"UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "LOCATION", "DESCRIPTION"}


def invite(city_tz: str, local: str, **overrides: str) -> str:
    slot = SlotTime(day=date(2026, 10, 20), time=local, city="x")
    starts = slot.starts_at(ZoneInfo(city_tz))
    values = {
        "uid": "interview-7@gruposazon.example",
        "summary": "Entrevista Grupo Sazón — repartidor/a",
        "location": "Calle del Ejemplo 12, 2.º (dirección ficticia)",
        "description": "Entrevista para el puesto. Si no puedes ir, escribe a Sofi.",
    } | overrides
    return build_ics(
        CalendarEvent(
            starts_at=starts, ends_at=starts + timedelta(minutes=30), stamp=STAMP, **values
        )
    )


def parse(ics: str) -> list[tuple[str, str]]:
    """A strict-enough reader: CRLF only, folded lines <= 75 octets, NAME:VALUE pairs."""
    assert ics.endswith("\r\n")
    assert "\n" not in ics.replace("\r\n", ""), "bare LF"
    assert "\r" not in ics.replace("\r\n", ""), "bare CR"
    physical = ics.split("\r\n")[:-1]
    assert all(len(line.encode("utf-8")) <= 75 for line in physical)
    unfolded: list[str] = []
    for line in physical:
        if line.startswith(" "):
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    pairs = []
    for line in unfolded:
        name, sep, value = line.partition(":")
        assert sep, line
        assert name == name.upper(), line
        pairs.append((name, value))
    return pairs


def unescape(value: str) -> str:
    out, i = "", 0
    while i < len(value):
        if value[i] == "\\":
            nxt = value[i + 1]
            out += "\n" if nxt in "nN" else nxt
            i += 2
        else:
            out += value[i]
            i += 1
    return out


@pytest.mark.ac("010:AC-5")
@pytest.mark.parametrize(
    ("city_tz", "local", "start", "end"),
    [
        ("Europe/Madrid", "10:00", "20261020T080000Z", "20261020T083000Z"),  # CEST, UTC+2
        ("America/Mexico_City", "10:00", "20261020T160000Z", "20261020T163000Z"),  # UTC-6
        ("America/Monterrey", "17:00", "20261020T230000Z", "20261020T233000Z"),
    ],
)
def test_invite_is_valid_icalendar_with_timezone_correct_times(
    city_tz: str, local: str, start: str, end: str
) -> None:
    pairs = parse(invite(city_tz, local))
    names = [name for name, _ in pairs]
    assert names[:5] == ["BEGIN", "VERSION", "PRODID", "CALSCALE", "METHOD"]
    assert pairs[0] == ("BEGIN", "VCALENDAR")
    assert pairs[-1] == ("END", "VCALENDAR")
    assert ("VERSION", "2.0") in pairs
    assert ("METHOD", "PUBLISH") in pairs
    event = dict(pairs[pairs.index(("BEGIN", "VEVENT")) + 1 : pairs.index(("END", "VEVENT"))])
    assert set(event) >= REQUIRED_EVENT
    assert (event["DTSTART"], event["DTEND"]) == (start, end)
    assert event["DTSTAMP"] == "20261016T093000Z"
    assert unescape(event["SUMMARY"]) == "Entrevista Grupo Sazón — repartidor/a"
    assert unescape(event["LOCATION"]) == "Calle del Ejemplo 12, 2.º (dirección ficticia)"


@pytest.mark.ac("010:AC-5")
def test_a_winter_date_in_madrid_is_one_hour_off_utc() -> None:
    slot = SlotTime(day=date(2026, 10, 26), time="10:00", city="madrid")
    starts = slot.starts_at(ZoneInfo("Europe/Madrid"))
    ics = build_ics(
        CalendarEvent("u", starts, starts + timedelta(minutes=30), STAMP, "s", "l", "d")
    )
    assert "DTSTART:20261026T090000Z\r\n" in ics


@pytest.mark.ac("010:AC-5")
def test_long_multibyte_text_is_folded_and_round_trips() -> None:
    description = "Entrevista en la oficina de Grupo Sazón — repartidor/a; trae tu DNI, " * 4
    pairs = dict(parse(invite("Europe/Madrid", "10:00", description=description)))
    assert unescape(pairs["DESCRIPTION"]) == description


def test_text_escaping() -> None:
    assert escape_text("a\\b;c,d\ne") == "a\\\\b\\;c\\,d\\ne"


def test_fold_never_splits_a_character() -> None:
    line = "DESCRIPTION:" + "ñ" * 80
    for part in fold(line).split("\r\n"):
        part.encode("utf-8").decode("utf-8")
        assert len(part.encode("utf-8")) <= 75


def test_naive_times_are_refused() -> None:
    naive = datetime(2026, 10, 20, 10, 0)
    with pytest.raises(ValueError, match="aware"):
        build_ics(CalendarEvent("u", naive, naive, STAMP, "s", "l", "d"))
