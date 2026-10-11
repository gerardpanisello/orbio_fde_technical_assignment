"""Collecting answers (plan §4.1): apply proposals, classify the attempt, choose the next ask.

`apply_proposals` is the only place that writes screening values. It validates in stage
order (FR-8) and lets the latest value win (FR-9). What to ask next is always
`next_missing_field`, so out-of-order answers need no special case.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import AskField, PrimaryAction, ReaskField
from sazon_screening.engine.enums import (
    Availability,
    FieldName,
    FieldStatus,
    Flag,
    PendingKind,
    ReaskReason,
    ScheduleSlot,
    VehicleType,
)
from sazon_screening.engine.flow import FIELD_ORDER, FIELD_STAGE, next_missing_field
from sazon_screening.engine.inputs import (
    AgeProposal,
    AvailabilityProposal,
    CandidateTurn,
    ConsentProposal,
    ExperienceProposal,
    LicenseProposal,
    LocationProposal,
    NameProposal,
    Proposal,
    ScheduleProposal,
    StartDateProposal,
    Unclear,
    VehicleProposal,
)
from sazon_screening.engine.location import needs_zone, validate_location
from sazon_screening.engine.state import ConversationState, LocationValue, PendingAsk, add_flag
from sazon_screening.engine.validators import (
    Accepted,
    NeedsConfirmation,
    Rejected,
    validate_age,
    validate_availability,
    validate_consent,
    validate_experience,
    validate_license,
    validate_name,
    validate_schedule,
    validate_start_date,
    validate_vehicle,
)

Outcome = Accepted[object] | Rejected | NeedsConfirmation


@dataclass
class Applied:
    """What `apply_proposals` did with one turn's proposals."""

    accepted: set[FieldName] = field(default_factory=set)
    changed: list[FieldName] = field(default_factory=list)  # overwrote a different value
    pending_outcome: Rejected | None = None  # the field we asked about was not usable
    confirmation: bool | Unclear | None = None  # yes/no, read by recap/confirm handlers
    raised_confirmation: bool = False  # a value now needs confirming: that is the next ask
    declined_consent: bool = False


@dataclass(frozen=True)
class Attempt:
    """How this turn counts for the field we asked about (FR-23)."""

    kind: Literal["answered", "failed", "neutral"]
    reason: ReaskReason = ReaskReason.unclear
    options: tuple[str, ...] = ()


# --- applying proposals ------------------------------------------------------------------


def apply_proposals(
    s: ConversationState, turn: CandidateTurn, cfg: EngineConfig, today: date
) -> Applied:
    applied = Applied()
    latest: dict[str, Proposal] = {p.field: p for p in turn.proposals}  # latest wins
    consent = latest.pop("consent", None)
    if not _passes_consent_gate(s, consent, bool(latest), applied):
        return applied  # FR-7: data sent before consent is discarded
    for name in FIELD_ORDER:  # stage order, whatever order the candidate used
        if (proposal := latest.get(name.value)) is not None:
            _apply_one(s, name, proposal, cfg, today, applied)
    return applied


def _passes_consent_gate(
    s: ConversationState,
    proposal: Proposal | None,
    has_other_proposals: bool,
    applied: Applied,
) -> bool:
    if s.consent is True:
        return True
    if not isinstance(proposal, ConsentProposal):
        if has_other_proposals:  # data without consent: ask for consent explicitly
            applied.pending_outcome = Rejected(ReaskReason.consent_required)
        return False
    outcome = validate_consent(proposal.value)
    if isinstance(outcome, Rejected):
        applied.pending_outcome = outcome
        return False
    if outcome.value is False:
        applied.declined_consent = True
        return False
    s.consent = True
    applied.accepted.add(FieldName.consent)
    return True


def _apply_one(
    s: ConversationState,
    name: FieldName,
    proposal: Proposal,
    cfg: EngineConfig,
    today: date,
    applied: Applied,
) -> None:
    outcome = _validate(s, proposal, cfg, today)
    if isinstance(outcome, Accepted):
        _store(s, name, outcome.value, cfg, applied)
        for flag in outcome.flags:
            add_flag(s, flag)
    elif isinstance(outcome, Rejected) and _is_pending(s, name):
        applied.pending_outcome = outcome
    # A rejected value for a field we did not ask about is ignored: nothing stored or counted.


def _validate(s: ConversationState, proposal: Proposal, cfg: EngineConfig, today: date) -> Outcome:
    limits = cfg.thresholds
    match proposal:
        case NameProposal(value=value):
            return validate_name(value, reasks_used=s.reasks.get(FieldName.full_name, 0))
        case AgeProposal(value=value):
            return validate_age(
                value,
                min_plausible=limits.min_plausible_age,
                max_plausible=limits.max_plausible_age,
            )
        case VehicleProposal(value=value):
            return validate_vehicle(value)
        case LicenseProposal(value=value):
            return validate_license(value)
        case LocationProposal(value=value):
            return validate_location(
                value,
                cfg,
                country_hint=s.country_hint,
                current=s.profile.location.value,
                pending_zone=s.pending.field is FieldName.zone,
            )
        case AvailabilityProposal(value=value):
            return validate_availability(value)
        case ScheduleProposal(value=value):
            return validate_schedule(value)
        case ExperienceProposal(value=value):
            return validate_experience(
                value,
                platforms=cfg.screening.platforms,
                confirm_above=limits.experience_confirm_above_years,
            )
        case StartDateProposal(value=value):
            return validate_start_date(value, today)
    return Rejected(ReaskReason.unclear)  # consent/confirmation/choice never get here


def _store(
    s: ConversationState, name: FieldName, value: object, cfg: EngineConfig, applied: Applied
) -> None:
    slot = getattr(s.profile, name.value)
    if slot.value is not None and slot.value != value:
        applied.changed.append(name)
    slot.value = value
    slot.status = FieldStatus.valid
    if isinstance(value, LocationValue) and needs_zone(value, cfg):
        slot.status = FieldStatus.not_asked  # city known, zone still to ask (AC-14)
    applied.accepted.add(name)


def _is_pending(s: ConversationState, name: FieldName) -> bool:
    """Is this the field we asked about? A zone is answered with a location proposal."""
    return _answers(name, s.pending.field)


def _answers(name: FieldName, pending: FieldName | None) -> bool:
    return name is pending or (name is FieldName.location and pending is FieldName.zone)


# --- what to ask next ----------------------------------------------------------------------


def classify_attempt(
    s: ConversationState, turn: CandidateTurn, applied: Applied, *, neutral: bool
) -> Attempt:
    """answered / failed / neutral for the pending field (FR-23, AC-20).

    Only a rejected answer for the asked field, or an empty turn, consumes a re-ask.
    FAQ, off-topic, a language switch or other fields filled are neutral.
    """
    if applied.pending_outcome is not None:
        outcome = applied.pending_outcome
        return Attempt("failed", outcome.reason, outcome.options)
    if any(_answers(name, s.pending.field) for name in applied.accepted):
        return Attempt("answered")
    if not turn.proposals and not neutral:
        return Attempt("failed", _empty_turn_reason(s))
    return Attempt("neutral")


def _empty_turn_reason(s: ConversationState) -> ReaskReason:
    if s.pending.field is FieldName.consent:
        return ReaskReason.consent_required
    return ReaskReason.unclear


def on_ask(s: ConversationState, attempt: Attempt, cfg: EngineConfig) -> PrimaryAction:
    """Handler for `pending.kind == ask`."""
    if attempt.kind == "failed" and s.pending.field is not None:
        options = attempt.options or default_options(s.pending.field, s, cfg)
        reask = reask_or_exhaust(s, s.pending.field, attempt.reason, options, cfg)
        if reask is not None:
            return reask
    return next_action(s, cfg)


def next_action(s: ConversationState, cfg: EngineConfig) -> PrimaryAction:
    field_name = next_missing_field(s, cfg)
    if field_name is None:  # pragma: no cover - recap arrives in T21
        raise NotImplementedError("recap")
    set_pending(s, PendingKind.ask, field_name)
    return AskField(field=field_name)


def reask_or_exhaust(
    s: ConversationState,
    name: FieldName,
    reason: ReaskReason,
    options: tuple[str, ...],
    cfg: EngineConfig,
) -> PrimaryAction | None:
    """Re-ask up to `max_reasks` times (FR-23); after that give up on the field (FR-24).

    Returns None when the field is exhausted: the caller moves on with `next_action`.
    """
    limit = cfg.thresholds.max_reasks
    used = s.reasks.get(name, 0) + 1
    if name is FieldName.consent:
        # Plan OQ-1: never assume consent and never close; silence (008) ends it.
        s.reasks[name] = min(used, limit + 1)
        return ReaskField(field=name, reason=ReaskReason.consent_required)
    s.reasks[name] = used
    if used > limit:
        exhaust(s, name)
        return None
    return ReaskField(field=name, reason=reason, options=list(options))


def exhaust(s: ConversationState, name: FieldName) -> None:
    """Out of re-asks: store `unclear` and move on (never disqualify on ambiguity)."""
    if name is FieldName.full_name:
        add_flag(s, Flag.name_unclear)  # required but not qualifying (FR-16)
    getattr(s.profile, name.value).status = FieldStatus.unclear


def repeat_pending(s: ConversationState, reason: ReaskReason, cfg: EngineConfig) -> PrimaryAction:
    """Ask the pending question again without using a re-ask (e.g. extraction failed)."""
    name = s.pending.field
    if s.pending.kind is PendingKind.ask and name is not None:
        return ReaskField(field=name, reason=reason, options=list(default_options(name, s, cfg)))
    return pending_action(s)


def pending_action(s: ConversationState) -> PrimaryAction:
    """The action that asks what `s.pending` waits for."""
    return AskField(field=s.pending.field or FieldName.consent)


def default_options(name: FieldName, s: ConversationState, cfg: EngineConfig) -> tuple[str, ...]:
    """Choices to offer when re-asking a closed question (IDs; 003 phrases them)."""
    index = cfg.location_index
    location = s.profile.location.value
    match name:
        case FieldName.vehicle_type:
            return tuple(option.value for option in VehicleType)
        case FieldName.availability:
            return tuple(option.value for option in Availability)
        case FieldName.schedule:
            return tuple(option.value for option in ScheduleSlot)
        case FieldName.location:
            return index.served_city_ids()
        case FieldName.zone if location is not None and location.city is not None:
            return tuple(ref.id for ref in index.zones_by_city.get(location.city, ()))
        case FieldName.slot:
            return tuple(s.offered_slot_ids)
    return ()


def set_pending(s: ConversationState, kind: PendingKind, name: FieldName | None = None) -> None:
    """Record what we wait for next and keep `stage` in sync with it (FR-6)."""
    s.pending = PendingAsk(kind=kind, field=name)
    if name is not None:
        s.stage = FIELD_STAGE[name]
