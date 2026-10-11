"""Fixtures for the LLM layer tests."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Async tests run on asyncio only: it is what FastAPI (004) uses in production."""
    return "asyncio"
