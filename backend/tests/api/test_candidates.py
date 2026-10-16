"""T5: the recruiter dashboard endpoints (AC-5..AC-7, AC-10)."""

import csv
import io
from typing import Any

import pytest
from httpx import AsyncClient

from sazon_screening.llm.client.base import Role
from sazon_screening.llm.client.fake import FakeLLMClient
from tests.api.conftest import HAPPY_PATH

MEXICO = [
    "sí, acepto",
    "Me llamo Ana López",
    "tengo 25",
    "moto",
    "sí",
    "vivo en Coyoacán, CDMX",
    "medio tiempo",
    "noches",
    "ninguna",
    "en 3 semanas",
    "sí",
    "2",
]
UNDER_AGE = ["sí", "Me llamo Hugo Sanz", "tengo 16"]
OPTED_OUT = ["sí", "Me llamo Iván Mora", "tengo 31", "no me interesa, dame de baja"]


async def converse(client: AsyncClient, texts: list[str], **start: Any) -> str:
    created = await client.post("/api/conversations", json=start)
    conversation_id: str = created.json()["id"]
    for text in texts:
        response = await client.post(
            f"/api/conversations/{conversation_id}/messages", json={"text": text}
        )
        assert response.status_code == 200
    return conversation_id


@pytest.fixture
async def ids(client: AsyncClient) -> dict[str, str]:
    """Four candidates, created in this order (so `-updated` lists them in reverse)."""
    return {
        "lucia": await converse(client, HAPPY_PATH),
        "ana": await converse(client, MEXICO, country_hint="MX"),
        "hugo": await converse(client, UNDER_AGE),
        "ivan": await converse(client, OPTED_OUT),
    }


@pytest.mark.anyio
async def test_a_month_level_start_date_is_marked_approximate(client: AsyncClient) -> None:
    """ "el mes que viene" is stored as the 1st; the dashboard must show the month only."""
    texts = [("el mes que viene" if text == "en 3 semanas" else text) for text in MEXICO]
    conversation_id = await converse(client, texts, country_hint="MX")
    rows = {row["id"]: row for row in (await client.get("/api/candidates")).json()}
    row = rows[conversation_id]
    assert (row["start_date"], row["start_date_approximate"]) == ("2026-11-01", True)


async def names(client: AsyncClient, **params: str) -> list[str | None]:
    response = await client.get("/api/candidates", params=params)
    assert response.status_code == 200
    return [row["full_name"] for row in response.json()]


@pytest.mark.anyio
@pytest.mark.ac("004:AC-5")
async def test_list_rows_carry_what_the_dashboard_shows(
    client: AsyncClient, ids: dict[str, str]
) -> None:
    rows = {row["id"]: row for row in (await client.get("/api/candidates")).json()}
    lucia = rows[ids["lucia"]]
    assert lucia["status"] == "interview_scheduled"
    assert (lucia["city"], lucia["zone"], lucia["country"]) == ("madrid", "mad-chamberi", "ES")
    assert lucia["availability"] == ["full_time"]
    assert lucia["experience_years"] == 3
    assert lucia["platforms"] == ["glovo"]
    assert lucia["start_date"] == "2026-10-19"
    assert lucia["start_date_approximate"] is False
    assert lucia["interview_slot"] == "2026-10-13T10:00"
    assert lucia["recruiter_status"] == "new"
    assert lucia["bucket"] in ("high", "medium", "low")
    assert rows[ids["hugo"]]["disqualification_reason"] == "under_age"


@pytest.mark.anyio
@pytest.mark.ac("004:AC-5")
async def test_list_filters_and_sorts(client: AsyncClient, ids: dict[str, str]) -> None:
    assert await names(client) == [None, "Hugo Sanz", "Ana López", "Lucía Martín"]  # -updated
    assert await names(client, sort="updated") == ["Lucía Martín", "Ana López", "Hugo Sanz", None]
    assert await names(client, status="interview_scheduled", sort="created") == [
        "Lucía Martín",
        "Ana López",
    ]
    assert await names(client, city="cdmx") == ["Ana López"]
    assert await names(client, country="MX") == ["Ana López"]
    assert await names(client, q="LÓP") == ["Ana López"]

    rows = (await client.get("/api/candidates", params={"sort": "-score"})).json()
    scores = [row["score"] for row in rows]
    scored = [s for s in scores if s is not None]
    assert scored == sorted(scored, reverse=True)
    assert scores[len(scored) :] == [None] * (len(scores) - len(scored))  # unscored last
    bucket = rows[0]["bucket"]
    assert rows[0]["full_name"] in await names(client, bucket=bucket)


@pytest.mark.anyio
@pytest.mark.ac("004:AC-5")
async def test_bad_filter_values_are_422(client: AsyncClient) -> None:
    assert (await client.get("/api/candidates", params={"status": "hired"})).status_code == 422
    assert (await client.get("/api/candidates", params={"sort": "name"})).status_code == 422


@pytest.mark.anyio
@pytest.mark.ac("004:AC-5")
async def test_export_csv_has_a_header_and_one_row_per_candidate(
    client: AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.get("/api/candidates/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert {row["id"] for row in rows} == set(ids.values())
    assert response.text.splitlines()[0].startswith("id,full_name,")
    filtered = await client.get("/api/candidates/export.csv", params={"status": "disqualified"})
    assert len(list(csv.DictReader(io.StringIO(filtered.text)))) == 1


@pytest.mark.anyio
@pytest.mark.ac("004:AC-6")
async def test_detail_has_record_summary_transcript_and_traces(
    client: AsyncClient, ids: dict[str, str]
) -> None:
    response = await client.get(f"/api/candidates/{ids['lucia']}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["record"]["status"] == "interview_scheduled"
    assert detail["summary"]["language"] == "es"
    assert detail["summary"]["text"]
    assert len(detail["transcript"]) == 1 + 2 * len(HAPPY_PATH)
    assert len(detail["traces"]) == 1 + len(HAPPY_PATH)
    trace = detail["traces"][-1]
    assert trace["action"] == "confirm_interview"
    assert trace["client"] == "fake-rules"
    assert trace["fallback"] is False
    assert detail["actions"] == []
    assert (await client.get("/api/candidates/nope")).status_code == 404


@pytest.mark.anyio
@pytest.mark.ac("004:AC-6")
async def test_english_summary_is_generated_once_then_served_from_the_db(
    client: AsyncClient, ids: dict[str, str], fake_client: FakeLLMClient
) -> None:
    def summary_calls() -> int:
        return sum(1 for call in fake_client.calls if call.role is Role.summary)

    before = summary_calls()
    first = await client.get(f"/api/candidates/{ids['hugo']}/summary", params={"lang": "en"})
    assert first.status_code == 200
    assert first.json()["language"] == "en"
    assert summary_calls() == before + 1
    second = await client.get(f"/api/candidates/{ids['hugo']}/summary", params={"lang": "en"})
    assert second.json() == first.json()
    assert summary_calls() == before + 1  # no new LLM call


@pytest.mark.anyio
@pytest.mark.ac("004:AC-6")
async def test_no_summary_while_the_conversation_runs(client: AsyncClient) -> None:
    conversation_id = await converse(client, ["sí"])
    response = await client.get(f"/api/candidates/{conversation_id}/summary")
    assert response.status_code == 409
    assert (await client.get("/api/candidates/nope/summary")).status_code == 404


@pytest.mark.anyio
@pytest.mark.ac("004:AC-7")
async def test_actions_are_stored_in_order_and_override_shortlists(
    client: AsyncClient, ids: dict[str, str]
) -> None:
    url = f"/api/candidates/{ids['hugo']}/actions"
    for body in (
        {"action": "note", "note": "Says he turns 18 next month"},
        {"action": "reject"},
        {"action": "override", "note": "Birthday is tomorrow, checked ID"},
    ):
        response = await client.post(url, json=body)
        assert response.status_code == 201, response.text
    detail = (await client.get(f"/api/candidates/{ids['hugo']}")).json()
    assert [a["action"] for a in detail["actions"]] == ["note", "reject", "override"]
    assert detail["candidate"]["recruiter_status"] == "shortlisted"
    assert detail["candidate"]["recruiter_override"] is True
    assert detail["candidate"]["status"] == "disqualified"  # the agent's outcome is kept


@pytest.mark.anyio
@pytest.mark.ac("004:AC-7")
async def test_shortlist_hire_and_the_rules_on_actions(
    client: AsyncClient, ids: dict[str, str]
) -> None:
    url = f"/api/candidates/{ids['lucia']}/actions"
    assert (await client.post(url, json={"action": "shortlist"})).status_code == 201
    assert (await client.post(url, json={"action": "hire"})).status_code == 201
    rows = (await client.get("/api/candidates", params={"recruiter_status": "hired"})).json()
    assert [row["id"] for row in rows] == [ids["lucia"]]
    assert (await client.post(url, json={"action": "override"})).status_code == 409
    assert (await client.post(url, json={"action": "note"})).status_code == 422  # no text
    assert (await client.post(url, json={"action": "promote"})).status_code == 422
    ivan = f"/api/candidates/{ids['ivan']}/actions"
    assert (await client.post(ivan, json={"action": "shortlist"})).status_code == 409
    missing = await client.post("/api/candidates/nope/actions", json={"action": "reject"})
    assert missing.status_code == 404


@pytest.mark.anyio
@pytest.mark.ac("004:AC-10")
async def test_opted_out_candidates_expose_no_pii(client: AsyncClient, ids: dict[str, str]) -> None:
    ivan = ids["ivan"]
    listed = (await client.get("/api/candidates")).text
    detail = await client.get(f"/api/candidates/{ivan}")
    exported = (await client.get("/api/candidates/export.csv")).text
    summary = await client.get(f"/api/candidates/{ivan}/summary")
    conversation = await client.get(f"/api/conversations/{ivan}")
    assert detail.json()["candidate"]["status"] == "opted_out"
    for text in (listed, detail.text, exported, summary.text, conversation.text):
        assert "Iván" not in text
        assert "Mora" not in text
