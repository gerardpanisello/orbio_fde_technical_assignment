"""T11-T13: matching free-text locations against configured service areas (FR-19)."""

import pytest

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.engine.inputs import UNCLEAR, LocationAnswer
from sazon_screening.engine.location import (
    CityWithUnknownZone,
    LocationMatch,
    Matched,
    NoMatch,
    match_location,
    needs_zone,
    normalise,
    similarity,
    validate_location,
)
from sazon_screening.engine.rules import hard_rule_failure
from sazon_screening.engine.state import ConversationState, LocationValue, Slot
from sazon_screening.engine.validators import Accepted, NeedsConfirmation, Rejected
from sazon_screening.vocab import Country, FieldStatus, ReaskReason
from tests.engine.conftest import MakeConfig
from tests.paths import SHIPPED_CONFIG_DIR


def match(
    text: str,
    config: EngineConfig,
    *,
    country_hint: Country | None = None,
    within_city: str | None = None,
) -> LocationMatch:
    return match_location(
        text,
        config.location_index,
        threshold=config.thresholds.fuzzy_match_min_score,
        country_hint=country_hint,
        within_city=within_city,
    )


def ref_ids(result: LocationMatch) -> list[str]:
    assert isinstance(result, Matched), result
    return [ref.id for ref in result.refs]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Coyoacán", "coyoacan"),
        ("COYOACÁN", "coyoacan"),
        ("  Ciudad   de México ", "ciudad de mexico"),
        ("D.F.", "d f"),
        ("Chamberí!", "chamberi"),
        ("Sants-Montjuïc", "sants montjuic"),
        ("O'Donnell", "o donnell"),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


class TestIndex:
    def test_index_is_built_with_the_config(self, config: EngineConfig) -> None:
        index = config.location_index
        assert index.cities["cdmx"].country == Country.MX
        assert [z.id for z in index.zones_by_city["madrid"]] == [
            "mad-centro",
            "mad-chamberi",
            "mad-salamanca",
        ]
        assert index.zones_by_city["barcelona"] == ()

    def test_served_city_ids_keep_config_order(self, config: EngineConfig) -> None:
        assert config.location_index.served_city_ids() == (
            "madrid",
            "barcelona",
            "valencia",
            "cdmx",
            "monterrey",
        )


class TestExactMatch:
    @pytest.mark.ac("AC-12")
    @pytest.mark.parametrize("text", ["CDMX", "DF", "D.F.", "Ciudad de México", "ciudad de mexico"])
    def test_city_aliases_resolve_to_cdmx(self, config: EngineConfig, text: str) -> None:
        assert ref_ids(match(text, config)) == ["cdmx"]

    @pytest.mark.ac("AC-12")
    @pytest.mark.parametrize("text", ["coyoacan", "COYOACÁN", "Coyoacán"])
    def test_zone_names_resolve_accent_and_case_insensitive(
        self, config: EngineConfig, text: str
    ) -> None:
        result = match(text, config)
        assert isinstance(result, Matched)
        (ref,) = result.refs
        assert (ref.id, ref.city, ref.zone, ref.country) == (
            "cdmx-coyoacan",
            "cdmx",
            "cdmx-coyoacan",
            Country.MX,
        )

    def test_zone_alias(self, config: EngineConfig) -> None:
        assert ref_ids(match("Roma", config)) == ["cdmx-cuauhtemoc"]

    @pytest.mark.parametrize("text", ["Coyoacán, CDMX", "CDMX / Coyoacán", "Coyoacán (DF)"])
    def test_zone_with_its_city_resolves_to_the_zone(self, config: EngineConfig, text: str) -> None:
        assert ref_ids(match(text, config)) == ["cdmx-coyoacan"]

    @pytest.mark.parametrize(
        "text",
        ["colonia Roma, CDMX", "Col. Roma", "en la colonia Roma", "barrio de Roma", "zona Roma"],
    )
    def test_place_type_words_around_a_zone_are_ignored(
        self, config: EngineConfig, text: str
    ) -> None:
        """Found by the sample conversations: "colonia Roma, CDMX" was out of area."""
        assert ref_ids(match(text, config)) == ["cdmx-cuauhtemoc"]

    @pytest.mark.parametrize("text", ["barrio de Chamberí, Madrid", "el barrio Chamberí"])
    def test_place_type_words_in_spain(self, config: EngineConfig, text: str) -> None:
        assert ref_ids(match(text, config)) == ["mad-chamberi"]

    def test_a_name_that_starts_with_an_article_still_matches_whole(
        self, config: EngineConfig
    ) -> None:
        assert ref_ids(match("El Carme", config)) == ["val-el-carmen"]

    def test_place_words_alone_are_no_match(self, config: EngineConfig) -> None:
        assert match("colonia", config) == NoMatch()

    def test_city_alone_is_city_only(self, config: EngineConfig) -> None:
        result = match("Madrid", config)
        assert isinstance(result, Matched)
        (ref,) = result.refs
        assert (ref.id, ref.city, ref.zone) == ("madrid", "madrid", None)

    def test_city_narrows_a_shared_zone_name(self, config: EngineConfig) -> None:
        assert ref_ids(match("Centro, Madrid", config)) == ["mad-centro"]

    def test_shared_zone_name_alone_matches_every_city(self, config: EngineConfig) -> None:
        assert ref_ids(match("Centro", config)) == ["cdmx-centro", "mad-centro"]

    def test_unknown_text_is_no_match(self, config: EngineConfig) -> None:
        assert match("xjkq", config) == NoMatch()

    def test_empty_text_is_no_match(self, config: EngineConfig) -> None:
        assert match(" , ", config) == NoMatch()

    def test_city_with_unknown_part_is_flagged(self, config: EngineConfig) -> None:
        result = match("Vallecas, Madrid", config)
        assert isinstance(result, CityWithUnknownZone)
        assert result.city.id == "madrid"
        assert result.residual == "vallecas"

    def test_extra_part_after_a_city_without_zones_is_still_that_city(
        self, config: EngineConfig
    ) -> None:
        # Barcelona has no zones in the fixture: the whole city is served.
        assert ref_ids(match("Gràcia, Barcelona", config)) == ["barcelona"]


class TestFuzzyAndContext:
    @pytest.mark.ac("AC-12")
    def test_typo_resolves_by_fuzzy_match(self, config: EngineConfig) -> None:
        assert ref_ids(match("Cuyoacán", config)) == ["cdmx-coyoacan"]

    def test_similarity_of_the_documented_example(self) -> None:
        assert similarity("cuyoacan", "coyoacan") == pytest.approx(87.5)

    def test_threshold_comes_from_config(self, make_config: MakeConfig) -> None:
        strict = make_config(screening={"thresholds": {"fuzzy_match_min_score": 95}})
        assert match("Cuyoacán", strict) == NoMatch()

    def test_short_text_is_never_fuzzy_matched(self, config: EngineConfig) -> None:
        # "Sal" is 1 edit from "Sol" (a Madrid alias): too short to guess safely.
        assert match("Sal", config) == NoMatch()

    @pytest.mark.ac("AC-13")
    def test_name_in_two_countries_is_ambiguous_without_hint(self, config: EngineConfig) -> None:
        assert ref_ids(match("El Carmen", config)) == ["mty-el-carmen", "val-el-carmen"]

    @pytest.mark.ac("AC-13")
    def test_country_hint_resolves_the_ambiguity(self, config: EngineConfig) -> None:
        assert ref_ids(match("El Carmen", config, country_hint=Country.MX)) == ["mty-el-carmen"]

    def test_country_hint_never_removes_every_match(self, config: EngineConfig) -> None:
        # A Spanish phone saying "Coyoacán" still gets Coyoacán (plan OQ-3).
        assert ref_ids(match("Coyoacán", config, country_hint=Country.ES)) == ["cdmx-coyoacan"]

    def test_centro_with_spanish_hint_in_fixture_is_madrid(self, config: EngineConfig) -> None:
        assert ref_ids(match("Centro", config, country_hint=Country.ES)) == ["mad-centro"]

    def test_centro_with_spanish_hint_in_shipped_config_is_still_ambiguous(self) -> None:
        shipped = load_config(SHIPPED_CONFIG_DIR)
        ids = ref_ids(match("Centro", shipped, country_hint=Country.ES))
        assert len(ids) >= 2
        assert "mad-centro" in ids

    def test_pending_zone_prefers_the_known_city(self, config: EngineConfig) -> None:
        assert ref_ids(match("Centro", config, within_city="madrid")) == ["mad-centro"]

    def test_pending_zone_falls_back_to_a_global_match(self, config: EngineConfig) -> None:
        # The candidate may be moving: "Coyoacán" while we asked for a Madrid zone.
        assert ref_ids(match("Coyoacán", config, within_city="madrid")) == ["cdmx-coyoacan"]

    def test_unknown_zone_of_a_named_city(self, config: EngineConfig) -> None:
        result = match("Vallecas, Madrid", config, country_hint=Country.ES)
        assert result == CityWithUnknownZone(
            city=config.location_index.cities["madrid"], residual="vallecas"
        )

    @pytest.mark.parametrize("text", ["xjkq", "Zaragoza"])
    def test_unserved_or_unknown_text_is_no_match(self, config: EngineConfig, text: str) -> None:
        assert match(text, config) == NoMatch()


def validate(
    text: str | None,
    config: EngineConfig,
    *,
    known: bool = True,
    country_hint: Country | None = None,
    current: LocationValue | None = None,
) -> Accepted[LocationValue] | Rejected | NeedsConfirmation:
    answer = UNCLEAR if text is None else LocationAnswer(text=text, is_known_place=known)
    return validate_location(
        answer,
        config,
        country_hint=country_hint,
        current=current,
        pending_zone=current is not None,
    )


def accepted_value(outcome: object) -> LocationValue:
    assert isinstance(outcome, Accepted), outcome
    assert isinstance(outcome.value, LocationValue)
    return outcome.value


def state_at(value: LocationValue) -> ConversationState:
    state = ConversationState()
    state.profile.location = Slot(status=FieldStatus.valid, value=value)
    return state


MADRID_ZONES = ("mad-centro", "mad-chamberi", "mad-salamanca")
SERVED_CITIES = ("madrid", "barcelona", "valencia", "cdmx", "monterrey")


class TestValidateLocation:
    def test_zone_is_accepted_complete(self, config: EngineConfig) -> None:
        value = accepted_value(validate("Coyoacán", config))
        assert (value.country, value.city, value.zone) == (Country.MX, "cdmx", "cdmx-coyoacan")
        assert value.in_service_area
        assert value.raw_text == "Coyoacán"
        assert not needs_zone(value, config)

    def test_city_without_zones_is_complete(self, config: EngineConfig) -> None:
        value = accepted_value(validate("BCN", config))
        assert (value.city, value.zone, value.in_service_area) == ("barcelona", None, True)
        assert not needs_zone(value, config)

    @pytest.mark.ac("AC-14")
    def test_city_with_zones_is_partial(self, config: EngineConfig) -> None:
        value = accepted_value(validate("Madrid", config))
        assert (value.city, value.zone, value.in_service_area) == ("madrid", None, True)
        assert needs_zone(value, config)

    @pytest.mark.ac("AC-10")
    def test_known_unserved_zone_of_a_served_city_is_out_of_area(
        self, config: EngineConfig
    ) -> None:
        value = accepted_value(validate("Vallecas, Madrid", config, known=True))
        assert (value.country, value.city, value.zone) == (Country.ES, "madrid", None)
        assert not value.in_service_area
        assert hard_rule_failure(state_at(value), config) == "out_of_area"

    def test_colonia_of_a_served_zone_is_in_area(self, config: EngineConfig) -> None:
        value = accepted_value(validate("colonia Roma, CDMX", config, known=True))
        assert (value.city, value.zone, value.in_service_area) == ("cdmx", "cdmx-cuauhtemoc", True)

    @pytest.mark.ac("AC-11")
    def test_known_unserved_place_is_out_of_area(self, config: EngineConfig) -> None:
        value = accepted_value(validate("Zaragoza", config, known=True))
        assert (value.country, value.city, value.in_service_area) == (None, None, False)
        assert hard_rule_failure(state_at(value), config) == "out_of_area"

    @pytest.mark.ac("AC-11")
    def test_unrecognisable_text_is_reasked_with_served_cities(self, config: EngineConfig) -> None:
        outcome = validate("xjkq", config, known=False)
        assert outcome == Rejected(ReaskReason.not_recognised, options=SERVED_CITIES)

    def test_unclear_is_reasked_with_served_cities(self, config: EngineConfig) -> None:
        outcome = validate(None, config)
        assert outcome == Rejected(ReaskReason.not_recognised, options=SERVED_CITIES)

    def test_unknown_part_of_a_city_not_known_as_a_place_lists_its_zones(
        self, config: EngineConfig
    ) -> None:
        outcome = validate("Vallecsa, Madrid", config, known=False)
        assert outcome == Rejected(ReaskReason.not_recognised, options=MADRID_ZONES)

    @pytest.mark.ac("AC-13")
    def test_ambiguous_place_needs_confirmation(self, config: EngineConfig) -> None:
        outcome = validate("El Carmen", config)
        assert isinstance(outcome, NeedsConfirmation)
        assert outcome.kind == "ambiguous"
        assert [ref.id for ref in outcome.options] == ["mty-el-carmen", "val-el-carmen"]

    @pytest.mark.ac("AC-13")
    def test_country_hint_avoids_the_confirmation(self, config: EngineConfig) -> None:
        value = accepted_value(validate("El Carmen", config, country_hint=Country.MX))
        assert value.zone == "mty-el-carmen"

    def test_served_place_is_accepted_even_if_extractor_says_unknown(
        self, config: EngineConfig
    ) -> None:
        # The config is the source of truth for served places, not the LLM's flag.
        value = accepted_value(validate("Coyoacán", config, known=False))
        assert value.in_service_area


class TestValidateZoneAnswer:
    @pytest.fixture
    def madrid(self, config: EngineConfig) -> LocationValue:
        return accepted_value(validate("Madrid", config))

    @pytest.mark.ac("AC-14")
    def test_zone_answer_completes_the_city(
        self, config: EngineConfig, madrid: LocationValue
    ) -> None:
        value = accepted_value(validate("Centro", config, current=madrid))
        assert (value.city, value.zone) == ("madrid", "mad-centro")
        assert value.raw_text == "Madrid, Centro"

    def test_repeating_the_city_does_not_answer_the_zone(
        self, config: EngineConfig, madrid: LocationValue
    ) -> None:
        outcome = validate("Madrid", config, current=madrid)
        assert outcome == Rejected(ReaskReason.unclear, options=MADRID_ZONES)

    def test_unrecognisable_zone_lists_the_city_zones(
        self, config: EngineConfig, madrid: LocationValue
    ) -> None:
        outcome = validate("xjkq", config, known=False, current=madrid)
        assert outcome == Rejected(ReaskReason.not_recognised, options=MADRID_ZONES)

    def test_known_unserved_zone_is_out_of_area(
        self, config: EngineConfig, madrid: LocationValue
    ) -> None:
        value = accepted_value(validate("Vallecas", config, known=True, current=madrid))
        assert not value.in_service_area
        assert hard_rule_failure(state_at(value), config) == "out_of_area"

    def test_moving_to_another_served_city_is_accepted(
        self, config: EngineConfig, madrid: LocationValue
    ) -> None:
        value = accepted_value(validate("Coyoacán", config, current=madrid))
        assert value.zone == "cdmx-coyoacan"
