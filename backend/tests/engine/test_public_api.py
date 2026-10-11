"""T30: the engine's public API, and the one-way dependency engine -> config -> vocab."""

import ast
import inspect
from pathlib import Path
from types import ModuleType

import sazon_screening.config as config_package
import sazon_screening.engine as engine
from sazon_screening import vocab

CONFIG_DIR = Path(config_package.__file__).parent


def test_every_export_resolves_to_what_it_names() -> None:
    for name in engine.__all__:
        assert not isinstance(getattr(engine, name), ModuleType), name


def test_entry_points_are_functions() -> None:
    for name in ("start", "step", "build_record", "score_candidate"):
        assert inspect.isfunction(getattr(engine, name)), name


def test_core_models_are_exported() -> None:
    assert {"TurnInput", "CandidateTurn", "EngineAction", "ConversationState"} <= set(
        engine.__all__
    )
    assert {"CandidateRecord", "ScoreResult", "UNCLEAR"} <= set(engine.__all__)


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
    return modules


def test_config_and_vocab_never_import_the_engine() -> None:
    # Keeps imports acyclic: engine -> config -> vocab, never back.
    files = [*CONFIG_DIR.glob("*.py"), Path(vocab.__file__)]
    engine_imports = {
        path.name: sorted(m for m in imported_modules(path) if m.startswith(engine.__name__))
        for path in files
    }
    assert {name: mods for name, mods in engine_imports.items() if mods} == {}
