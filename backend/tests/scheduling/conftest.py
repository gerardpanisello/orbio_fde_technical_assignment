import pytest

from sazon_screening.config import EngineConfig, load_config
from tests.paths import SHIPPED_CONFIG_DIR


@pytest.fixture(scope="session")
def shipped_config() -> EngineConfig:
    return load_config(SHIPPED_CONFIG_DIR)
