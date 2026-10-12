"""T6: funnel analytics (AC-8)."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sazon_screening.api.service import ScreeningService
from sazon_screening.engine import SilenceExpired
from tests.api.conftest import HAPPY_PATH
from tests.api.test_candidates import UNDER_AGE, converse


@pytest.mark.anyio
@pytest.mark.ac("004:AC-8")
async def test_empty_database(client: AsyncClient) -> None:
    analytics = (await client.get("/api/analytics")).json()
    assert analytics["total"] == 0
    assert analytics["completion_rate"] == 0.0
    assert analytics["median_duration_s"] is None


@pytest.mark.anyio
@pytest.mark.ac("004:AC-8")
async def test_counts_rates_and_drop_off(client: AsyncClient, app: FastAPI) -> None:
    service: ScreeningService = app.state.service
    await converse(client, HAPPY_PATH)
    await converse(client, UNDER_AGE)
    abandoned = await converse(client, ["sí", "Me llamo Eva Gil"])
    await service.send_event(abandoned, SilenceExpired())
    await converse(client, ["sí"], country_hint="MX")  # still in progress

    analytics = (await client.get("/api/analytics")).json()
    assert analytics["total"] == 4
    assert sum(analytics["by_status"].values()) == analytics["total"]
    assert analytics["by_status"] == {
        "interview_scheduled": 1,
        "disqualified": 1,
        "abandoned": 1,
        "in_progress": 1,
    }
    assert analytics["finished"] == 2
    assert analytics["completion_rate"] == 0.5
    assert analytics["drop_off_by_stage"] == {"age": 1}
    assert analytics["disqualification_reasons"] == {"under_age": 1}
    assert analytics["median_duration_s"] > 0
    assert analytics["fallback_rate"] == 0.0
    assert analytics["agent_turns"] > 0
    assert analytics["avg_cost_usd"] == 0.0  # the fake costs nothing
    assert analytics["by_country"] == {
        "ES": {"interview_scheduled": 1},
        "MX": {"in_progress": 1},  # from the phone prefix
        "unknown": {"disqualified": 1, "abandoned": 1},  # stopped before the location
    }
