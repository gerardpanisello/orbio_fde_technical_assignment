"""T3/T4: config models validate client-editable YAML content (FR-29, AC-35)."""

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from sazon_screening.config.models import (
    AvailabilityScoring,
    EngineConfig,
    ScreeningConfig,
    ServiceAreasConfig,
)
from sazon_screening.engine.enums import Availability, VehicleType


def minimal_areas() -> dict[str, Any]:
    return {
        "version": "test.1",
        "countries": [
            {
                "id": "ES",
                "names": {"es": "España", "en": "Spain"},
                "cities": [
                    {
                        "id": "madrid",
                        "names": {"es": "Madrid", "en": "Madrid"},
                        "aliases": ["MAD"],
                        "timezone": "Europe/Madrid",
                        "zones": [
                            {"id": "mad-centro", "names": {"es": "Centro", "en": "Centre"}},
                            {"id": "mad-chamberi", "names": {"es": "Chamberí", "en": "Chamberí"}},
                        ],
                    }
                ],
            },
            {
                "id": "MX",
                "names": {"es": "México", "en": "Mexico"},
                "cities": [
                    {
                        "id": "cdmx",
                        "names": {"es": "Ciudad de México", "en": "Mexico City"},
                        "aliases": ["CDMX"],
                        "timezone": "America/Mexico_City",
                        "zones": [
                            {"id": "cdmx-centro", "names": {"es": "Centro", "en": "Centro"}},
                        ],
                    }
                ],
            },
        ],
    }


def madrid(data: dict[str, Any]) -> dict[str, Any]:
    city: dict[str, Any] = data["countries"][0]["cities"][0]
    return city


class TestServiceAreas:
    def test_valid_minimal_config_passes(self) -> None:
        areas = ServiceAreasConfig.model_validate(minimal_areas())
        assert [c.id for c in areas.countries] == ["ES", "MX"]

    def test_same_zone_name_in_two_cities_is_allowed(self) -> None:
        # "Centro" exists in Madrid and CDMX on purpose: country_hint disambiguates it.
        ServiceAreasConfig.model_validate(minimal_areas())

    @pytest.mark.ac("AC-35")
    def test_duplicate_zone_id_is_rejected_naming_the_id(self) -> None:
        data = minimal_areas()
        madrid(data)["zones"][1]["id"] = "mad-centro"
        with pytest.raises(ValidationError, match="duplicate id 'mad-centro'"):
            ServiceAreasConfig.model_validate(data)

    def test_id_shared_between_city_and_zone_is_rejected(self) -> None:
        data = minimal_areas()
        madrid(data)["zones"][0]["id"] = "cdmx"
        with pytest.raises(ValidationError, match="duplicate id 'cdmx'"):
            ServiceAreasConfig.model_validate(data)

    def test_bad_timezone_is_rejected(self) -> None:
        data = minimal_areas()
        madrid(data)["timezone"] = "Europe/Madird"
        with pytest.raises(ValidationError, match="unknown timezone 'Europe/Madird'"):
            ServiceAreasConfig.model_validate(data)

    @pytest.mark.parametrize("bad_id", ["Madrid", "mad centro", "mad_centro", ""])
    def test_ids_must_be_slugs(self, bad_id: str) -> None:
        data = minimal_areas()
        madrid(data)["id"] = bad_id
        with pytest.raises(ValidationError):
            ServiceAreasConfig.model_validate(data)

    def test_duplicate_normalised_name_inside_one_city_is_rejected(self) -> None:
        data = minimal_areas()
        madrid(data)["zones"][1]["aliases"] = ["CENTRO"]
        with pytest.raises(ValidationError, match="'centro' is used by more than one zone"):
            ServiceAreasConfig.model_validate(data)

    def test_unknown_keys_are_rejected(self) -> None:
        data = copy.deepcopy(minimal_areas())
        madrid(data)["zonse"] = []
        with pytest.raises(ValidationError, match="zonse"):
            ServiceAreasConfig.model_validate(data)


def minimal_screening() -> dict[str, Any]:
    return {
        "version": "test.1",
        "default_country": "ES",
        "min_age": {"ES": 18, "MX": 18},
        "license_required": {
            "motorbike": True,
            "car": True,
            "bicycle": True,
            "e_bike": True,
            "none": True,
        },
        "platforms": [{"id": "glovo", "aliases": ["glovo"]}],
        "scoring": {
            "experience_years": {"points_per_year": 5, "max_points": 20},
            "platforms": {"points_per_known_platform": 10, "max_points": 20},
            "availability": {"full_time": 15, "part_time": 8, "weekends": 7, "max_points": 25},
            "schedule": {"flexible": 15, "per_slot": 5, "max_points": 15},
            "start_date": [
                {"within_days": 3, "points": 20},
                {"within_days": 14, "points": 10},
                {"within_days": 30, "points": 5},
            ],
            "buckets": {"high": 60, "medium": 35},
        },
    }


class TestScreening:
    def test_valid_minimal_config_passes(self) -> None:
        screening = ScreeningConfig.model_validate(minimal_screening())
        assert screening.requires_license(VehicleType.bicycle)
        assert screening.scoring.max_score == 100

    @pytest.mark.ac("AC-35")
    def test_unknown_vehicle_type_is_rejected_naming_it(self) -> None:
        data = minimal_screening()
        data["license_required"]["scooter"] = True
        with pytest.raises(ValidationError, match="unknown vehicle type 'scooter'"):
            ScreeningConfig.model_validate(data)

    def test_missing_vehicle_type_is_rejected(self) -> None:
        data = minimal_screening()
        del data["license_required"]["e_bike"]
        with pytest.raises(ValidationError, match=r"missing vehicle type.*e_bike"):
            ScreeningConfig.model_validate(data)

    @pytest.mark.ac("AC-35")
    @pytest.mark.parametrize(("high", "medium"), [(35, 35), (30, 35), (101, 35), (60, 0)])
    def test_bucket_thresholds_out_of_order_are_rejected(self, high: int, medium: int) -> None:
        data = minimal_screening()
        data["scoring"]["buckets"] = {"high": high, "medium": medium}
        with pytest.raises(ValidationError, match="bucket thresholds"):
            ScreeningConfig.model_validate(data)

    def test_start_date_bands_must_increase(self) -> None:
        data = minimal_screening()
        data["scoring"]["start_date"][1]["within_days"] = 3
        with pytest.raises(ValidationError, match="strictly increasing"):
            ScreeningConfig.model_validate(data)

    def test_missing_availability_weight_is_rejected(self) -> None:
        data = minimal_screening()
        del data["scoring"]["availability"]["weekends"]
        with pytest.raises(ValidationError, match="weekends"):
            ScreeningConfig.model_validate(data)

    def test_availability_weights_cover_the_enum(self) -> None:
        # Guards against adding an Availability value without a scoring weight.
        assert set(Availability) <= set(AvailabilityScoring.model_fields)

    def test_duplicate_platform_id_is_rejected(self) -> None:
        data = minimal_screening()
        data["platforms"].append({"id": "glovo"})
        with pytest.raises(ValidationError, match="duplicate platform id 'glovo'"):
            ScreeningConfig.model_validate(data)

    def test_threshold_defaults_match_spec(self) -> None:
        # Spec §7 #11: max re-asks 2, recap rounds 3, extraction failures 3, abuse 2, fuzzy 85.
        thresholds = ScreeningConfig.model_validate(minimal_screening()).thresholds
        assert thresholds.max_reasks == 2
        assert thresholds.max_recap_rounds == 3
        assert thresholds.max_consecutive_extraction_failures == 3
        assert thresholds.abuse_close_count == 2
        assert thresholds.fuzzy_match_min_score == 85

    def test_plausible_age_bounds_must_be_ordered(self) -> None:
        data = minimal_screening()
        data["thresholds"] = {"min_plausible_age": 99, "max_plausible_age": 14}
        with pytest.raises(ValidationError, match="min_plausible_age"):
            ScreeningConfig.model_validate(data)


class TestEngineConfig:
    def test_combines_both_files_and_versions(self) -> None:
        config = EngineConfig.model_validate(
            {"service_areas": minimal_areas(), "screening": minimal_screening()}
        )
        assert config.version == "test.1+test.1"

    def test_min_age_must_cover_every_configured_country(self) -> None:
        screening = minimal_screening()
        del screening["min_age"]["MX"]
        with pytest.raises(ValidationError, match="min_age has no value for country 'MX'"):
            EngineConfig.model_validate({"service_areas": minimal_areas(), "screening": screening})

    def test_default_country_must_be_configured(self) -> None:
        areas = minimal_areas()
        del areas["countries"][0]
        with pytest.raises(ValidationError, match="default_country 'ES'"):
            EngineConfig.model_validate({"service_areas": areas, "screening": minimal_screening()})

    def test_is_frozen(self) -> None:
        config = EngineConfig.model_validate(
            {"service_areas": minimal_areas(), "screening": minimal_screening()}
        )
        with pytest.raises(ValidationError):
            config.screening = config.screening  # type: ignore[misc]
