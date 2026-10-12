"""The sample-conversations generator runs end to end offline (fake rules mode)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sample_conversations.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sample_conversations", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def test_fake_run_writes_one_file_per_scenario_and_an_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    script = _load()
    assert script.main(["--mode", "fake", "--out", str(tmp_path)]) == 0
    keys = [scenario.key for scenario in script.SCENARIOS]
    assert sorted(p.stem for p in tmp_path.glob("*.md")) == sorted([*keys, "README"])
    index = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert all(f"({key}.md)" in index for key in keys)
    silent = (tmp_path / "k-silent-abandoned.md").read_text(encoding="utf-8")
    assert "`abandoned`" in silent
    assert "silence_expired" in silent
    assert "<details>" in silent
    assert "## Recruiter summary" in silent
    opted_out = (tmp_path / "j-opt-out.md").read_text(encoding="utf-8")
    assert "`opted_out`" in opted_out
