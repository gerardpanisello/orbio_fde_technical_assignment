"""T10: the flat, described schema the extraction model fills (FR-6, plan §3.6)."""

from typing import Any

from sazon_screening.llm.extraction.schema import ExtractionOutput


def properties() -> dict[str, dict[str, Any]]:
    schema = ExtractionOutput.model_json_schema()
    props: dict[str, dict[str, Any]] = schema["properties"]
    return props


def test_every_property_has_a_description() -> None:
    undocumented = [name for name, prop in properties().items() if not prop.get("description")]
    assert undocumented == []


def test_unions_are_at_most_value_or_null() -> None:
    """Small models fill flat fields reliably; nested unions are where they go wrong."""
    for name, prop in properties().items():
        assert "oneOf" not in prop, name
        branches = prop.get("anyOf")
        if branches is None:
            continue
        assert len(branches) == 2, name
        assert {"type": "null"} in branches, name
        other = next(branch for branch in branches if branch != {"type": "null"})
        assert "anyOf" not in other, name
        assert "oneOf" not in other, name


def test_all_defaults_is_valid_and_means_nothing_understood() -> None:
    empty = ExtractionOutput()
    assert empty.unclear_fields == []
    assert not empty.opt_out
    assert not empty.off_topic
    assert not empty.no_option_fits
    assert empty.sentiment == "neutral"


def test_empty_json_object_parses_to_the_all_defaults_output() -> None:
    # Carry-over 3: `{}` from the model is "nothing understood", never UNCLEAR.
    assert ExtractionOutput.model_validate_json("{}") == ExtractionOutput()
