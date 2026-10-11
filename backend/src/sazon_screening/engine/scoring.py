"""Soft scoring (FR-30, ADR 0004): ranks qualified candidates, never rejects anyone.

Every point is explained: the result lists five factors, in a fixed order, each with the
field, the value it was computed from, the points and a reason code; the score is their
sum. Weights and bucket thresholds come only from `config/screening.yaml`.
"""

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


def score_candidate(profile: Profile, config: EngineConfig, *, reference_date: date) -> ScoreResult:
    """Score from soft fields only. `reference_date` is injected (the last turn's `today`)."""
    weights = config.screening.scoring
    factors = [
        *_experience_factors(profile, weights),
        _availability_factor(profile, weights),
        _schedule_factor(profile, weights),
        _start_date_factor(profile, weights, reference_date),
    ]
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


def _bucket(score: int, weights: ScoringConfig) -> Bucket:
    if score >= weights.buckets.high:
        return Bucket.high
    if score >= weights.buckets.medium:
        return Bucket.medium
    return Bucket.low
