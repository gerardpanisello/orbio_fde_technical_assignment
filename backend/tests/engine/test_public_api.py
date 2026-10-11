"""T30: the engine's public API, importable in any order (config <-> engine)."""

import subprocess
import sys
from types import ModuleType

import pytest

import sazon_screening.engine as engine


def test_every_exported_name_resolves_to_what_it_names() -> None:
    import sazon_screening.engine.record
    import sazon_screening.engine.scoring  # noqa: F401

    for name in engine.__all__:
        value = getattr(engine, name)
        assert not isinstance(value, ModuleType), f"{name} resolves to a module"


def test_entry_points_are_functions_even_after_internal_imports() -> None:
    # A submodule named like an export shadows it once imported (engine/step.py did).
    code = "; ".join(
        [
            "import importlib, inspect, pkgutil, sazon_screening.engine as e",
            "[importlib.import_module(e.__name__ + '.' + m.name)"
            " for m in pkgutil.iter_modules(e.__path__)]",
            "from sazon_screening.engine import start, step, build_record, score_candidate",
            "assert all(inspect.isfunction(f)"
            " for f in (start, step, build_record, score_candidate)), step",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_core_entry_points_are_exported() -> None:
    assert {"start", "step", "build_record", "score_candidate"} <= set(engine.__all__)
    assert {"TurnInput", "CandidateTurn", "EngineAction", "ConversationState"} <= set(
        engine.__all__
    )
    assert {"CandidateRecord", "ScoreResult", "UNCLEAR"} <= set(engine.__all__)


def test_unknown_name_raises_attribute_error() -> None:
    with pytest.raises(AttributeError):
        _ = engine.does_not_exist


@pytest.mark.parametrize(
    "code",
    [
        "import sazon_screening.config; from sazon_screening.engine import start, step",
        "from sazon_screening.engine import start, step; import sazon_screening.config",
        "from sazon_screening.config import load_config; import sazon_screening.engine as e;"
        " e.build_record",
        "import sazon_screening.engine.location; from sazon_screening.engine import step",
    ],
)
def test_import_order_does_not_matter(code: str) -> None:
    # A fresh interpreter: the order is only meaningful before anything is cached.
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
