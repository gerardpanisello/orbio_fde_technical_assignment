"""Small helpers shared by the simulator and the judge (the eval's own API calls).

The eval talks to the Anthropic SDK directly: it is a dev tool, not part of the product,
so it does not go through the product's LLMClient (whose roles are the agent's jobs).
"""

from typing import Any

from sazon_screening.llm.settings import ModelPrice

END_TOKEN = "<END>"


def cost_of(usage: Any, price: ModelPrice | None) -> float:
    """USD for one response's `usage`, priced like the product's telemetry."""
    if usage is None or price is None:
        return 0.0
    total = (
        (usage.input_tokens or 0) * price.input
        + (usage.output_tokens or 0) * price.output
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * price.cache_read
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * price.cache_write
    )
    return total / 1_000_000


def text_of(response: Any) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()
