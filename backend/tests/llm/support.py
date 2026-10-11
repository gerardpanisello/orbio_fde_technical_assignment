"""Test doubles shared by the LLM layer tests."""


class FakeClock:
    """A monotonic clock that only moves when told to, so nothing in a test really sleeps.

    `sleep` is async and advances the clock: pass it wherever production code would
    use `anyio.sleep`, and backoff and deadlines become plain arithmetic.
    """

    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)
