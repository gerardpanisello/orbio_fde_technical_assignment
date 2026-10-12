"""T27: architectural boundaries of the LLM layer, checked on the source (NFR-7, plan §7.3)."""

import ast
from pathlib import Path

import sazon_screening.llm as llm_package

LLM_DIR = Path(llm_package.__file__).parent
SOURCES = sorted(LLM_DIR.rglob("*.py"))
# The engine is used only through its public API (ADR 0005), never its submodules.
# The FAQ knowledge base (009) likewise, through `sazon_screening.faq`.
ALLOWED_PROJECT_IMPORTS = (
    "sazon_screening.engine",
    "sazon_screening.faq",
    "sazon_screening.config",
    "sazon_screening.vocab",
)


def imports(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
    return modules


def relative(path: Path) -> str:
    return path.relative_to(LLM_DIR).as_posix()


def test_only_the_anthropic_client_imports_the_sdk() -> None:
    importers = {
        relative(path)
        for path in SOURCES
        if any(m == "anthropic" or m.startswith("anthropic.") for m in imports(path))
    }
    assert importers == {"client/anthropic_client.py"}


def test_the_engine_is_used_only_through_its_public_api() -> None:
    offenders = {
        relative(path): sorted(bad)
        for path in SOURCES
        if (
            bad := {
                m
                for m in imports(path)
                if m.startswith("sazon_screening.")
                and not m.startswith("sazon_screening.llm")
                and m not in ALLOWED_PROJECT_IMPORTS
            }
        )
    }
    assert offenders == {}


def test_nothing_reads_the_calendar_except_the_demo() -> None:
    """`today` always comes from the caller (004 or the demo), like in the engine."""
    readers = set()
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if is_calendar_read(node):
                readers.add(relative(path))
    assert readers <= {"demo.py"}


def is_calendar_read(node: ast.AST) -> bool:
    """`date.today`, `datetime.now`, `datetime.utcnow`."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr in {"today", "now", "utcnow"}
        and isinstance(node.value, ast.Name)
        and node.value.id in {"date", "datetime"}
    )
