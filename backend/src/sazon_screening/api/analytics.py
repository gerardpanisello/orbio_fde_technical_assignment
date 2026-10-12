"""Funnel numbers for the dashboard (FR-11). The SQL is in repo; the arithmetic is here."""

from statistics import median

from sqlalchemy.ext.asyncio import AsyncSession

from sazon_screening.api import repo
from sazon_screening.api.models import Conversation
from sazon_screening.api.schemas import Analytics
from sazon_screening.vocab import DisqualificationReason, Status

# Reached an outcome a recruiter can act on. Not abandoned, opted out or still running.
FINISHED = (
    Status.interview_scheduled,
    Status.qualified_unscheduled,
    Status.disqualified,
    Status.needs_review,
)


async def build_analytics(session: AsyncSession) -> Analytics:
    statuses = await repo.count_by(session, Conversation.status)
    by_status = {Status(status): n for status, n in statuses.items() if status}
    total = sum(by_status.values())
    finished = sum(by_status.get(status, 0) for status in FINISHED)
    drop_off = await repo.count_by(
        session, Conversation.drop_off_stage, Conversation.status == Status.abandoned
    )
    reasons = await repo.count_by(
        session, Conversation.disqualification_reason, Conversation.status == Status.disqualified
    )
    durations = [
        (updated - created).total_seconds()
        for created, updated in await repo.durations(session, FINISHED)
    ]
    turns, fallbacks, cost = await repo.turn_totals(session)
    by_country: dict[str, dict[Status, int]] = {}
    for country, status, count in await repo.count_by_country_and_status(session):
        by_country.setdefault(country or "unknown", {})[Status(status)] = count
    return Analytics(
        total=total,
        by_status=by_status,
        finished=finished,
        completion_rate=_ratio(finished, total),
        drop_off_by_stage={stage: n for stage, n in drop_off.items() if stage},
        median_duration_s=median(durations) if durations else None,
        disqualification_reasons={
            DisqualificationReason(reason): n for reason, n in reasons.items() if reason
        },
        agent_turns=turns,
        fallback_rate=_ratio(fallbacks, turns),
        avg_cost_usd=round(cost / total, 6) if total else 0.0,
        by_country=by_country,
    )


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0
