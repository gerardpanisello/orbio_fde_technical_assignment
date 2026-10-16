"""Spec 010 T2: the database-backed slot provider (FR-1, FR-2)."""

from datetime import UTC, datetime

import pytest

from sazon_screening.api import repo
from sazon_screening.api.db import Sessions
from sazon_screening.api.models import InterviewBooking
from sazon_screening.api.service import ScreeningService
from sazon_screening.api.slots import load_slot_provider
from sazon_screening.config import EngineConfig
from sazon_screening.vocab import Language
from tests.api.test_bookings import _conversation
from tests.paths import SHIPPED_CONFIG_DIR

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)  # Tuesday 10:00 in Madrid


async def test_availability_is_seeded_once_and_never_overwritten(
    service: ScreeningService, sessions: Sessions
) -> None:
    async with sessions.begin() as session:
        madrid = await repo.get_availability(session, "madrid")
        assert madrid is not None
        assert madrid.capacity == 3  # from interview_slots.yaml
        madrid.capacity = 7  # a recruiter's edit
    assert await service.init_interview_availability() == []  # every city has a row
    async with sessions() as session:
        madrid = await repo.get_availability(session, "madrid")
        assert madrid is not None
        assert madrid.capacity == 7
        assert len(await repo.list_availability(session)) == 9


@pytest.mark.ac("010:AC-1")
async def test_offer_reads_the_city_agenda_and_skips_full_slots(
    service: ScreeningService, sessions: Sessions
) -> None:
    async with sessions() as session:
        offered = await service.slots.offer(session, "malaga", NOW)  # capacity 1
    assert [s.id for s in offered] == [
        "malaga:2026-10-14T10:00",
        "malaga:2026-10-15T17:00",
        "malaga:2026-10-16T10:00",
    ]
    assert offered[0].place is not None
    assert "malaga" in offered[0].place
    async with sessions.begin() as session:
        repo.add(session, _conversation("other", NOW))
        repo.add(session, _booking("malaga:2026-10-15T17:00", "malaga"))
    async with sessions() as session:
        offered = await service.slots.offer(session, "malaga", NOW)
    assert "malaga:2026-10-15T17:00" not in [s.id for s in offered]
    assert [s.id for s in offered][1] == "malaga:2026-10-15T10:00"


async def test_cancelled_bookings_free_their_seat(
    service: ScreeningService, sessions: Sessions
) -> None:
    async with sessions.begin() as session:
        repo.add(session, _conversation("other", NOW))
        repo.add(session, _booking("malaga:2026-10-14T10:00", "malaga", status="cancelled"))
    async with sessions() as session:
        offered = await service.slots.offer(session, "malaga", NOW)
    assert offered[0].id == "malaga:2026-10-14T10:00"


async def test_unknown_city_offers_nothing(service: ScreeningService, sessions: Sessions) -> None:
    async with sessions() as session:
        assert await service.slots.offer(session, "atlantis", NOW) == []


async def test_describe_labels_known_ids_and_skips_others(
    service: ScreeningService, sessions: Sessions
) -> None:
    async with sessions() as session:
        shown = await service.slots.describe(session, ["cdmx:2026-10-20T10:00", "s1"])
    assert [s.id for s in shown] == ["cdmx:2026-10-20T10:00"]
    assert shown[0].label(Language.es) == "martes 20/10, 10:00"


def test_preview_needs_no_database(shipped_config: EngineConfig) -> None:
    provider = load_slot_provider(SHIPPED_CONFIG_DIR, shipped_config.service_areas)
    assert len(provider.preview("madrid", NOW)) == 3
    assert provider.preview("atlantis", NOW) == []


def _booking(slot_id: str, city: str, *, status: str = "booked") -> InterviewBooking:
    starts = datetime(2026, 10, 15, 15, 0, tzinfo=UTC)
    return InterviewBooking(
        conversation_id="other",
        slot_id=slot_id,
        city=city,
        starts_at=starts,
        duration_min=30,
        place="x",
        seat=0,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )
