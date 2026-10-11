"""T5: load_config reads both YAML files and reports problems by file and path (AC-35)."""

import shutil
from pathlib import Path

import pytest

from sazon_screening.config import ConfigError, EngineConfig, load_config
from tests.paths import FIXTURE_CONFIG_DIR


@pytest.fixture
def config_copy(tmp_path: Path) -> Path:
    for name in ("service_areas.yaml", "screening.yaml"):
        shutil.copy(FIXTURE_CONFIG_DIR / name, tmp_path / name)
    return tmp_path


def replace_in(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture no longer contains {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_fixture_config_loads() -> None:
    config = load_config(FIXTURE_CONFIG_DIR)
    assert isinstance(config, EngineConfig)
    assert config.version == "fixture.1+fixture.1"


@pytest.mark.ac("AC-35")
def test_error_names_file_and_path(config_copy: Path) -> None:
    replace_in(config_copy / "service_areas.yaml", "Europe/Madrid", "Europe/Madird")
    with pytest.raises(ConfigError) as excinfo:
        load_config(config_copy)
    message = str(excinfo.value)
    assert "service_areas.yaml: countries.0.cities.0.timezone: unknown timezone" in message


@pytest.mark.ac("AC-35")
def test_unknown_vehicle_error_names_screening_file(config_copy: Path) -> None:
    replace_in(config_copy / "screening.yaml", "e_bike: true", "scooter: true")
    with pytest.raises(ConfigError) as excinfo:
        load_config(config_copy)
    message = str(excinfo.value)
    assert "screening.yaml: license_required: unknown vehicle type 'scooter'" in message


def test_cross_file_error_is_reported(config_copy: Path) -> None:
    replace_in(config_copy / "screening.yaml", "MX: 18", "")
    with pytest.raises(ConfigError, match="min_age has no value for country 'MX'"):
        load_config(config_copy)


def test_missing_file_raises_config_error(config_copy: Path) -> None:
    (config_copy / "screening.yaml").unlink()
    with pytest.raises(ConfigError, match=r"screening\.yaml: file not found"):
        load_config(config_copy)


def test_invalid_yaml_raises_config_error(config_copy: Path) -> None:
    (config_copy / "screening.yaml").write_text("version: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"screening\.yaml: invalid YAML"):
        load_config(config_copy)


def test_non_mapping_yaml_raises_config_error(config_copy: Path) -> None:
    (config_copy / "screening.yaml").write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"screening\.yaml: expected a mapping"):
        load_config(config_copy)
