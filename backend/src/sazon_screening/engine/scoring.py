"""Soft scoring (FR-30, ADR 0004): ranks qualified candidates, never rejects anyone.

Every point is explained: the result lists six factors, in a fixed order, each with the
field, the value it was computed from, the points and a reason code; the score is their
sum. Weights and bucket thresholds come only from `config/screening.yaml`.

The sixth factor, zone demand (spec 015), depends on how staffed the candidate's area is.
Staffing changes after the conversation, so it is an *input* (`occupancy`), never read
here: the caller looks it up, and `with_zone_demand` re-prices a stored score with the
current occupancy without touching the other factors.
"""

import math
from datetime import date

from pydantic import BaseModel, ConfigDict

from sazon_screening.config import EngineConfig
from sazon_screening.config.models import ScoringConfig
from sazon_screening.engine.state import Profile
from sazon_screening.vocab import (
    Bucket,
    FactorReason,
    FieldName,
    FieldStatus,
    ScheduleSlot,
)


class ScoreFactor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: FieldName
    value: str | int | list[str] | None
    points: int
    reason_code: FactorReason


class ScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: int
    bucket: Bucket
    factors: list[ScoreFactor]
    max_score: int


def score_candidate(
    profile: Profile,
    config: EngineConfig,
    *,
    reference_date: date,
    occupancy: float | None = None,
) -> ScoreResult:
    """Score from soft fields only. `reference_date` is injected (the last turn's `today`).

    `occupancy` is the candidate's area staffing as current / target (0.45 = 45 %), or
    None when the area has no staffing data: then the zone-demand factor scores 0.
    """
    weights = config.screening.scoring
    factors = [
        *_experience_factors(profile, weights),
        _availability_factor(profile, weights),
        _schedule_factor(profile, weights),
        _start_date_factor(profile, weights, reference_date),
        _zone_demand_factor(profile.location.status, weights, occupancy),
    ]
    return _result(factors, weights)


def with_zone_demand(
    result: ScoreResult, config: EngineConfig, *, occupancy: float | None
) -> ScoreResult:
    """The same score with the zone-demand factor re-priced at `occupancy` (spec 015 FR-6).

    The other factors are kept as computed at the time (e.g. start-date proximity is
    relative to the conversation, not to today). A score stored before spec 015 has no
    zone factor: one is added. An unknown location stays unknown.
    """
    weights = config.screening.scoring
    others = [f for f in result.factors if not _is_zone_factor(f)]
    previous = next((f for f in result.factors if _is_zone_factor(f)), None)
    location_unknown = previous is not None and previous.reason_code is FactorReason.unknown
    status = FieldStatus.unclear if location_unknown else FieldStatus.valid
    return _result([*others, _zone_demand_factor(status, weights, occupancy)], weights)


def _result(factors: list[ScoreFactor], weights: ScoringConfig) -> ScoreResult:
    score = sum(factor.points for factor in factors)
    return ScoreResult(
        score=score,
        bucket=_bucket(score, weights),
        factors=factors,
        max_score=weights.max_score,
    )


def _unknown(name: FieldName) -> ScoreFactor:
    return ScoreFactor(field=name, value=None, points=0, reason_code=FactorReason.unknown)


def _experience_factors(profile: Profile, weights: ScoringConfig) -> list[ScoreFactor]:
    slot = profile.experience
    if slot.status is not FieldStatus.valid or slot.value is None:
        return [_unknown(FieldName.experience), _unknown(FieldName.experience)]
    years, platforms = slot.value.years, slot.value.platforms
    known = [p for p in platforms if not p.startswith("other:")]  # unknown platforms: 0 points
    per_year, per_platform = weights.experience_years, weights.platforms
    platform_points = len(known) * per_platform.points_per_known_platform
    return [
        ScoreFactor(
            field=FieldName.experience,
            value=years,
            points=min(years * per_year.points_per_year, per_year.max_points),
            reason_code=FactorReason.years_of_experience,
        ),
        ScoreFactor(
            field=FieldName.experience,
            value=list(platforms),
            points=min(platform_points, per_platform.max_points),
            reason_code=FactorReason.known_platforms,
        ),
    ]


def _availability_factor(profile: Profile, weights: ScoringConfig) -> ScoreFactor:
    slot = profile.availability
    if slot.status is not FieldStatus.valid or slot.value is None:
        return _unknown(FieldName.availability)
    raw = sum(weights.availability.points_for(option) for option in slot.value)
    return ScoreFactor(
        field=FieldName.availability,
        value=[option.value for option in slot.value],
        points=min(raw, weights.availability.max_points),
        reason_code=FactorReason.availability_breadth,
    )


def _schedule_factor(profile: Profile, weights: ScoringConfig) -> ScoreFactor:
    slot = profile.schedule
    if slot.status is not FieldStatus.valid or slot.value is None:
        return _unknown(FieldName.schedule)
    rule = weights.schedule
    flexible = ScheduleSlot.flexible in slot.value  # "whenever you need me" beats any list
    raw = rule.flexible if flexible else rule.per_slot * len(slot.value)
    return ScoreFactor(
        field=FieldName.schedule,
        value=[option.value for option in slot.value],
        points=min(raw, rule.max_points),
        reason_code=FactorReason.schedule_flexibility,
    )


def _start_date_factor(
    profile: Profile, weights: ScoringConfig, reference_date: date
) -> ScoreFactor:
    slot = profile.start_date
    if slot.status is not FieldStatus.valid or slot.value is None:
        return _unknown(FieldName.start_date)
    days = max(0, (slot.value - reference_date).days)
    band_points = next((b.points for b in weights.start_date if days <= b.within_days), 0)
    return ScoreFactor(
        field=FieldName.start_date,
        value=slot.value.isoformat(),
        points=band_points,
        reason_code=FactorReason.start_date_proximity,
    )


def _zone_demand_factor(
    location_status: FieldStatus, weights: ScoringConfig, occupancy: float | None
) -> ScoreFactor:
    """Points for how short-staffed the area is; no staffing data means no bonus (AC-5)."""
    if location_status is not FieldStatus.valid:
        return _unknown(FieldName.location)
    if occupancy is None:
        return ScoreFactor(
            field=FieldName.location, value=None, points=0, reason_code=FactorReason.zone_demand
        )
    pct = max(0.0, occupancy) * 100
    band_points = next((b.points for b in weights.zone_demand if pct < b.below_pct), 0)
    return ScoreFactor(
        field=FieldName.location,
        value=math.floor(pct),  # shown as "45% cubierta"; floor keeps it under the band edge
        points=band_points,
        reason_code=FactorReason.zone_demand,
    )


def _is_zone_factor(factor: ScoreFactor) -> bool:
    return factor.field is FieldName.location


def _bucket(score: int, weights: ScoringConfig) -> Bucket:
    if score >= weights.buckets.high:
        return Bucket.high
    if score >= weights.buckets.medium:
        return Bucket.medium
    return Bucket.low
