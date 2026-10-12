"""The JSON schema sent to the API must stay inside structured-output limits.

Found in the first live run (T29): the API rejects schemas with > 24 optional or > 16
union-typed parameters. These tests fail before the API would.
"""

from typing import Any

from sazon_screening.llm.extraction.schema import ExtractionOutput


def _wire() -> dict[str, Any]:
    return ExtractionOutput.model_json_schema()


def test_every_field_is_required_on_the_wire() -> None:
    schema = _wire()
    assert set(schema["required"]) == set(schema["properties"])


def test_no_union_or_nullable_types_on_the_wire() -> None:
    for name, prop in _wire()["properties"].items():
        assert "anyOf" not in prop, name
        assert not isinstance(prop.get("type"), list), name


def test_neutral_wire_values_mean_not_stated() -> None:
    out = ExtractionOutput.model_validate(
        {"full_name": "", "age": -1, "has_license": "unknown", "platforms": [], "language": ""}
    )
    assert out.full_name is None
    assert out.age is None
    assert out.has_license is None
    assert out.platforms is None
    assert out.language is None


def test_wire_tristate_maps_to_bool() -> None:
    out = ExtractionOutput.model_validate({"has_license": "yes", "is_adult": "no"})
    assert out.has_license is True
    assert out.is_adult is False


def test_zero_years_of_experience_is_a_real_value() -> None:
    assert ExtractionOutput.model_validate({"experience_years": 0}).experience_years == 0
