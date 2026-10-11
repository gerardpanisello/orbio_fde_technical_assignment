"""Filesystem locations shared by the test suites."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE_CONFIG_DIR = BACKEND_DIR / "tests" / "fixtures" / "config"
SHIPPED_CONFIG_DIR = BACKEND_DIR.parent / "config"
