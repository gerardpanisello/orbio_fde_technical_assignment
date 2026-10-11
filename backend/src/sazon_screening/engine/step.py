"""The engine entry points: `start()` and `step()` (ADR 0005, plan §4.1).

`step` is a pure function of (state, input, config, today). It deep-copies the state on
entry, mutates only that copy, and returns it with exactly one primary action. Read
`on_candidate_turn` top to bottom: it is the FR-10 precedence, one rule per block.
"""

from datetime import date

from sazon_screening.config import EngineConfig
from sazon_screening.engine.actions import (
    AskField,
    ClosedAck,
    EngineAction,
    Preface,
    PrimaryAction,
    register_for,
)
from sazon_screening.engine.closing import close_disqualified, close_needs_review, opt_out
from sazon_screening.engine.collect import (
    apply_proposals,
    classify_attempt,
    on_ask,
    repeat_pending,
)
from sazon_screening.engine.enums import (
    Country,
    FieldName,
    Flag,
    Language,
    ReaskReason,
    ReviewReason,
    Status,
)
from sazon_screening.engine.inputs import CandidateTurn, TurnInput
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
    if (reason := hard_rule_failure(s, cfg)) is not None:
        return close_disqualified(s, reason)

    # (6) the next ask, depending on how this turn answered the pending one.
    neutral = language_changed or signals.faq_question or signals.off_topic or signals.abuse
    attempt = classify_attempt(s, t, applied, neutral=neutral)
    return on_ask(s, attempt, cfg)


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
