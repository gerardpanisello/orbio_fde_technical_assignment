"""The in-process re-engagement loop (spec 008 FR-7), started in the API lifespan.

It also sends the day-before interview reminders (spec 010 FR-6) on the same tick.

Every `tick_seconds` it asks the service which conversations have a due step and runs
each one through `ScreeningService.reengage`, which takes the conversation's lock and
claims the step with a compare-and-set: a candidate's message and a reminder never race,
and a step is never sent twice. One failing conversation is logged and skipped; the loop
itself never dies on an error.

Fine for one instance and the demo. Production: a scheduler service or a delayed queue
with a DB lock (docs/design/deployment.md).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from sazon_screening.api.service import Reengaged, ScreeningService

logger = logging.getLogger("sazon_screening.reengagement")


class ReengagementScheduler:
    def __init__(
        self,
        service: ScreeningService,
        *,
        tick_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._service = service
        self._tick_seconds = tick_seconds
        self._sleep = sleep

    async def tick(self, now: datetime | None = None) -> list[Reengaged]:
        """Run every due step once. Tests call this directly instead of the loop."""
        now = now or self._service.now()
        done: list[Reengaged] = []
        for conversation_id in await self._service.due_for_reengagement(now):
            try:
                outcome = await self._service.reengage(conversation_id, at=now)
                if outcome.summary_due:  # the abandon closed it (or qualified_unscheduled)
                    await self._service.write_summary(conversation_id, at=now)
            except Exception:
                logger.exception("re-engagement failed (conversation %s)", conversation_id)
                continue
            if outcome.action != "none":
                logger.info(
                    "re-engagement %s step=%s (conversation %s)",
                    outcome.action,
                    outcome.step,
                    conversation_id,
                )
            done.append(outcome)
        await self.send_interview_reminders(now)
        return done

    async def send_interview_reminders(self, now: datetime) -> int:
        """Spec 010 FR-6: the day-before reminders, on the same tick. Returns how many went
        out; one failing booking is logged and skipped."""
        sent = 0
        for booking_id in await self._service.due_interview_reminders(now):
            try:
                if await self._service.send_interview_reminder(booking_id, at=now) is not None:
                    sent += 1
            except Exception:
                logger.exception("interview reminder failed (booking %s)", booking_id)
        return sent

    async def run(self) -> None:
        """Tick forever; cancelled at shutdown."""
        while True:
            await self._sleep(self._tick_seconds)
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # e.g. the database is briefly unavailable: try next tick
                logger.exception("re-engagement tick failed")
