"""Phone numbers (spec 016 FR-3): kept out of logs, transcripts and records.

The WhatsApp id (`wa_id`: international number, digits only) is stored in one column
of the conversation, to reply and to find the conversation again. Everywhere else
(logs, the do-not-contact set) only its hash appears.

A SHA-256 of a phone number is pseudonymisation, not anonymisation: the number space is
small enough to brute-force. Encryption at rest is out of scope (spec 016 FR-3).
"""

import hashlib

REF_LENGTH = 10  # hex chars of the hash shown in logs: enough to correlate lines


def phone_hash(wa_id: str) -> str:
    return hashlib.sha256(normalise(wa_id).encode()).hexdigest()


def phone_ref(wa_id: str | None) -> str:
    """What a log line shows instead of the number."""
    return f"wa:{phone_hash(wa_id)[:REF_LENGTH]}" if wa_id else "wa:-"


def normalise(wa_id: str) -> str:
    """Digits only: '+34 600 000 000' and '34600000000' are the same person."""
    return "".join(ch for ch in wa_id if ch.isdigit())
