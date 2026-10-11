"""Versioned system prompts, one file per role (FR-26, plan §3.5).

The version is in the file name (`extraction.v1.md`) and `llm.yaml` picks which one a
role uses, so a prompt change is a reviewed config change, and rolling back is a
one-line edit. The trace also records a short sha256 of the text, so an edit made
without bumping the version is still visible in the data.
"""

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

from sazon_screening.config import ConfigError

_PROMPT_ID = re.compile(r"[a-z_]+\.v\d+")  # also rules out paths like "../x.v1"


@dataclass(frozen=True)
class Prompt:
    id: str  # e.g. "extraction.v1"
    sha: str  # first 12 hex chars of sha256(text)
    text: str


class PromptRegistry:
    """Loads prompts from this package (or another directory, in tests) and caches them."""

    def __init__(self, directory: Traversable | None = None) -> None:
        self._directory = directory if directory is not None else files(__name__)
        self._cache: dict[str, Prompt] = {}

    def load(self, prompt_id: str) -> Prompt:
        if prompt_id not in self._cache:
            self._cache[prompt_id] = self._read(prompt_id)
        return self._cache[prompt_id]

    def _read(self, prompt_id: str) -> Prompt:
        if not _PROMPT_ID.fullmatch(prompt_id):
            raise ConfigError(f"llm.yaml: prompt id {prompt_id!r} is not like 'extraction.v1'")
        entry = self._directory.joinpath(f"{prompt_id}.md")
        if not entry.is_file():
            raise ConfigError(f"llm.yaml: prompt {prompt_id!r} not found ({prompt_id}.md)")
        text = entry.read_text(encoding="utf-8")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        return Prompt(id=prompt_id, sha=sha, text=text)
