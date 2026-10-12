"""Location matching (FR-19, plan §3.6): free text -> configured service-area IDs.

The extractor (003) passes the candidate's words plus `is_known_place`; this module does
the deterministic part: normalise, look up names and aliases, and combine the pieces of
"Coyoacán, CDMX". It never decides qualification (rules.py does).
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sazon_screening.config import EngineConfig
from sazon_screening.config.areas import AreaRef, IndexEntry, LocationIndex, normalise
from sazon_screening.engine.inputs import LocationAnswer, Unclear
from sazon_screening.engine.state import LocationValue
from sazon_screening.engine.validators import Accepted, NeedsConfirmation, Rejected
from sazon_screening.vocab import Country, ReaskReason

# --- match results -------------------------------------------------------------------------


@dataclass(frozen=True)
class Matched:
    """One or more served areas (more than one = ambiguous, the engine will ask)."""

    refs: tuple[AreaRef, ...]


@dataclass(frozen=True)
class CityWithUnknownZone:
    """A served city plus a part we could not match, e.g. "Vallecas, Madrid"."""

    city: AreaRef
    residual: str


@dataclass(frozen=True)
class NoMatch:
    pass


LocationMatch = Matched | CityWithUnknownZone | NoMatch


# --- matching ------------------------------------------------------------------------------


def similarity(a: str, b: str) -> float:
    """0-100 similarity of two normalised strings.

    stdlib difflib is enough for ~150 index keys (< 1 ms); swapping in rapidfuzz would
    be a change to this one function.
    """
    return SequenceMatcher(None, a, b).ratio() * 100


def match_location(
    text: str,
    index: LocationIndex,
    *,
    threshold: int,
    country_hint: Country | None,
    within_city: str | None,
) -> LocationMatch:
    """Match free text against the service areas (plan §3.6).

    `within_city` is set when we asked for a zone: that city's zones are tried first,
    then everything (the candidate may be moving). `country_hint` (phone prefix) only
    narrows an ambiguous result, and never down to nothing.
    """
    if within_city is not None:
        local = _match(text, index.zone_entries(within_city), index, threshold)
        if isinstance(local, Matched):
            return local
    result = _match(text, index.entries, index, threshold)
    if isinstance(result, Matched) and country_hint is not None:
        in_country = tuple(ref for ref in result.refs if ref.country is country_hint)
        if in_country:
            return Matched(in_country)
    return result


# Generic words candidates put around a place name: "colonia Roma", "barrio de Chamberí",
# "Col. Roma". Language vocabulary, not a business rule (which places we serve stays in
# config). Matched on normalised text, and only tried when the segment as written misses,
# so a configured name that starts with one of these words still matches whole.
_PLACE_WORDS = re.compile(
    r"^(?:(?:en|la|el|los|las|mi|in|the|my)\s+)*"
    r"(?:colonia|col|barrio|bo|zona|distrito|alcaldia|delegacion|municipio|fraccionamiento"
    r"|fracc|neighbou?rhood|district|area)"
    r"(?:\s+(?:de|del|la|el|of|the))*\s+"
)
_MIN_FUZZY_LENGTH = 4  # shorter words are one typo away from too many places
_FUZZY_TIE_MARGIN = 2.0  # keep every candidate this close to the best score


def _match(
    text: str, entries: tuple[IndexEntry, ...], index: LocationIndex, threshold: int
) -> LocationMatch:
    whole, *parts = _segments(text)
    if not whole:
        return NoMatch()
    if hits := _hits_bare(whole, entries, threshold):
        return _combine(hits, [], index)
    part_hits = [(part, _hits_bare(part, entries, threshold)) for part in parts]
    return _combine(
        [hit for _, hits in part_hits for hit in hits],
        [part for part, hits in part_hits if not hits],
        index,
    )


def _segments(text: str) -> list[str]:
    """The whole text first, then its pieces split on , / ( ) (normalised, de-duplicated)."""
    whole = normalise(text)
    pieces = [normalise(piece) for piece in re.split(r"[,/()]", text)]
    parts = [p for p in dict.fromkeys(pieces) if p and p != whole]
    return [whole, *parts]


def _hits_bare(segment: str, entries: tuple[IndexEntry, ...], threshold: int) -> list[IndexEntry]:
    """Hits for the segment as written; failing that, without generic place words."""
    if hits := _hits(segment, entries, threshold):
        return hits
    bare = _PLACE_WORDS.sub("", segment, count=1)
    return _hits(bare, entries, threshold) if bare and bare != segment else []


def _hits(segment: str, entries: tuple[IndexEntry, ...], threshold: int) -> list[IndexEntry]:
    """Exact name/alias hits; failing that, the best fuzzy hits above the threshold."""
    exact = [entry for entry in entries if entry.key == segment]
    if exact or len(segment) < _MIN_FUZZY_LENGTH:
        return exact
    scored = [(similarity(segment, entry.key), entry) for entry in entries]
    good = [(score, entry) for score, entry in scored if score >= threshold]
    if not good:
        return []
    best = max(score for score, _ in good)
    return [entry for score, entry in good if score >= best - _FUZZY_TIE_MARGIN]


def _combine(
    entries: list[IndexEntry], unmatched: list[str], index: LocationIndex
) -> LocationMatch:
    city_ids = {entry.ref.city for entry in entries if entry.level == "city"}
    zones = [entry.ref for entry in entries if entry.level == "zone"]
    if zones:
        # "Centro, Madrid": the city picks which "Centro" is meant.
        in_named_city = [ref for ref in zones if ref.city in city_ids]
        return Matched(_unique(in_named_city or zones))
    cities = [entry.ref for entry in entries if entry.level == "city"]
    # "Vallecas, Madrid": a served city plus a zone we do not know. Only meaningful when
    # the city is split into zones; a city without zones is served as a whole.
    if len(set(cities)) == 1 and unmatched and index.zones_by_city[cities[0].city]:
        return CityWithUnknownZone(city=cities[0], residual=unmatched[0])
    return Matched(_unique(cities)) if cities else NoMatch()


def _unique(refs: list[AreaRef]) -> tuple[AreaRef, ...]:
    """De-duplicate and sort by id so results never depend on config or input order."""
    return tuple(sorted(set(refs), key=lambda ref: ref.id))


# --- validation (FR-19 outcomes) ------------------------------------------------------------


def needs_zone(value: LocationValue, config: EngineConfig) -> bool:
    """A served city that is split into zones, but we do not know which zone yet (AC-14)."""
    if not value.in_service_area or value.city is None or value.zone is not None:
        return False
    return bool(config.location_index.zones_by_city.get(value.city))


def validate_location(
    answer: LocationAnswer | Unclear,
    config: EngineConfig,
    *,
    country_hint: Country | None,
    current: LocationValue | None,
    pending_zone: bool,
) -> Accepted[LocationValue] | Rejected | NeedsConfirmation:
    """Turn a location answer into a stored value, a re-ask or an ambiguity question.

    Ambiguity never disqualifies. Only a place the extractor knows is real, and that we
    do not serve, is stored as out of area (`in_service_area=False`); rules.py rejects it.
    """
    index = config.location_index
    within_city = current.city if pending_zone and current is not None else None
    if isinstance(answer, Unclear):
        return _not_recognised(index, within_city)
    raw_text = f"{current.raw_text}, {answer.text}" if within_city and current else answer.text
    result = match_location(
        answer.text,
        index,
        threshold=config.thresholds.fuzzy_match_min_score,
        country_hint=country_hint,
        within_city=within_city,
    )
    match result:
        case Matched(refs=(ref,)):
            if within_city == ref.city and ref.zone is None:  # "Madrid" again: no zone given
                return Rejected(ReaskReason.unclear, options=_zone_ids(index, ref.city))
            return Accepted(served_value(ref, raw_text))
        case Matched(refs=refs):
            return NeedsConfirmation("ambiguous", options=refs)
        case CityWithUnknownZone(city=city) if answer.is_known_place:
            return Accepted(_unserved(raw_text, city))
        case CityWithUnknownZone(city=city):
            return Rejected(ReaskReason.not_recognised, options=_zone_ids(index, city.city))
        case NoMatch() if answer.is_known_place:
            return Accepted(_unserved(raw_text, None))
        case _:
            return _not_recognised(index, within_city)


def served_value(ref: AreaRef, raw_text: str) -> LocationValue:
    """The stored value for a served area (zone, or a city with or without zones)."""
    return LocationValue(
        raw_text=raw_text, country=ref.country, city=ref.city, zone=ref.zone, in_service_area=True
    )


def _unserved(raw_text: str, city: AreaRef | None) -> LocationValue:
    return LocationValue(
        raw_text=raw_text,
        country=city.country if city else None,
        city=city.city if city else None,
        zone=None,
        in_service_area=False,
    )


def _not_recognised(index: LocationIndex, within_city: str | None) -> Rejected:
    """Re-ask listing what we serve: the city's zones if we asked for one, else the cities."""
    options = _zone_ids(index, within_city) if within_city else index.served_city_ids()
    return Rejected(ReaskReason.not_recognised, options=options)


def _zone_ids(index: LocationIndex, city_id: str) -> tuple[str, ...]:
    return tuple(ref.id for ref in index.zones_by_city.get(city_id, ()))
