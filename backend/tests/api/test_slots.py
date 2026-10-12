"""T3: the interview slot provider (FR-5)."""

from datetime import date

from sazon_screening.api.slots import SlotConfig, SlotProvider, load_slot_provider
from sazon_screening.vocab import Language
from tests.paths import SHIPPED_CONFIG_DIR


def test_next_working_days_at_each_time_skipping_the_weekend() -> None:
    provider = SlotProvider(SlotConfig(version="t", working_days=3, times=["10:00", "17:00"]))
    slots = provider.slots(date(2026, 10, 16))  # a Friday
    assert [s.id for s in slots] == [
        "2026-10-19T10:00",
        "2026-10-19T17:00",
        "2026-10-20T10:00",
        "2026-10-20T17:00",
        "2026-10-21T10:00",
        "2026-10-21T17:00",
    ]
    assert slots[0].label(Language.es) == "lunes 19/10, 10:00"
    assert slots[0].label(Language.en) == "Mon 19 Oct, 10:00"


def test_shipped_config_loads() -> None:
    assert load_slot_provider(SHIPPED_CONFIG_DIR).slots(date(2026, 10, 12))


def test_max_slots_spreads_the_offer_over_days_and_times() -> None:
    """Spec 001 §6: offer 2-3 slots. One per day first, rotating the times."""
    config = SlotConfig(version="t", working_days=3, times=["10:00", "17:00"], max_slots=3)
    slots = SlotProvider(config).slots(date(2026, 10, 13))  # a Tuesday
    assert [s.id for s in slots] == ["2026-10-14T10:00", "2026-10-15T17:00", "2026-10-16T10:00"]


def test_max_slots_above_one_per_day_fills_in_order() -> None:
    config = SlotConfig(version="t", working_days=2, times=["10:00", "17:00"], max_slots=3)
    slots = SlotProvider(config).slots(date(2026, 10, 13))
    assert [s.id for s in slots] == ["2026-10-14T10:00", "2026-10-14T17:00", "2026-10-15T17:00"]


def test_shipped_config_offers_three_slots() -> None:
    assert len(load_slot_provider(SHIPPED_CONFIG_DIR).slots(date(2026, 10, 13))) == 3
