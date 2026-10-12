"""Service-area lookup structures, derived from `service_areas.yaml` at load time.

`EngineConfig` builds one `LocationIndex` when it is validated; the engine's location
matching only reads it. Kept in `config` so the config package never imports `engine`.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.vocab import Country


def normalise(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form used to compare place names.

    "COYOACÁN" and "coyoacan" must be the same place; candidates type on phones.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    spaced = re.sub(r"[^\w\s]|_", " ", without_marks.casefold())
    return " ".join(spaced.split())


class AreaRef(BaseModel):
    """A resolved service area: a zone, or a city served as a whole."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str  # zone id, or city id when there is no zone
    country: Country
    city: str
    zone: str | None


@dataclass(frozen=True)
class IndexEntry:
    key: str  # normalised name or alias
    ref: AreaRef
    level: Literal["city", "zone"]


@dataclass(frozen=True)
class LocationIndex:
    """Every name/alias of every city and zone, built once per config."""

    entries: tuple[IndexEntry, ...]
    cities: dict[str, AreaRef]  # city id -> ref, in config order
    zones_by_city: dict[str, tuple[AreaRef, ...]]  # city id -> its zones, in config order

    def served_city_ids(self) -> tuple[str, ...]:
        return tuple(self.cities)

    def served_areas(self) -> tuple[AreaRef, ...]:
        """Every area candidates are placed in: each zone, or a city served as a whole.

        These are the units staffing is tracked for (spec 015), in config order.
        """
        areas: list[AreaRef] = []
        for city_id, city_ref in self.cities.items():
            areas += self.zones_by_city[city_id] or (city_ref,)
        return tuple(areas)

    def zone_entries(self, city_id: str) -> tuple[IndexEntry, ...]:
        return tuple(e for e in self.entries if e.level == "zone" and e.ref.city == city_id)
