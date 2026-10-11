"""Applying one turn's proposals to the state (plan §4.1 `apply_proposals`).

This is the only place that writes screening values. Proposals are validated in stage
order (FR-8) and the latest value wins (FR-9). Answers to a pending confirmation
(yes/no, an option id) are resolved here too, so the hard rules that run right after
always see the final values of the turn.
"""

from dataclasses import dataclass, field
from datetime import date

from sazon_screening.config import EngineConfig
from sazon_screening.engine.enums import FieldName, FieldStatus, PendingKind, ReaskReason, Stage
from sazon_screening.engine.flow import FIELD_ORDER, FIELD_STAGE
from sazon_screening.engine.inputs import (
    AgeProposal,
    AvailabilityProposal,
    CandidateTurn,
    ChoiceProposal,
    ConfirmationProposal,
    ConsentProposal,
    ExperienceProposal,
    LicenseProposal,
    LocationAnswer,
    LocationProposal,
    NameProposal,
    Proposal,
    ScheduleProposal,
    StartDateProposal,
    Unclear,
    VehicleProposal,
)
from sazon_screening.engine.location import (
    Matched,
    match_location,
    needs_zone,
    served_value,
    validate_location,
)
from sazon_screening.engine.state import (
    AreaRef,
    ConversationState,
    Experience,
    LocationValue,
    PendingAsk,
    add_flag,
)
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
    confirmation: bool | Unclear | None = None  # yes/no, read by the recap handlers
    raised_confirmation: bool = False  # a value now needs confirming: that is the next ask
    declined_consent: bool = False


def apply_proposals(
    s: ConversationState, turn: CandidateTurn, cfg: EngineConfig, today: date
) -> Applied:
    applied = Applied()
    latest: dict[str, Proposal] = {p.field: p for p in turn.proposals}  # latest wins
    consent = latest.pop("consent", None)
    if not _passes_consent_gate(s, consent, bool(latest), applied):
        return applied  # FR-7: data sent before consent is discarded
    confirmation = latest.pop("confirmation", None)
    if isinstance(confirmation, ConfirmationProposal):
        applied.confirmation = confirmation.value
    choice = latest.pop("choice", None)
    if s.pending.kind is PendingKind.confirm_value and "experience" not in latest:
        _answer_value_confirmation(s, applied, cfg)
    if s.pending.kind is PendingKind.confirm_ambiguous:
        _answer_ambiguity(s, choice, latest, cfg, applied)
    for name in FIELD_ORDER:  # stage order, whatever order the candidate used
        if (proposal := latest.get(name.value)) is not None:
            _apply_one(s, name, proposal, cfg, today, applied)
    return applied


def answers_pending(name: FieldName, pending: FieldName | None) -> bool:
    """Does a value for `name` answer the pending question? A zone is a location answer."""
    return name is pending or (name is FieldName.location and pending is FieldName.zone)


def set_pending(
    s: ConversationState,
    kind: PendingKind,
    name: FieldName | None = None,
    *,
    candidate_value: Experience | None = None,
    options: tuple[AreaRef, ...] = (),
    raw_text: str | None = None,
) -> None:
    """Record what we wait for next and keep `stage` in sync with it (FR-6)."""
    s.pending = PendingAsk(
        kind=kind,
        field=name,
        candidate_value=candidate_value,
        options=list(options),
        raw_text=raw_text,
    )
    if kind in (PendingKind.recap, PendingKind.correction_field):
        s.stage = Stage.recap
    elif name is not None:
        s.stage = FIELD_STAGE[name]


# --- consent ---------------------------------------------------------------------------


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


# --- answers to a pending confirmation ----------------------------------------------------


def _answer_value_confirmation(s: ConversationState, applied: Applied, cfg: EngineConfig) -> None:
    """Yes stores the value we asked about; no asks for the field again (value_rejected)."""
    answer = applied.confirmation
    if answer is True and s.pending.candidate_value is not None:
        _store(s, FieldName.experience, s.pending.candidate_value, cfg, applied)
    elif answer is False:
        applied.pending_outcome = Rejected(ReaskReason.value_rejected)
    elif isinstance(answer, Unclear):
        applied.pending_outcome = Rejected(ReaskReason.unclear)


def _answer_ambiguity(
    s: ConversationState,
    choice: Proposal | None,
    latest: dict[str, Proposal],
    cfg: EngineConfig,
    applied: Applied,
) -> None:
    """Pick one of the offered places, by option id or by naming its city ("Monterrey")."""
    options = s.pending.options
    picked: AreaRef | None = None
    if isinstance(choice, ChoiceProposal):
        picked = next((o for o in options if o.id == choice.value), None)
    location = latest.get("location")
    if picked is None and isinstance(location, LocationProposal):
        if isinstance(location.value, LocationAnswer):
            picked = _option_named(location.value.text, options, cfg)
        if picked is not None:
            del latest["location"]  # used to choose; not a new location
    if picked is not None:
        value = served_value(picked, s.pending.raw_text or picked.id)
        _store(s, FieldName.location, value, cfg, applied)
    elif choice is not None:
        applied.pending_outcome = Rejected(ReaskReason.unclear, tuple(o.id for o in options))


def _option_named(text: str, options: list[AreaRef], cfg: EngineConfig) -> AreaRef | None:
    result = match_location(
        text,
        cfg.location_index,
        threshold=cfg.thresholds.fuzzy_match_min_score,
        country_hint=None,
        within_city=None,
    )
    if not isinstance(result, Matched):
        return None
    ids = {ref.id for ref in result.refs}
    cities = {ref.city for ref in result.refs}
    fits = [o for o in options if o.id in ids or o.city in cities]
    return fits[0] if len(fits) == 1 else None


# --- field proposals ----------------------------------------------------------------------


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
    elif isinstance(outcome, NeedsConfirmation):
        _raise_confirmation(s, name, outcome, proposal, applied)
    elif answers_pending(name, s.pending.field):
        applied.pending_outcome = outcome
    # A rejected value for a field we did not ask about is ignored: nothing stored or counted.


def _raise_confirmation(
    s: ConversationState,
    name: FieldName,
    outcome: NeedsConfirmation,
    proposal: Proposal,
    applied: Applied,
) -> None:
    """The first confirmation of the turn becomes the next question; later ones are
    dropped and simply asked again in stage order (plan §5)."""
    if applied.raised_confirmation:
        return
    applied.raised_confirmation = True
    if outcome.kind == "value":
        set_pending(s, PendingKind.confirm_value, name, candidate_value=outcome.value)
        return
    text = proposal.value.text if isinstance(proposal.value, LocationAnswer) else None
    set_pending(
        s, PendingKind.confirm_ambiguous, FieldName.location, options=outcome.options, raw_text=text
    )


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
