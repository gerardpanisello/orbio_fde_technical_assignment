"""Zone staffing (spec 015): occupancy per served area, and the live score built on it.

The engine never reads staffing (ADR 0002/0005). This module is the caller's side: it
turns `zone_staffing` rows into the two engine inputs, `occupancy` (for the score) and
`zone_full` (for the scheduling decision), and re-prices stored scores for the dashboard.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.models import Conversation, ZoneStaffing
from sazon_screening.config import EngineConfig, ZoneStaffingConfig
from sazon_screening.engine import CandidateRecord, ConversationState, ScoreResult
from sazon_screening.engine import with_zone_demand as reprice
from sazon_screening.vocab import Status


def occupancy_ratio(target: int, current: int) -> float:
    """current / target. A target of 0 means "we need nobody here": the area counts as full."""
    return current / target if target > 0 else 1.0


def occupancy_pct(ratio: float) -> int:
    """Rounded down, like the score factor, so 99.6 % never reads as "100 % (full)"."""
    return math.floor(ratio * 100)


@dataclass(frozen=True)
class Staffing:
    """A snapshot of every area's staffing; areas without a row have no data."""

    rows: Mapping[str, ZoneStaffing]

    def ratio(self, area_id: str | None) -> float | None:
        row = self.rows.get(area_id) if area_id else None
        return occupancy_ratio(row.target_drivers, row.current_drivers) if row else None

    def is_full(self, area_id: str | None) -> bool:
        """At or above 100 % of target. No data is never full (AC-5)."""
        ratio = self.ratio(area_id)
        return ratio is not None and ratio >= 1.0


async def load_staffing(session: AsyncSession) -> Staffing:
    return Staffing({row.area_id: row for row in await repo.list_staffing(session)})


async def seed_staffing(session: AsyncSession, seed: ZoneStaffingConfig, now: datetime) -> bool:
    """Insert the config seed only when the table is empty (FR-1). True if it inserted."""
    if not await repo.staffing_is_empty(session):
        return False
    for area_id, values in seed.areas.items():
        repo.add(
            session,
            ZoneStaffing(
                area_id=area_id,
                target_drivers=values.target_drivers,
                current_drivers=values.current_drivers,
                updated_at=now,
            ),
        )
    return True


def area_of_state(state: ConversationState) -> str | None:
    location = state.profile.location.value
    return location.area_id if location is not None else None


def area_of_row(row: Conversation) -> str | None:
    """Same rule as `LocationValue.area_id`: the zone, or the city served as a whole."""
    return row.zone or row.city


def live_score(
    record: CandidateRecord, area_id: str | None, staffing: Staffing, config: EngineConfig
) -> ScoreResult | None:
    """The stored (at-close) score with the zone-demand factor at today's occupancy (FR-6)."""
    if record.score is None:
        return None
    return reprice(record.score, config, occupancy=staffing.ratio(area_id))


# Qualified candidates per area, shown on the "Zonas" page (FR-7).
PIPELINE_STATUSES: Sequence[Status] = (
    Status.qualified_unscheduled,
    Status.interview_scheduled,
    Status.waitlisted,
)
