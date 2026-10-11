"""T15/T16: the message catalog loads, and fails loudly when incomplete (FR-16)."""

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from sazon_screening.config import ConfigError
from sazon_screening.llm.phrasing.catalog import MessageCatalog, load_catalog
from sazon_screening.vocab import Language, Register, VehicleType
from tests.paths import BACKEND_DIR

FIXTURE_MESSAGES = BACKEND_DIR / "tests" / "fixtures" / "messages"


def copy_fixture(tmp_path: Path) -> Path:
    for path in FIXTURE_MESSAGES.glob("*.yaml"):
        shutil.copy(path, tmp_path / path.name)
    return tmp_path


def edit(directory: Path, file_name: str, change: Any) -> None:
    path = directory / file_name
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_fixture_catalog_loads() -> None:
    catalog = load_catalog(FIXTURE_MESSAGES)
    assert isinstance(catalog, MessageCatalog)
    assert set(catalog.registers) == set(Register)
    assert catalog.for_register(Register.es_MX).labels.vehicle_type[VehicleType.car] == "es-MX car"


def test_label_lookup_by_language() -> None:
    catalog = load_catalog(FIXTURE_MESSAGES)
    assert catalog.label("vehicle_type", "car", Language.es) == "es-ES car"
    assert catalog.label("vehicle_type", "car", Language.en) == "en car"
    assert catalog.label("yes_no", "yes", Language.en) == "Yes"


def test_missing_disqualification_template_names_file_and_key(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    edit(directory, "es-MX.yaml", lambda d: d["templates"]["close_disqualified"].pop("no_license"))
    with pytest.raises(ConfigError, match=r"es-MX\.yaml: templates\.close_disqualified: .*no_lic"):
        load_catalog(directory)


def test_unknown_placeholder_is_rejected(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    edit(directory, "en.yaml", lambda d: d["templates"].update(closed_ack="You earn {salary}."))
    with pytest.raises(ConfigError, match=r"en\.yaml: .*closed_ack: unknown placeholder"):
        load_catalog(directory)


def test_missing_register_is_rejected(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    (directory / "es-MX.yaml").unlink()
    with pytest.raises(ConfigError, match=r"es-MX\.yaml: file not found"):
        load_catalog(directory)


def test_missing_label_is_rejected(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    edit(directory, "es-ES.yaml", lambda d: d["labels"]["vehicle_type"].pop("e_bike"))
    with pytest.raises(ConfigError, match=r"labels\.vehicle_type: missing e_bike"):
        load_catalog(directory)


def test_summary_labels_are_required_for_es_and_en(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    edit(directory, "en.yaml", lambda d: d.pop("summary"))
    with pytest.raises(ConfigError, match=r"en\.yaml: summary: missing"):
        load_catalog(directory)


def test_file_must_declare_its_register(tmp_path: Path) -> None:
    directory = copy_fixture(tmp_path)
    edit(directory, "es-MX.yaml", lambda d: d.update(register="es-ES"))
    with pytest.raises(ConfigError, match=r"es-MX\.yaml: register"):
        load_catalog(directory)


def test_shipped_catalog_loads(catalog: MessageCatalog) -> None:
    assert set(catalog.registers) == set(Register)
    assert catalog.label("vehicle_type", "car", Language.es) == "Coche"
