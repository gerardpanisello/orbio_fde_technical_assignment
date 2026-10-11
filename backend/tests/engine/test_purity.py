"""T29: the engine has no clock, randomness, environment, network or file access (NFR-2).

A static scan, so a forbidden call fails CI even on a path no test executes.
"""

import ast
from pathlib import Path

import pytest

import sazon_screening.engine as engine_package

ENGINE_DIR = Path(engine_package.__file__).parent
ENGINE_FILES = sorted(ENGINE_DIR.glob("*.py"))

FORBIDDEN_MODULES = {
    "os",
    "sys",
    "time",
    "random",
    "secrets",
    "uuid",
    "socket",
    "subprocess",
    "yaml",
    "httpx",
    "requests",
    "anthropic",
    "sqlalchemy",
    "sazon_screening.config.loader",
}
FORBIDDEN_CALLS = {
    "open",
    "print",
    "input",
    "date.today",
    "datetime.now",
    "datetime.today",
    "datetime.utcnow",
    "os.environ",
    "os.getenv",
}


def dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{dotted(node.value)}.{node.attr}"
    return ""


def violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in FORBIDDEN_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in FORBIDDEN_MODULES or node.module.split(".")[0] in FORBIDDEN_MODULES:
                found.append(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:  # open(), print(), input()
                found.append(node.func.id)
        elif isinstance(node, ast.Attribute) and dotted(node) in FORBIDDEN_CALLS:
            found.append(dotted(node))
    return found


def test_engine_files_are_found() -> None:
    assert {"step.py", "apply.py", "collect.py", "closing.py"} <= {p.name for p in ENGINE_FILES}


@pytest.mark.parametrize("path", ENGINE_FILES, ids=lambda p: p.name)
def test_engine_module_is_pure(path: Path) -> None:
    assert violations(path) == []


def test_scanner_catches_a_clock_read(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import os\nfrom datetime import date\nx = date.today()\n", encoding="utf-8")
    assert violations(bad) == ["os", "date.today"]
