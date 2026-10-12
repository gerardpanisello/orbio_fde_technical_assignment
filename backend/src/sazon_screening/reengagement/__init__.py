"""Re-engagement (spec 008): follow-ups when a candidate goes silent mid-screening.

`config` and `policy` are pure (no clock, no I/O); the API's scheduler applies them.
"""

from sazon_screening.reengagement.config import (
    FollowUpStep,
    QuietHours,
    ReengagementConfig,
    load_reengagement,
    timezone_for,
)
from sazon_screening.reengagement.policy import (
    Abandon,
    Planned,
    SendFollowUp,
    Silence,
    due,
    next_step,
    postpone,
)

__all__ = [
    "Abandon",
    "FollowUpStep",
    "Planned",
    "QuietHours",
    "ReengagementConfig",
    "SendFollowUp",
    "Silence",
    "due",
    "load_reengagement",
    "next_step",
    "postpone",
    "timezone_for",
]
