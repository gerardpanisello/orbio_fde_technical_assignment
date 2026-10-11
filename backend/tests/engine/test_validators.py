"""T9, T14, T15: field validators turn proposed values into Accepted / Rejected outcomes."""

from datetime import date

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.inputs import (
    UNCLEAR,
    AbsoluteDate,
    Asap,
    ExperienceAnswer,
    NextWeekday,
    Offset,
    StartDateExpr,
    Unclear,
)
from sazon_screening.engine.state import Experience
from sazon_screening.engine.validators import (
    Accepted,
    NeedsConfirmation,
    Rejected,
    resolve_start_date,
    validate_availability,
    validate_consent,
    validate_experience,
    validate_name,
    validate_schedule,
    validate_start_date,
)
from sazon_screening.vocab import Availability, Flag, ReaskReason, ScheduleSlot, Weekday

TYPO_APOSTROPHE = "\N{RIGHT SINGLE QUOTATION MARK}"  # what phone keyboards type


class TestConsent:
    @pytest.mark.parametrize("answer", [True, False])
    def test_explicit_answer_is_accepted(self, answer: bool) -> None:
        assert validate_consent(answer) == Accepted(answer)

    def test_unclear_requires_explicit_consent(self) -> None:
        assert validate_consent(UNCLEAR) == Rejected(ReaskReason.consent_required)


class TestName:
    @pytest.mark.parametrize(
        ("raw", "stored"),
        [
            ("Ana López", "Ana López"),
            ("María-José O'Neill", "María-José O'Neill"),
            ("José  Pérez ", "José Pérez"),
            (f"  Zoë   D{TYPO_APOSTROPHE}Angelo  Ruiz", f"Zoë D{TYPO_APOSTROPHE}Angelo Ruiz"),
        ],
    )
    def test_valid_names_are_accepted_with_spaces_collapsed(self, raw: str, stored: str) -> None:
        assert validate_name(raw, surname_requested=False) == Accepted(stored)

    @pytest.mark.parametrize("raw", ["Ana2 López", "Ana López!", "@ana lopez"])
    def test_digits_and_symbols_are_rejected(self, raw: str) -> None:
        assert validate_name(raw, surname_requested=False) == Rejected(
            ReaskReason.invalid_characters
        )

    @pytest.mark.ac("AC-15")
    def test_first_name_only_asks_for_surname_once(self) -> None:
        assert validate_name("Ana", surname_requested=False) == Rejected(
            ReaskReason.surname_missing
        )

    @pytest.mark.ac("AC-15")
    def test_first_name_only_is_accepted_with_flag_after_a_reask(self) -> None:
        assert validate_name("Ana", surname_requested=True) == Accepted(
            "Ana", flags=(Flag.surname_missing,)
        )

    @pytest.mark.parametrize("raw", [UNCLEAR, "", "   ", "- '"])
    def test_empty_or_unclear_is_rejected_as_unclear(self, raw: str | Unclear) -> None:
        assert validate_name(raw, surname_requested=False) == Rejected(ReaskReason.unclear)


class TestAvailabilityAndSchedule:
    def test_availability_is_deduplicated_in_enum_order(self) -> None:
        answer = [Availability.weekends, Availability.full_time, Availability.weekends]
        assert validate_availability(answer) == Accepted(
            [Availability.full_time, Availability.weekends]
        )

    def test_schedule_is_deduplicated_in_enum_order(self) -> None:
        answer = [ScheduleSlot.evening, ScheduleSlot.morning, ScheduleSlot.evening]
        assert validate_schedule(answer) == Accepted([ScheduleSlot.morning, ScheduleSlot.evening])

    def test_empty_availability_lists_every_option(self) -> None:
        assert validate_availability([]) == Rejected(
            ReaskReason.empty_selection, options=("full_time", "part_time", "weekends")
        )

    def test_empty_schedule_lists_every_option(self) -> None:
        assert validate_schedule([]) == Rejected(
            ReaskReason.empty_selection, options=("morning", "afternoon", "evening", "flexible")
        )

    @pytest.mark.ac("AC-18")
    def test_unclear_availability_lists_every_option(self) -> None:
        assert validate_availability(UNCLEAR) == Rejected(
            ReaskReason.unclear, options=("full_time", "part_time", "weekends")
        )

    def test_unclear_schedule_lists_every_option(self) -> None:
        assert validate_schedule(UNCLEAR) == Rejected(
            ReaskReason.unclear, options=("morning", "afternoon", "evening", "flexible")
        )


def check_experience(
    config: EngineConfig, answer: ExperienceAnswer | Unclear
) -> Accepted[Experience] | Rejected | NeedsConfirmation:
    return validate_experience(
        answer,
        platforms=config.screening.platforms,
        confirm_above=config.thresholds.experience_confirm_above_years,
    )


class TestExperience:
    def test_years_and_known_platforms(self, config: EngineConfig) -> None:
        outcome = check_experience(config, ExperienceAnswer(years=3, platforms=["Glovo"]))
        assert outcome == Accepted(Experience(years=3, platforms=["glovo"]))

    @pytest.mark.ac("AC-16")
    def test_more_than_40_years_needs_confirmation(self, config: EngineConfig) -> None:
        outcome = check_experience(config, ExperienceAnswer(years=45))
        assert outcome == NeedsConfirmation("value", value=Experience(years=45, platforms=[]))

    def test_exactly_40_years_is_accepted(self, config: EngineConfig) -> None:
        outcome = check_experience(config, ExperienceAnswer(years=40))
        assert outcome == Accepted(Experience(years=40, platforms=[]))

    @pytest.mark.ac("AC-16")
    def test_none_means_zero_years_and_no_platforms(self, config: EngineConfig) -> None:
        outcome = check_experience(config, ExperienceAnswer(years="none", platforms=["Glovo"]))
        assert outcome == Accepted(Experience(years=0, platforms=[]))

    def test_negative_years_are_reasked(self, config: EngineConfig) -> None:
        outcome = check_experience(config, ExperienceAnswer(years=-1))
        assert outcome == Rejected(ReaskReason.negative_value)

    def test_platforms_without_years_are_reasked(self, config: EngineConfig) -> None:
        # Plan OQ-5: the platforms are re-extracted with the next answer.
        outcome = check_experience(config, ExperienceAnswer(years=None, platforms=["Glovo"]))
        assert outcome == Rejected(ReaskReason.missing_years)

    def test_unclear_is_reasked(self, config: EngineConfig) -> None:
        assert check_experience(config, UNCLEAR) == Rejected(ReaskReason.unclear)

    @pytest.mark.ac("AC-16")
    @pytest.mark.parametrize(
        ("raw", "stored"),
        [
            (["Uber Eats"], ["uber_eats"]),
            (["UBEREATS", "uber"], ["uber_eats"]),
            (["uber_eats"], ["uber_eats"]),
            (["Rappi Turbo"], ["other:Rappi Turbo"]),
            (["  Rappi  Turbo "], ["other:Rappi Turbo"]),
            (["Didi", "Glovo", "Just-Eat"], ["didi_food", "glovo", "just_eat"]),
            (["", "Glovo"], ["glovo"]),
        ],
    )
    def test_platforms_normalised_to_config_ids(
        self, config: EngineConfig, raw: list[str], stored: list[str]
    ) -> None:
        outcome = check_experience(config, ExperienceAnswer(years=2, platforms=raw))
        assert outcome == Accepted(Experience(years=2, platforms=stored))


class TestStartDate:
    @pytest.mark.ac("AC-17")
    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            (NextWeekday(weekday=Weekday.mon), date(2026, 10, 19)),  # today is Monday: next one
            (NextWeekday(weekday=Weekday.wed), date(2026, 10, 14)),
            (NextWeekday(weekday=Weekday.sun), date(2026, 10, 18)),
            (Offset(amount=2, unit="weeks"), date(2026, 10, 26)),
            (Offset(amount=3, unit="days"), date(2026, 10, 15)),
            (Offset(amount=0, unit="days"), date(2026, 10, 12)),
            (Asap(), date(2026, 10, 12)),
            (AbsoluteDate(on=date(2026, 11, 2)), date(2026, 11, 2)),
            (AbsoluteDate(on=date(2026, 10, 12)), date(2026, 10, 12)),
        ],
    )
    def test_expression_resolves_against_today(
        self, today: date, expr: StartDateExpr, expected: date
    ) -> None:
        assert resolve_start_date(expr, today) == (expected, False)
        assert validate_start_date(expr, today) == Accepted(expected)

    @pytest.mark.ac("AC-17")
    def test_past_date_is_normalised_to_today_with_flag(self, today: date) -> None:
        expr = AbsoluteDate(on=date(2026, 9, 1))
        assert resolve_start_date(expr, today) == (today, True)
        assert validate_start_date(expr, today) == Accepted(
            today, flags=(Flag.start_date_normalised,)
        )

    @pytest.mark.ac("AC-17")
    def test_negative_offset_is_reasked(self, today: date) -> None:
        expr = Offset(amount=-1, unit="days")
        assert validate_start_date(expr, today) == Rejected(ReaskReason.negative_value)

    def test_absurd_offset_is_reasked_instead_of_raising(self, today: date) -> None:
        expr = Offset(amount=10**9, unit="weeks")
        assert validate_start_date(expr, today) == Rejected(ReaskReason.implausible_value)

    def test_unclear_is_reasked(self, today: date) -> None:
        assert validate_start_date(UNCLEAR, today) == Rejected(ReaskReason.unclear)
