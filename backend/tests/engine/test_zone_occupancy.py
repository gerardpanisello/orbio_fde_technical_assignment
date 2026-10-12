"""Spec 015: zone demand in the score, and the waitlist when the area is full.

The engine never looks staffing up: occupancy (for the score) and `zone_full` (for the
scheduling decision) are inputs, so every rule here is tested without a database.
"""

import pytest

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import ClosedAck, CloseOptedOut, CloseWaitlisted, OfferSlots
from sazon_screening.engine.record import build_record
from sazon_screening.engine.scoring import ScoreFactor, score_candidate, with_zone_demand
from sazon_screening.engine.state import Profile
from sazon_screening.vocab import Bucket, FactorReason, FieldName, FieldStatus, Stage, Status
from tests.engine.builders import OFFERED_SLOTS, Convo, yes
from tests.engine.conftest import TODAY, MakeConfig
from tests.engine.test_scoring import profile


def zone_factor(occupancy: float | None, config: EngineConfig) -> ScoreFactor:
    result = score_candidate(profile(), config, reference_date=TODAY, occupancy=occupancy)
    return result.factors[-1]


def unclear_location() -> Profile:
    p = profile()
    p.location.status = FieldStatus.unclear
    return p


class TestZoneDemandFactor:
    @pytest.mark.ac("015:AC-1")
    def test_short_staffed_area_scores_higher_with_its_reason(self, config: EngineConfig) -> None:
        candidate = profile(years=0, platforms=(), start_in_days=4)  # 47 points, medium
        short = score_candidate(candidate, config, reference_date=TODAY, occupancy=0.40)
        almost_full = score_candidate(candidate, config, reference_date=TODAY, occupancy=0.90)
        assert short.score > almost_full.score
        assert short.factors[-1] == ScoreFactor(
            field=FieldName.location, value=40, points=20, reason_code=FactorReason.zone_demand
        )
        assert almost_full.factors[-1] == ScoreFactor(
            field=FieldName.location, value=90, points=5, reason_code=FactorReason.zone_demand
        )
        assert (short.score, short.bucket) == (67, Bucket.high)
        assert (almost_full.score, almost_full.bucket) == (52, Bucket.medium)

    @pytest.mark.parametrize(
        ("occupancy", "value", "points"),
        [
            (0.0, 0, 20),
            (0.4999, 49, 20),
            (0.5, 50, 12),
            (0.79, 79, 12),
            (0.8, 80, 5),
            (0.99, 99, 5),
            (1.0, 100, 0),
            (1.3, 130, 0),
        ],
    )
    def test_bands_first_fit_wins(
        self, config: EngineConfig, occupancy: float, value: int, points: int
    ) -> None:
        factor = zone_factor(occupancy, config)
        assert (factor.value, factor.points) == (value, points)

    @pytest.mark.ac("015:AC-5")
    def test_no_staffing_data_means_no_bonus(self, config: EngineConfig) -> None:
        factor = zone_factor(None, config)
        assert (factor.value, factor.points, factor.reason_code) == (
            None,
            0,
            FactorReason.zone_demand,
        )

    def test_unclear_location_is_unknown(self, config: EngineConfig) -> None:
        result = score_candidate(unclear_location(), config, reference_date=TODAY, occupancy=0.1)
        assert (result.factors[-1].points, result.factors[-1].reason_code) == (
            0,
            FactorReason.unknown,
        )

    def test_bands_come_from_config(self, make_config: MakeConfig) -> None:
        band = {"below_pct": 100, "points": 3}
        flat = make_config(screening={"scoring": {"zone_demand": [band]}})
        assert zone_factor(0.1, flat).points == 3
        off = make_config(screening={"scoring": {"zone_demand": []}})
        assert zone_factor(0.1, off).points == 0
        assert off.screening.scoring.max_score == 100


class TestLiveRepricing:
    @pytest.mark.ac("015:AC-2")
    def test_repricing_changes_only_the_zone_factor(self, config: EngineConfig) -> None:
        at_close = score_candidate(profile(), config, reference_date=TODAY, occupancy=0.9)
        live = with_zone_demand(at_close, config, occupancy=0.3)
        assert live.factors[:-1] == at_close.factors[:-1]
        assert live.score == at_close.score - 5 + 20
        assert at_close.score == 87  # the stored score is untouched

    def test_bucket_is_recomputed(self, config: EngineConfig) -> None:
        candidate = profile(years=0, platforms=(), start_in_days=4)  # 47, medium
        at_close = score_candidate(candidate, config, reference_date=TODAY, occupancy=1.0)
        assert at_close.bucket is Bucket.medium
        assert with_zone_demand(at_close, config, occupancy=0.2).bucket is Bucket.high

    def test_score_stored_before_spec_015_gets_a_zone_factor(self, config: EngineConfig) -> None:
        old = score_candidate(profile(), config, reference_date=TODAY)
        old = old.model_copy(update={"factors": old.factors[:-1]})  # five factors, as stored
        live = with_zone_demand(old, config, occupancy=0.4)
        assert len(live.factors) == 6
        assert live.factors[-1].points == 20

    def test_unknown_location_stays_unknown(self, config: EngineConfig) -> None:
        at_close = score_candidate(unclear_location(), config, reference_date=TODAY)
        live = with_zone_demand(at_close, config, occupancy=0.1)
        assert live.factors[-1].reason_code is FactorReason.unknown
        assert live.score == at_close.score

    def test_record_score_uses_the_occupancy_given(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to_status(Status.qualified_unscheduled)
        without = build_record(c.state, config)
        with_data = build_record(c.state, config, occupancy=0.3)
        assert without.score is not None
        assert with_data.score is not None
        assert with_data.score.score == without.score.score + 20


def at_recap(config: EngineConfig) -> Convo:
    return Convo(config).advance_to(Stage.recap)


class TestWaitlist:
    @pytest.mark.ac("015:AC-3")
    def test_full_area_at_recap_confirmation_waitlists(self, config: EngineConfig) -> None:
        c = at_recap(config).say(yes(), offered_slots=OFFERED_SLOTS, zone_full=True)
        c.expect(CloseWaitlisted, area_id="cdmx-coyoacan").expect_status(Status.waitlisted)
        assert c.state.offered_slot_ids == []  # no slots offered
        assert c.state.selected_slot_id is None
        assert c.state.drop_off_stage is Stage.recap
        assert c.state.disqualification_reason is None  # never a rejection

    @pytest.mark.ac("015:AC-3")
    def test_area_with_room_offers_slots_as_before(self, config: EngineConfig) -> None:
        c = at_recap(config).say(yes(), offered_slots=OFFERED_SLOTS, zone_full=False)
        c.expect(OfferSlots, slot_ids=OFFERED_SLOTS).expect_status(Status.in_progress)

    @pytest.mark.ac("015:AC-5")
    def test_without_the_flag_nobody_is_waitlisted(self, config: EngineConfig) -> None:
        c = at_recap(config).say(yes(), offered_slots=OFFERED_SLOTS)  # default: not full
        c.expect(OfferSlots)

    def test_zone_full_is_ignored_before_scheduling(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to(Stage.availability).say(zone_full=True)
        c.expect_status(Status.in_progress)
        assert c.state.stage is Stage.availability

    def test_zone_full_is_ignored_while_slots_are_on_offer(self, config: EngineConfig) -> None:
        Convo(config).advance_to(Stage.scheduling).say(zone_full=True).expect_status(
            Status.in_progress
        )

    def test_opt_out_still_works_and_later_messages_get_closed_ack(
        self, config: EngineConfig
    ) -> None:
        c = Convo(config).advance_to_status(Status.waitlisted)
        c.say(faq_question=True).expect(ClosedAck).expect_status(Status.waitlisted)
        c.say(opt_out=True).expect(CloseOptedOut).expect_status(Status.opted_out)
        c.say(faq_question=True).expect(ClosedAck)

    def test_silence_on_a_waitlisted_candidate_sends_nothing(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to_status(Status.waitlisted).silence()
        assert c.action.primary.type == "no_message"
        c.expect_status(Status.waitlisted)

    def test_waitlisted_record_is_scored(self, config: EngineConfig) -> None:
        c = Convo(config).advance_to_status(Status.waitlisted)
        record = build_record(c.state, config, occupancy=1.2)
        assert record.status is Status.waitlisted
        assert record.score is not None
        assert (record.score.factors[-1].value, record.score.factors[-1].points) == (120, 0)
