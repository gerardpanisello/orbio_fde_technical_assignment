"""What an opted-out conversation may still hold (FR-11: data minimisation).

Allow-list, not deny-list: any new state or record field is assumed to be candidate
data and must be purged on opt-out unless it is added here on purpose.
"""

from typing import Any

from sazon_screening.config import EngineConfig
from sazon_screening.engine.record import CandidateRecord, build_record
from sazon_screening.engine.state import ConversationState

# Kept: where it ended, how to talk to them, the explicit consent answer (audit of the
# refusal), never-contact-again, and which rules/date applied. No candidate content.
STATE_KEEPS = {
    "state_version",
    "status",
    "stage",
    "drop_off_stage",
    "language",
    "consent",
    "flags",
    "config_version",
    "last_turn_on",
    "last_error",
}
RECORD_KEEPS = {
    "record_version",
    "status",
    "drop_off_stage",
    "language",
    "consent",
    "flags",
    "config_version",
}


def leaked_state(state: ConversationState) -> dict[str, Any]:
    """Every non-allow-listed state key whose value differs from a fresh state."""
    blank = ConversationState().model_dump()
    return {
        key: value
        for key, value in state.model_dump().items()
        if key not in STATE_KEEPS and value != blank[key]
    }


def leaked_record(record: CandidateRecord, config: EngineConfig) -> dict[str, Any]:
    blank = build_record(ConversationState(), config).model_dump()
    return {
        key: value
        for key, value in record.model_dump().items()
        if key not in RECORD_KEEPS and value != blank[key]
    }
