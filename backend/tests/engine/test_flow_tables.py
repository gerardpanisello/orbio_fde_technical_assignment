"""T2: the static flow tables match the stage order of FR-5."""

from sazon_screening.engine.enums import FieldName, Stage
from sazon_screening.engine.flow import FIELD_ORDER, FIELD_STAGE, HARD_FIELDS, SOFT_FIELDS


def test_stage_enum_follows_fr5_order() -> None:
    assert list(Stage) == [
        Stage.consent,
        Stage.name,
        Stage.age,
        Stage.vehicle_license,
        Stage.location,
        Stage.availability,
        Stage.schedule,
        Stage.experience,
        Stage.start_date,
        Stage.recap,
        Stage.scheduling,
    ]


def test_field_order_walks_stages_in_order() -> None:
    stage_positions = [list(Stage).index(FIELD_STAGE[field]) for field in FIELD_ORDER]
    assert stage_positions == sorted(stage_positions)


def test_knockouts_come_before_profile_fields() -> None:
    last_knockout = max(FIELD_ORDER.index(f) for f in HARD_FIELDS)
    first_soft = min(FIELD_ORDER.index(f) for f in SOFT_FIELDS)
    assert last_knockout < first_soft


def test_every_field_has_a_stage() -> None:
    assert set(FIELD_STAGE) == set(FieldName)


def test_vehicle_and_license_share_the_drop_off_stage() -> None:
    # AC-29 reports drop_off_stage = vehicle_license while vehicle_type is pending.
    assert FIELD_STAGE[FieldName.vehicle_type] == Stage.vehicle_license
    assert FIELD_STAGE[FieldName.has_license] == Stage.vehicle_license


def test_hard_and_soft_fields_are_disjoint() -> None:
    assert HARD_FIELDS.isdisjoint(SOFT_FIELDS)
    assert FieldName.full_name not in HARD_FIELDS | SOFT_FIELDS
    assert FieldName.consent not in HARD_FIELDS | SOFT_FIELDS
