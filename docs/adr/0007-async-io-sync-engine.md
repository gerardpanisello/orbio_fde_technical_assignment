# ADR 0007 — Async I/O layers around a sync, pure engine

**Status:** Accepted (2026-10-11, spec 003 plan OQ-6)

## Context
Spec 003 adds the first network I/O: up to two LLM calls per candidate turn (extraction, phrasing), each taking ~1–3 s. Spec 004 serves the agent through FastAPI, which runs on an event loop. At ~1000 applications/week (≈ 10 000 screenings and many concurrent turns at peak), most of a turn's time is spent waiting on the API. Spec 001/003 also set a hard ceiling of 15 s per turn (NFR-1), so every call needs a timeout that respects the time left in the turn.

The engine (spec 002) is a pure function that runs in well under 1 ms and does no I/O.

## Decision
- **Everything that does I/O is async**: the LLM client (`AsyncAnthropic`), the extraction / phrasing / summary services, the turn pipeline, and the layers that will call them (004 persistence and API, 008 timers, 010 calendars, 013 voice).
- **The engine stays sync and pure.** The pipeline calls `step()` inline; it needs no thread pool.
- **SDK retries are off** (`max_retries=0`). Our own retry loop (`call_with_retry`) runs under a per-turn `Deadline`, so each attempt's timeout is `min(role timeout, time left)` and the retry count is visible in telemetry.
- **Time is injected.** The deadline reads an injectable clock, and tests advance a fake clock instead of sleeping.
- **Async tests use the anyio pytest plugin** (it ships with `anyio`, an SDK dependency), pinned to the asyncio backend.

## Alternatives considered
- **Sync client everywhere:** simpler tests and no event loop. But in FastAPI each blocked turn would hold a worker thread for seconds, and cancelling at a deadline is awkward.
- **Async engine too:** one colour everywhere. But the engine does no I/O, so `async` would add noise to 500+ tests and suggest I/O that is not there.
- **`asyncio.timeout` around the whole turn:** a hard guarantee, but it cancels mid-call with no clean fallback accounting, and it needs real time in tests.
- **SDK built-in retries:** free backoff, but invisible to telemetry and able to exceed the 15 s ceiling.

## Consequences
- Callers of the LLM layer (004, 008, 010, 013) must be async, or run it with `anyio.run`.
- Unit tests stay fast and deterministic: a fake clock, a fake client, no sleeping, no network.
- The engine remains reusable from any context (sync scripts, voice adapters, property tests).
- Retry and timeout behaviour is ours to maintain; revisit if live runs show retry storms or 429 handling issues (plan OQ-4).
