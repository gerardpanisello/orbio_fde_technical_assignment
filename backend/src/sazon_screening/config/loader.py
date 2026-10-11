"""Load and validate the YAML config. The only I/O around the engine (plan §3.10).

Errors are collected and re-worded as `<file>: <dotted.path>: <problem>` so whoever
edits the YAML can find the line without reading a Pydantic traceback (AC-35).
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from sazon_screening.config.models import EngineConfig, ScreeningConfig, ServiceAreasConfig

SERVICE_AREAS_FILE = "service_areas.yaml"
SCREENING_FILE = "screening.yaml"


class ConfigError(Exception):
    """The config directory cannot be turned into a valid `EngineConfig`."""


def load_config(config_dir: Path) -> EngineConfig:
    """Read both config files from `config_dir` and validate them, failing fast."""
    service_areas = load_yaml_model(config_dir / SERVICE_AREAS_FILE, ServiceAreasConfig)
    screening = load_yaml_model(config_dir / SCREENING_FILE, ScreeningConfig)
    try:
        return EngineConfig(service_areas=service_areas, screening=screening)
    except ValidationError as error:
        # Cross-file checks (min_age, default_country) are about screening.yaml values.
        raise ConfigError(_format(SCREENING_FILE, error)) from None


def load_yaml_model[M: BaseModel](path: Path, model: type[M]) -> M:
    """Read one YAML file into `model`; errors read `<file>: <dotted.path>: <problem>`.

    Public so other config files (e.g. the LLM layer's `llm.yaml`) fail the same way.
    """
    data = _read_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise ConfigError(_format(path.name, error)) from None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path.name}: file not found in {path.parent}") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{path.name}: invalid YAML: {error}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


def _format(file_name: str, error: ValidationError) -> str:
    lines = []
    for detail in error.errors():
        path = ".".join(str(part) for part in detail["loc"]) or "(root)"
        message = detail["msg"].removeprefix("Value error, ")
        lines.append(f"{file_name}: {path}: {message}")
    return "\n".join(lines)
