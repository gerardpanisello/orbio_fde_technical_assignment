"""Spec 015 T3: staffing per area, the live score, hire +1 and the waitlist over HTTP."""

import csv
import io
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.api import repo
from sazon_screening.api.app import create_app
from sazon_screening.api.db import Sessions
from sazon_screening.api.settings import AppSettings
from sazon_screening.llm.pipeline import ScreeningAgent
from tests.api.conftest import HAPPY_PATH, TickingClock
from tests.api.test_candidates import converse

UP_TO_RECAP = HAPPY_PATH[:-1]  # ... "sí" to the recap; the slot pick is not sent


def living_in(place: str, script: list[str] = UP_TO_RECAP) -> list[str]:
    return [f"vivo en {place}" if text.startswith("vivo en") else text for text in script]


async def zones(client: AsyncClient, **params: str) -> dict[str, dict[str, Any]]:
    response = await client.get("/api/zones", params=params)
    assert response.status_code == 200
    return {zone["id"]: zone for zone in response.json()}


async def patch(client: AsyncClient, area_id: str, **body: int) -> Any:
    return await client.patch(f"/api/zones/{area_id}", json=body)


async def row(client: AsyncClient, conversation_id: str) -> dict[str, Any]:
    rows = (await client.get("/api/candidates")).json()
    found: dict[str, Any] = next(r for r in rows if r["id"] == conversation_id)
    return found


async def last_reply(client: AsyncClient, conversation_id: str) -> str:
    conversation = (await client.get(f"/api/conversations/{conversation_id}")).json()
    text: str = conversation["messages"][-1]["text"]
    return text


def sessions_of(app: FastAPI) -> Sessions:
    sessions: Sessions = app.state.sessions
    return sessions


async def current_drivers(app: FastAPI, area_id: str) -> int:
    async with sessions_of(app)() as session:
        staffing = await repo.get_staffing(session, area_id)
    assert staffing is not None
    return staffing.current_drivers


# --- GET / PATCH /api/zones ---------------------------------------------------------------


@pytest.mark.anyio
async def test_zones_list_every_served_area_seeded_from_config(client: AsyncClient) -> None:
    by_id = await zones(client)
    assert len(by_id) == 44  # every zone of service_areas.yaml (all cities have zones)
    salamanca = by_id["mad-salamanca"]
    assert salamanca == {
        "id": "mad-salamanca",
        "name": "Salamanca",
        "city": "madrid",
        "city_name": "Madrid",
        "country": "ES",
        "target_drivers": 30,
        "current_drivers": 32,
        "occupancy_pct": 106,
        "full": True,
        "pipeline": {"qualified_unscheduled": 0, "interview_scheduled": 0, "waitlisted": 0},
        "updated_at": salamanca["updated_at"],
    }
    assert by_id["mad-chamberi"]["occupancy_pct"] == 40
    assert by_id["mad-chamberi"]["full"] is False
    no_data = by_id["pue-cholula"]
    assert (no_data["target_drivers"], no_data["occupancy_pct"], no_data["full"]) == (
        None,
        None,
        False,
    )
    english = await zones(client, lang="en")
    assert english["sev-casco-antiguo"]["name"] == "Old Town"
    assert english["cdmx-coyoacan"]["city_name"] == "Mexico City"


@pytest.mark.anyio
async def test_patch_updates_one_or_both_numbers(client: AsyncClient) -> None:
    response = await patch(client, "mad-chamberi", target_drivers=24)
    assert response.status_code == 200
    assert (response.json()["target_drivers"], response.json()["current_drivers"]) == (24, 12)
    assert response.json()["occupancy_pct"] == 50
    both = (await patch(client, "mad-chamberi", target_drivers=10, current_drivers=10)).json()
    assert (both["occupancy_pct"], both["full"]) == (100, True)
    assert (await zones(client))["mad-chamberi"]["full"] is True  # persisted


@pytest.mark.anyio
async def test_patch_on_an_area_without_data_creates_it(client: AsyncClient) -> None:
    created = (await patch(client, "pue-cholula", target_drivers=20)).json()
    assert (created["target_drivers"], created["current_drivers"]) == (20, 0)
    assert created["occupancy_pct"] == 0


@pytest.mark.anyio
async def test_target_of_zero_counts_as_full(client: AsyncClient) -> None:
    zone = (await patch(client, "mad-retiro", target_drivers=0)).json()
    assert (zone["occupancy_pct"], zone["full"]) == (100, True)


@pytest.mark.anyio
@pytest.mark.ac("015:AC-6")
@pytest.mark.parametrize(
    "body",
    [
        {"target_drivers": -1},
        {"current_drivers": -5},
        {"target_drivers": 10, "current_drivers": -1},
        {},
        {"target_drivers": "many"},
        {"target_drivers": 10, "occupancy": 3},
    ],
)
async def test_patch_rejects_invalid_numbers(client: AsyncClient, body: dict[str, Any]) -> None:
    response = await client.patch("/api/zones/mad-chamberi", json=body)
    assert response.status_code == 422
    assert (await zones(client))["mad-chamberi"]["target_drivers"] == 30  # unchanged


@pytest.mark.anyio
async def test_patch_unknown_area_is_404(client: AsyncClient) -> None:
    for area_id in ("mad-vallecas", "madrid"):  # not served; a city with zones is not an area
        assert (await patch(client, area_id, target_drivers=3)).status_code == 404


@pytest.mark.anyio
async def test_seed_only_fills_an_empty_table(
    settings: AppSettings, agent: ScreeningAgent, client: AsyncClient
) -> None:
    await patch(client, "mad-salamanca", current_drivers=3)
    restarted = create_app(settings, agent=agent, clock=TickingClock())  # same database
    async with restarted.router.lifespan_context(restarted):
        current = await current_drivers(restarted, "mad-salamanca")
    assert current == 3  # the dashboard edit survives a restart


# --- the waitlist (zone_full when entering scheduling) ---------------------------------


@pytest.mark.anyio
@pytest.mark.ac("015:AC-3")
async def test_recap_confirmed_in_a_full_area_waitlists(client: AsyncClient) -> None:
    conversation_id = await converse(client, living_in("Salamanca, Madrid"))
    candidate = await row(client, conversation_id)
    assert candidate["status"] == "waitlisted"
    assert candidate["interview_slot"] is None
    reply = await last_reply(client, conversation_id)
    assert "lista de espera" in reply
    assert "Salamanca" in reply
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["traces"][-1]["action"] == "close_waitlisted"
    assert (await zones(client))["mad-salamanca"]["pipeline"]["waitlisted"] == 1
    waitlisted = (await client.get("/api/candidates", params={"status": "waitlisted"})).json()
    assert [r["id"] for r in waitlisted] == [conversation_id]


@pytest.mark.anyio
@pytest.mark.ac("015:AC-3")
async def test_recap_confirmed_in_an_area_with_room_offers_slots(client: AsyncClient) -> None:
    conversation_id = await converse(client, UP_TO_RECAP)  # Chamberí, 40 %
    assert (await row(client, conversation_id))["status"] == "in_progress"
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["traces"][-1]["action"] == "offer_slots"
    assert (await zones(client))["mad-chamberi"]["pipeline"]["waitlisted"] == 0


@pytest.mark.anyio
@pytest.mark.ac("015:AC-3")
async def test_fullness_is_read_live_when_the_recap_is_confirmed(client: AsyncClient) -> None:
    await patch(client, "mad-chamberi", target_drivers=12)  # 12 / 12: now full
    conversation_id = await converse(client, UP_TO_RECAP)
    assert (await row(client, conversation_id))["status"] == "waitlisted"


@pytest.mark.anyio
@pytest.mark.ac("015:AC-5")
async def test_area_without_data_gets_no_bonus_and_is_never_waitlisted(
    app: FastAPI, client: AsyncClient
) -> None:
    async with sessions_of(app).begin() as session:
        staffing = await repo.get_staffing(session, "mad-chamberi")
        assert staffing is not None
        await session.delete(staffing)  # Chamberí: no staffing data
    conversation_id = await converse(client, HAPPY_PATH)
    candidate = await row(client, conversation_id)
    assert candidate["status"] == "interview_scheduled"
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    zone_factor = detail["live_score"]["factors"][-1]
    assert zone_factor == {
        "field": "location",
        "value": None,
        "points": 0,
        "reason_code": "zone_demand",
    }
    assert detail["record"]["score"]["factors"][-1]["points"] == 0
    assert candidate["score"] == candidate["score_at_close"]


# --- live score (FR-6) ------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.ac("015:AC-2")
async def test_staffing_edit_changes_the_live_score_not_the_score_at_close(
    client: AsyncClient,
) -> None:
    conversation_id = await converse(client, HAPPY_PATH)  # Chamberí 40 %: +20
    before = await row(client, conversation_id)
    assert before["score"] == before["score_at_close"] == 75
    assert before["bucket"] == before["bucket_at_close"] == "high"
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["live_score"]["factors"][-1]["value"] == 40

    await patch(client, "mad-chamberi", target_drivers=12)  # now 100 %: +0
    after = await row(client, conversation_id)
    assert (after["score"], after["bucket"]) == (55, "medium")
    assert (after["score_at_close"], after["bucket_at_close"]) == (75, "high")
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert detail["live_score"]["score"] == 55
    assert detail["live_score"]["factors"][-1] == {
        "field": "location",
        "value": 100,
        "points": 0,
        "reason_code": "zone_demand",
    }
    assert detail["record"]["score"]["score"] == 75  # the record is not reprocessed
    high = (await client.get("/api/candidates", params={"bucket": "high"})).json()
    medium = (await client.get("/api/candidates", params={"bucket": "medium"})).json()
    assert conversation_id not in [r["id"] for r in high]
    assert conversation_id in [r["id"] for r in medium]


@pytest.mark.anyio
@pytest.mark.ac("015:AC-2")
async def test_sort_by_score_uses_the_live_score(client: AsyncClient) -> None:
    chamberi = await converse(client, living_in("Chamberí, Madrid", HAPPY_PATH))
    tetuan = await converse(client, living_in("Tetuán, Madrid", HAPPY_PATH))

    async def order() -> list[str]:
        rows = (await client.get("/api/candidates", params={"sort": "-score"})).json()
        return [r["id"] for r in rows]

    await patch(client, "mad-tetuan", target_drivers=9)  # Tetuán full: 55 vs Chamberí 75
    assert await order() == [chamberi, tetuan]
    await patch(client, "mad-tetuan", target_drivers=90)  # Tetuán 10 %: 75
    await patch(client, "mad-chamberi", target_drivers=12)  # Chamberí full: 55
    assert await order() == [tetuan, chamberi]
    ascending = (await client.get("/api/candidates", params={"sort": "score"})).json()
    assert [r["id"] for r in ascending] == [chamberi, tetuan]


@pytest.mark.anyio
async def test_csv_has_live_and_at_close_scores(client: AsyncClient) -> None:
    await converse(client, HAPPY_PATH)
    await patch(client, "mad-chamberi", target_drivers=12)
    response = await client.get("/api/candidates/export.csv")
    (exported,) = list(csv.DictReader(io.StringIO(response.text)))
    assert (exported["score"], exported["score_at_close"]) == ("55", "75")
    assert (exported["bucket"], exported["bucket_at_close"]) == ("medium", "high")


# --- hire -> +1 (FR-5) --------------------------------------------------------------------


async def hire(client: AsyncClient, conversation_id: str) -> int:
    response = await client.post(
        f"/api/candidates/{conversation_id}/actions", json={"action": "hire"}
    )
    return response.status_code


@pytest.mark.anyio
@pytest.mark.ac("015:AC-4")
async def test_hire_adds_one_driver_once_per_candidate(client: AsyncClient) -> None:
    conversation_id = await converse(client, HAPPY_PATH)
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 12
    assert await hire(client, conversation_id) == 201
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 13
    assert await hire(client, conversation_id) == 201  # recorded again, counted once
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 13
    detail = (await client.get(f"/api/candidates/{conversation_id}")).json()
    assert [a["action"] for a in detail["actions"]] == ["hire", "hire"]
    other = await converse(client, HAPPY_PATH)
    assert await hire(client, other) == 201
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 14


@pytest.mark.anyio
@pytest.mark.ac("015:AC-4")
async def test_hire_after_a_manual_edit_still_adds_one(client: AsyncClient) -> None:
    conversation_id = await converse(client, HAPPY_PATH)
    await patch(client, "mad-chamberi", current_drivers=20)
    await hire(client, conversation_id)
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 21


@pytest.mark.anyio
async def test_other_actions_do_not_touch_staffing(client: AsyncClient) -> None:
    conversation_id = await converse(client, HAPPY_PATH)
    for action in ("shortlist", "reject"):
        body = {"action": action}
        assert (
            await client.post(f"/api/candidates/{conversation_id}/actions", json=body)
        ).status_code == 201
    assert (await zones(client))["mad-chamberi"]["current_drivers"] == 12


@pytest.mark.anyio
async def test_a_failed_staffing_lookup_offers_slots_as_before(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(*args: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(repo, "get_staffing", broken)
    conversation_id = await converse(client, living_in("Salamanca, Madrid"))
    assert (await row(client, conversation_id))["status"] == "in_progress"  # slots offered
    assert f"staffing lookup failed (conversation {conversation_id})" in caplog.text
