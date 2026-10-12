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
