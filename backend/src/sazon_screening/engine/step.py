"""The engine entry points: `start()` and `step()` (ADR 0005, plan §4.1).

`step` is a pure function of (state, input, config, today). It deep-copies the state on
entry, mutates only that copy, and returns it with exactly one primary action. Read
`on_candidate_turn` top to bottom: it is the FR-10 precedence, one rule per block.
"""

from datetime import date

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AckCorrection,
    AnswerFaq,
    AskField,
    ClosedAck,
    ConfirmInterview,
    EngineAction,
    NoMessage,
    Preface,
    PrimaryAction,
    Redirect,
    register_for,
)
from sazon_screening.engine.apply import apply_proposals
from sazon_screening.engine.closing import (
    close_disqualified,
    close_needs_review,
    close_qualified_unscheduled,
    handoff,
    on_closed,
    opt_out,
)
from sazon_screening.engine.collect import (
    classify_attempt,
    on_field_answer,
    on_recap,
    on_slot_answer,
    pending_action,
    reask_or_exhaust,
    repeat_pending,
)
from sazon_screening.engine.enums import (
    Country,
    FieldName,
    Flag,
    Language,
    PendingKind,
    ReaskReason,
    ReviewReason,
    Stage,
    Status,
)
from sazon_screening.engine.inputs import (
    CandidateTurn,
    NoSlotFits,
    SilenceExpired,
    SlotSelected,
    TurnInput,
)
from sazon_screening.engine.rules import hard_rule_failure, sync_license_requirement
from sazon_screening.engine.state import ConversationState


def start(
    config: EngineConfig, *, language: Language = Language.es, country_hint: Country | None = None
) -> tuple[ConversationState, EngineAction]:
    """A fresh conversation: we always start by asking for consent (FR-7)."""
    state = ConversationState(
        language=language, country_hint=country_hint, config_version=config.version
    )
    return state, finish(state, AskField(field=FieldName.consent), [], config)


def step(
    state: ConversationState, turn: TurnInput, config: EngineConfig, today: date
) -> tuple[ConversationState, EngineAction]:
    """Evaluate one turn. Never raises (NFR-5): a bug sends the candidate to a recruiter."""
    try:
        return step_unchecked(state, turn, config, today)
    except Exception:
        if state.status is Status.opted_out:  # never re-open an opted-out conversation
            return state, finish(state, ClosedAck(), [], config)
        s = state.model_copy(deep=True)
        primary = close_needs_review(s, ReviewReason.engine_error, flag=Flag.engine_error)
        return s, finish(s, primary, [], config)


def step_unchecked(
    state: ConversationState, turn: TurnInput, config: EngineConfig, today: date
) -> tuple[ConversationState, EngineAction]:
    """`step` without the safety net; tests call this so bugs are not hidden."""
    s = state.model_copy(deep=True)  # the caller's state is never mutated
    s.config_version = config.version
    s.last_turn_on = today
    prefaces: list[Preface] = []
    match turn:
        case CandidateTurn():
            primary = on_candidate_turn(s, turn, config, today, prefaces)
        case SilenceExpired():
            primary = on_silence(s)
        case SlotSelected() | NoSlotFits():
            primary = on_slot_event(s, turn, config)
    return s, finish(s, primary, prefaces, config)


def on_candidate_turn(
    s: ConversationState,
    t: CandidateTurn,
    cfg: EngineConfig,
    today: date,
    prefaces: list[Preface],
) -> PrimaryAction:
    signals = t.signals
    language_changed = signals.language is not None and signals.language is not s.language
    if signals.language is not None:
        s.language = signals.language
    if t.context.country_hint is not None:
        s.country_hint = t.context.country_hint

    # (1) opt-out wins over everything, in every stage and status (FR-11).
    if s.status is Status.opted_out:
        return ClosedAck()  # terminal (plan OQ-4)
    if signals.opt_out:
        return opt_out(s)

    # Closed conversations: answer FAQs, keep the data as it is (FR-15).
    if s.status in _CLOSED:
        return on_closed(s, t, cfg, today, prefaces)

    # Any message after a silence resumes the conversation where it stopped (FR-14).
    resumed = s.status is Status.abandoned
    if resumed:
        s.status = Status.in_progress

    # (2) abuse: first time a redirect, repeated -> a recruiter reviews (FR-28).
    if signals.abuse:
        s.abuse_count += 1
        if s.abuse_count >= cfg.thresholds.abuse_close_count:
            return close_needs_review(s, ReviewReason.abuse, flag=Flag.abuse)
        prefaces.append(Redirect(reason="abuse"))

    # The extractor could not read the message: ask again, without using a re-ask (FR-27).
    if signals.extraction_failed and not t.proposals:
        s.consecutive_extraction_failures += 1
        if s.consecutive_extraction_failures >= cfg.thresholds.max_consecutive_extraction_failures:
            return close_needs_review(s, ReviewReason.system_failure, flag=Flag.system_failure)
        return repeat_pending(s, ReaskReason.extraction_failed, cfg)
    s.consecutive_extraction_failures = 0

    # (3) apply proposals (stage order, latest wins), with the consent gate (FR-7).
    applied = apply_proposals(s, t, cfg, today)
    if applied.declined_consent:
        return opt_out(s)
    sync_license_requirement(s, cfg)
    if signals.correction and applied.changed:
        prefaces.append(AckCorrection(fields=applied.changed))
    if (reason := hard_rule_failure(s, cfg)) is not None:
        return close_disqualified(s, reason)

    # (4) the candidate asked for a person: pause screening (FR-12).
    if signals.wants_human:
        return handoff(s)
    # (5) FAQ / off-topic: say something first, then resume (FR-13, FR-28).
    if signals.faq_question:
        prefaces.append(AnswerFaq())
    if signals.off_topic:
        prefaces.append(Redirect(reason="off_topic"))

    # A value that needs confirming (45 years, "El Carmen") is the next question.
    if applied.raised_confirmation:
        return pending_action(s)

    # (6) the next ask, depending on how this turn answered the pending one.
    neutral = (
        resumed  # "hola, sigo aquí" after a silence: ask again, it is not a failed answer
        or language_changed
        or signals.faq_question
        or signals.off_topic
        or signals.abuse
    )
    attempt = classify_attempt(s, t, applied, neutral=neutral)
    if s.pending.kind in (PendingKind.recap, PendingKind.correction_field):
        return on_recap(s, t, applied, attempt, cfg)
    if s.pending.kind is PendingKind.slot:
        return on_slot_answer(s, t, applied, attempt, cfg)
    return on_field_answer(s, attempt, cfg)


def on_silence(s: ConversationState) -> PrimaryAction:
    """008's timer fired (FR-14). The channel must not send anything (OQ-2: no_message)."""
    if s.status is not Status.in_progress:
        return NoMessage()
    if s.stage is Stage.scheduling:  # qualified: never "abandoned" (Spec 001 §6)
        return close_qualified_unscheduled(s)
    s.status = Status.abandoned
    s.drop_off_stage = s.stage
    return NoMessage()


def on_slot_event(
    s: ConversationState, event: SlotSelected | NoSlotFits, cfg: EngineConfig
) -> PrimaryAction:
    """010 reports the candidate's pick, or that nothing fits (FR-26, AC-30)."""
    if s.status is not Status.in_progress:
        return ClosedAck()
    if s.pending.kind is not PendingKind.slot:
        return pending_action(s)  # a stale event: nothing changes, ask what we were asking
    if isinstance(event, NoSlotFits):
        return close_qualified_unscheduled(s)
    if event.slot_id in s.offered_slot_ids:
        s.selected_slot_id = event.slot_id
        s.status = Status.interview_scheduled
        return ConfirmInterview(slot_id=event.slot_id)
    offered = tuple(s.offered_slot_ids)
    reask = reask_or_exhaust(s, FieldName.slot, ReaskReason.slot_not_offered, offered, cfg)
    return reask or close_qualified_unscheduled(s)


_CLOSED = frozenset(
    {
        Status.disqualified,
        Status.needs_review,
        Status.qualified_unscheduled,
        Status.interview_scheduled,
    }
)
_PREFACE_ORDER = {"redirect": 0, "ack_correction": 1, "answer_faq": 2}


def finish(
    s: ConversationState, primary: PrimaryAction, prefaces: list[Preface], cfg: EngineConfig
) -> EngineAction:
    """Attach language and register; prefaces in a fixed order (redirect, ack, faq)."""
    location = s.profile.location.value
    register = register_for(
        s.language,
        location.country if location is not None else None,
        s.country_hint,
        default_country=cfg.screening.default_country,
    )
    ordered = sorted(prefaces, key=lambda preface: _PREFACE_ORDER[preface.type])
    return EngineAction(primary=primary, prefaces=ordered, language=s.language, register=register)
