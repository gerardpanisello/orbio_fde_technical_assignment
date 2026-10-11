"""T27: explainable soft scoring from config weights (FR-30, NFR-6)."""

from datetime import date, timedelta

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.enums import (
    Availability,
    Bucket,
    FactorReason,
    FieldName,
    FieldStatus,
    ScheduleSlot,
)
from sazon_screening.engine.scoring import ScoreFactor, score_candidate
from sazon_screening.engine.state import Experience, Profile, Slot
from tests.engine.conftest import TODAY, MakeConfig


def profile(
    *,
    years: int = 3,
    platforms: tuple[str, ...] = ("glovo",),
    availability: tuple[Availability, ...] = (Availability.full_time, Availability.weekends),
    schedule: tuple[ScheduleSlot, ...] = (ScheduleSlot.flexible,),
    start_in_days: int = 0,
) -> Profile:
    """The AC-33 candidate by default: 3 years, glovo, {full_time, weekends}, flexible, asap."""
    p = Profile()
    p.experience = Slot(
        status=FieldStatus.valid, value=Experience(years=years, platforms=list(platforms))
    )
    p.availability = Slot(status=FieldStatus.valid, value=list(availability))
    p.schedule = Slot(status=FieldStatus.valid, value=list(schedule))
    p.start_date = Slot(status=FieldStatus.valid, value=TODAY + timedelta(days=start_in_days))
    return p


def points(result_factors: list[ScoreFactor]) -> list[int]:
    return [factor.points for factor in result_factors]


@pytest.mark.ac("AC-33")
def test_score_is_the_sum_of_explained_factors(config: EngineConfig) -> None:
    result = score_candidate(profile(), config, reference_date=TODAY)
    assert result.factors == [
        ScoreFactor(
            field=FieldName.experience,
            value=3,
            points=15,
            reason_code=FactorReason.years_of_experience,
        ),
        ScoreFactor(
            field=FieldName.experience,
            value=["glovo"],
            points=10,
            reason_code=FactorReason.known_platforms,
        ),
        ScoreFactor(
            field=FieldName.availability,
            value=["full_time", "weekends"],
            points=22,
            reason_code=FactorReason.availability_breadth,
        ),
        ScoreFactor(
            field=FieldName.schedule,
            value=["flexible"],
            points=15,
            reason_code=FactorReason.schedule_flexibility,
        ),
        ScoreFactor(
            field=FieldName.start_date,
            value="2026-10-12",
            points=20,
            reason_code=FactorReason.start_date_proximity,
        ),
    ]
    assert result.score == sum(points(result.factors)) == 82
    assert result.bucket == Bucket.high
    assert result.max_score == 100


@pytest.mark.ac("AC-33")
def test_unclear_field_scores_zero_with_reason_unknown(config: EngineConfig) -> None:
    p = profile()
    p.availability = Slot(status=FieldStatus.unclear)
    result = score_candidate(p, config, reference_date=TODAY)
    factor = result.factors[2]
    assert (factor.field, factor.value, factor.points, factor.reason_code) == (
        FieldName.availability,
        None,
        0,
        FactorReason.unknown,
    )
    assert result.score == sum(points(result.factors)) == 60


def test_missing_experience_is_unknown_for_both_factors(config: EngineConfig) -> None:
    p = profile()
    p.experience = Slot(status=FieldStatus.not_asked)
    result = score_candidate(p, config, reference_date=TODAY)
    assert [f.reason_code for f in result.factors[:2]] == [FactorReason.unknown] * 2


@pytest.mark.ac("AC-34")
def test_weights_come_from_config(config: EngineConfig, make_config: MakeConfig) -> None:
    lighter = make_config(
        screening={
            "scoring": {
                "experience_years": {"points_per_year": 1, "max_points": 20},
                "buckets": {"high": 90, "medium": 70},
            }
        }
    )
    before = score_candidate(profile(), config, reference_date=TODAY)
    after = score_candidate(profile(), lighter, reference_date=TODAY)
    assert (before.score, before.bucket) == (82, Bucket.high)
    assert (after.score, after.bucket) == (70, Bucket.medium)


def test_caps_are_respected(config: EngineConfig) -> None:
    result = score_candidate(
        profile(
            years=30,
            platforms=("glovo", "uber_eats", "rappi", "deliveroo"),
            availability=tuple(Availability),
            schedule=(ScheduleSlot.morning, ScheduleSlot.afternoon, ScheduleSlot.evening),
        ),
        config,
        reference_date=TODAY,
    )
    assert points(result.factors) == [20, 20, 25, 15, 20]
    assert result.score == result.max_score == 100


def test_unknown_platforms_score_zero(config: EngineConfig) -> None:
    result = score_candidate(
        profile(platforms=("other:Rappi Turbo",)), config, reference_date=TODAY
    )
    assert result.factors[1].points == 0
    assert result.factors[1].value == ["other:Rappi Turbo"]


def test_schedule_without_flexible_scores_per_slot(config: EngineConfig) -> None:
    result = score_candidate(
        profile(schedule=(ScheduleSlot.morning, ScheduleSlot.evening)),
        config,
        reference_date=TODAY,
    )
    assert result.factors[3].points == 10


@pytest.mark.parametrize(
    ("days", "expected"), [(0, 20), (3, 20), (4, 10), (14, 10), (15, 5), (30, 5), (31, 0)]
)
def test_start_date_bands(config: EngineConfig, days: int, expected: int) -> None:
    result = score_candidate(profile(start_in_days=days), config, reference_date=TODAY)
    assert result.factors[4].points == expected


def test_start_before_reference_counts_as_now(config: EngineConfig) -> None:
    result = score_candidate(profile(), config, reference_date=date(2026, 10, 20))
    assert result.factors[4].points == 20


@pytest.mark.parametrize(
    ("candidate", "score", "bucket"),
    [
        (profile(), 82, Bucket.high),
        (profile(years=0, platforms=(), start_in_days=4), 47, Bucket.medium),
        (
            profile(
                years=0,
                platforms=(),
                availability=(Availability.part_time,),
                schedule=(ScheduleSlot.morning,),
                start_in_days=31,
            ),
            13,
            Bucket.low,
        ),
    ],
)
def test_bucket_thresholds(
    config: EngineConfig, candidate: Profile, score: int, bucket: Bucket
) -> None:
    result = score_candidate(candidate, config, reference_date=TODAY)
    assert (result.score, result.bucket) == (score, bucket)
