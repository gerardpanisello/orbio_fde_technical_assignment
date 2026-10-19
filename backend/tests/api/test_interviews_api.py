"""Spec 010 T6: availability, week view, attendance and interview analytics (AC-7, AC-8)."""

from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from tests.api.conftest import HAPPY_PATH, TickingClock
from tests.api.test_bookings import MALAGA_PATH

pytestmark = pytest.mark.anyio


async def chat(client: AsyncClient, messages: list[str]) -> str:
    conversation_id: str = (await client.post("/api/conversations")).json()["id"]
    for text in messages:
        response = await client.post(
            f"/api/conversations/{conversation_id}/messages", json={"text": text}
        )
        assert response.status_code == 200
    return conversation_id


async def last_offer(client: AsyncClient, conversation_id: str) -> list[str]:
    messages = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    return [q["id"] for q in messages[-1]["quick_replies"]]


async def test_lists_every_city_agenda(client: AsyncClient) -> None:
    cities = (await client.get("/api/interviews/availability")).json()
    assert [c["city"] for c in cities] == [
        "madrid",
        "barcelona",
        "valencia",
        "sevilla",
        "malaga",
        "cdmx",
        "guadalajara",
        "monterrey",
        "puebla",
    ]
    madrid = cities[0]
    assert madrid["city_name"] == "Madrid"
    assert madrid["timezone"] == "Europe/Madrid"
    assert madrid["times"] == ["10:00", "12:00", "17:00"]
    assert madrid["weekdays"] == ["mon", "tue", "wed", "thu", "fri"]
    assert (madrid["capacity"], madrid["duration_min"], madrid["days_ahead"]) == (3, 30, 3)
    assert "Calle del Ejemplo" in madrid["place"]


@pytest.mark.ac("010:AC-7")
@pytest.mark.parametrize(
    "body",
    [
        {"times": ["9:00"]},
        {"times": ["25:00"]},
        {"times": []},
        {"capacity": 0},
        {"capacity": -2},
        {"weekdays": ["funday"]},
        {"place": " "},
        {},
        {"unknown": 1},
    ],
)
async def test_availability_patch_validates_input(
    client: AsyncClient, body: dict[str, Any]
) -> None:
    response = await client.patch("/api/interviews/availability/madrid", json=body)
    assert response.status_code == 422, response.text
    madrid = (await client.get("/api/interviews/availability")).json()[0]
    assert madrid["capacity"] == 3  # nothing changed


async def test_unknown_city_is_a_404(client: AsyncClient) -> None:
    response = await client.patch("/api/interviews/availability/atlantis", json={"capacity": 2})
    assert response.status_code == 404
    assert (await client.get("/api/interviews/week?city=atlantis")).status_code == 404


@pytest.mark.ac("010:AC-7")
async def test_changes_affect_newly_offered_slots_only(client: AsyncClient) -> None:
    booked = await chat(client, [*MALAGA_PATH, "1"])  # Málaga, Tue 13/10 10:00
    response = await client.patch(
        "/api/interviews/availability/malaga",
        json={"times": ["12:30"], "capacity": 2, "weekdays": ["mon", "wed"]},
    )
    assert response.status_code == 200
    updated = response.json()
    assert (updated["times"], updated["capacity"]) == (["12:30"], 2)
    assert updated["weekdays"] == ["mon", "wed"]

    newcomer = await chat(client, MALAGA_PATH)
    assert await last_offer(client, newcomer) == [
        "malaga:2026-10-14T12:30",
        "malaga:2026-10-19T12:30",
        "malaga:2026-10-21T12:30",
    ]
    booking = (await client.get(f"/api/conversations/{booked}")).json()["booking"]
    assert booking["slot_id"] == "malaga:2026-10-13T10:00"  # the existing booking stands
    assert booking["status"] == "booked"


async def test_week_view_shows_capacity_and_who_is_booked(client: AsyncClient) -> None:
    lucia = await chat(client, HAPPY_PATH)  # Madrid, Tue 13/10 10:00
    week = (await client.get("/api/interviews/week?city=madrid")).json()
    assert (week["city"], week["city_name"], week["timezone"]) == (
        "madrid",
        "Madrid",
        "Europe/Madrid",
    )
    assert week["start"] == "2026-10-12"
    assert [d["weekday"] for d in week["days"]] == ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    assert week["days"][5]["slots"] == []  # no interviews at the weekend
    tuesday = week["days"][1]
    assert [s["time"] for s in tuesday["slots"]] == ["10:00", "12:00", "17:00"]
    ten = tuesday["slots"][0]
    assert ten["slot_id"] == "madrid:2026-10-13T10:00"
    assert ten["starts_at"].startswith("2026-10-13T08:00:00")
    assert (ten["capacity"], ten["booked"], ten["in_agenda"], ten["past"]) == (3, 1, True, False)
    [booked] = ten["bookings"]
    assert booked["conversation_id"] == lucia
    assert booked["full_name"] == "Lucía Martín"
    assert booked["status"] == "booked"
    monday = week["days"][0]["slots"][0]
    assert monday["past"] is True  # Monday 10:00 Madrid is before the clock (Mon 11:00)
    next_week = (await client.get("/api/interviews/week?city=madrid&start=2026-10-21")).json()
    assert next_week["start"] == "2026-10-19"
    assert next_week["days"][1]["slots"][0]["booked"] == 0


async def test_a_booking_outside_the_new_agenda_still_shows(client: AsyncClient) -> None:
    await chat(client, HAPPY_PATH)
    await client.patch("/api/interviews/availability/madrid", json={"times": ["12:00"]})
    tuesday = (await client.get("/api/interviews/week?city=madrid")).json()["days"][1]
    assert [(s["time"], s["in_agenda"], s["booked"]) for s in tuesday["slots"]] == [
        ("10:00", False, 1),
        ("12:00", True, 0),
    ]


@pytest.mark.ac("010:AC-8")
async def test_attendance_updates_the_show_up_rate(
    client: AsyncClient, clock: TickingClock
) -> None:
    ids = [await chat(client, HAPPY_PATH) for _ in range(3)]  # same slot, capacity 3
    booking_ids = [
        (await client.get(f"/api/candidates/{cid}")).json()["booking"]["id"] for cid in ids
    ]
    early = await client.patch(
        f"/api/interviews/bookings/{booking_ids[0]}", json={"status": "attended"}
    )
    assert early.status_code == 409  # the interview has not happened yet

    clock.now += timedelta(days=2)  # after Tuesday 10:00
    for booking_id, status in zip(booking_ids, ["attended", "attended", "no_show"], strict=True):
        response = await client.patch(
            f"/api/interviews/bookings/{booking_id}", json={"status": status}
        )
        assert response.status_code == 200
        assert response.json()["status"] == status
    interviews = (await client.get("/api/analytics")).json()["interviews"]
    assert interviews == {
        "booked": 3,
        "attended": 2,
        "no_show": 1,
        "show_up_rate": 0.6667,
        "rescheduled": 0,
        "cancelled": 0,
    }
    undo = await client.patch(
        f"/api/interviews/bookings/{booking_ids[2]}", json={"status": "booked"}
    )
    assert undo.status_code == 200
    assert (await client.get("/api/analytics")).json()["interviews"]["show_up_rate"] == 1.0
    detail = (await client.get(f"/api/candidates/{ids[0]}")).json()
    assert detail["booking"] is None  # attended: no longer a live booking
    assert [b["status"] for b in detail["bookings"]] == ["attended"]


@pytest.mark.ac("010:AC-8")
async def test_attendance_is_refused_for_moved_or_unknown_bookings(client: AsyncClient) -> None:
    conversation_id = await chat(client, HAPPY_PATH)
    await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "cancela la cita"}
    )
    [cancelled] = (await client.get(f"/api/candidates/{conversation_id}")).json()["bookings"]
    response = await client.patch(
        f"/api/interviews/bookings/{cancelled['id']}", json={"status": "no_show"}
    )
    assert response.status_code == 409
    assert (
        await client.patch("/api/interviews/bookings/999", json={"status": "attended"})
    ).status_code == 404
    bad = await client.patch(f"/api/interviews/bookings/{cancelled['id']}", json={"status": "x"})
    assert bad.status_code == 422


async def test_candidate_detail_shows_the_booking_and_its_history(client: AsyncClient) -> None:
    conversation_id = await chat(client, HAPPY_PATH)
    await client.post(
        f"/api/conversations/{conversation_id}/messages", json={"text": "¿puedo cambiar la cita?"}
    )
    await client.post(f"/api/conversations/{conversation_id}/messages", json={"text": "2"})
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert [b["status"] for b in detail["bookings"]] == ["rescheduled", "booked"]
    assert detail["booking"] == detail["bookings"][1]
    assert detail["booking"]["ics_url"] == f"/api/interviews/{conversation_id}.ics"
    assert detail["candidate"]["interview_slot_id"] == detail["booking"]["slot_id"]
    analytics = (await client.get("/api/analytics")).json()["interviews"]
    assert (analytics["booked"], analytics["rescheduled"]) == (1, 1)
