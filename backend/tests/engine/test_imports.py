"""T1: the engine and config packages exist and import cleanly."""

import importlib

import pytest


@pytest.mark.parametrize("module", ["sazon_screening.config", "sazon_screening.engine"])
def test_package_imports(module: str) -> None:
    assert importlib.import_module(module) is not None
