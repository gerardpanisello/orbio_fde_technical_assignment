"""The screening agent: one candidate turn is extract -> engine step() -> phrase (FR-1).

Start here to follow a turn. The engine decides everything (ADR 0002): the model only
turns the message into typed input and the engine's action into words, and both
stages degrade on their own (FR-4). One deadline covers the whole turn (NFR-1), and
nothing is persisted here (004 does that).
"""

from collections.abc import Awaitable, Callable, Sequence
from datetime import date

import anyio

from sazon_screening.config import EngineConfig, load_config
from sazon_screening.engine import (
    CandidateRecord,
    ConversationState,
    EngineAction,
    NoSlotFits,
    SilenceExpired,
    SlotSelected,
    TurnContext,
    TurnInput,
    register_for,
    start,
    step,
)
from sazon_screening.llm.client.base import LLMClient, Role
from sazon_screening.llm.client.factory import make_client
from sazon_screening.llm.client.retry import Clock, Deadline, SystemClock
from sazon_screening.llm.extraction.extractor import (
    ExtractionTrace,
    Extractor,
    InboundMessage,
    Skipped,
    TranscriptEntry,
)
from sazon_screening.llm.extraction.pending import pending_view
from sazon_screening.llm.phrasing.catalog import MessageCatalog, load_catalog
from sazon_screening.llm.phrasing.labels import display_name
from sazon_screening.llm.phrasing.phraser import OutboundMessage, Phraser, PhrasingTrace
from sazon_screening.llm.phrasing.templates import NAME_REST, RenderContext
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import LLMConfig, Settings, load_llm_config, load_settings
from sazon_screening.llm.summary.summarizer import Summarizer, Summary, summary_due
from sazon_screening.llm.telemetry import CallTelemetry
from sazon_screening.llm.trace import TurnContextIn, TurnResult, TurnTrace
from sazon_screening.vocab import Language

Event = SilenceExpired | SlotSelected | NoSlotFits
_NO_CONTEXT = TurnContextIn()


class ScreeningAgent:
    def __init__(
        self,
        *,
        client: LLMClient,
        engine_config: EngineConfig,
        llm_config: LLMConfig,
        catalog: MessageCatalog,
        prompts: PromptRegistry,
        clock: Clock | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
    ) -> None:
        self._client = client
        self._engine_config = engine_config
        self._config = llm_config
        self._catalog = catalog
        self._prompts = prompts
        self._clock = clock or SystemClock()
        self._extractor = Extractor(client=client, config=llm_config, prompts=prompts, sleep=sleep)
        self._phraser = Phraser(
            client=client,
            config=llm_config,
            catalog=catalog,
            prompts=prompts,
            engine_config=engine_config,
            sleep=sleep,
        )
        self._summarizer = Summarizer(
            client=client,
            config=llm_config,
            catalog=catalog,
            prompts=prompts,
            engine_config=engine_config,
            clock=self._clock,
            sleep=sleep,
        )

    @property
    def engine_config(self) -> EngineConfig:
        """The rules in force, e.g. for `build_record` at the caller."""
        return self._engine_config

    @property
    def default_summary_language(self) -> Language:
        """The recruiters' language (`llm.yaml`): 004 stores this summary after each close."""
        return self._config.summary_default_language

    # --- the three entry points --------------------------------------------------------

    async def start_conversation(
        self,
        *,
        language: Language = Language.es,
        context: TurnContextIn = _NO_CONTEXT,
        conversation_id: str | None = None,
    ) -> TurnResult:
        """Sofi's greeting: the engine's consent ask, phrased as the introduction (FR-2)."""
        began = self._clock.monotonic()
        state, action = start(
            self._engine_config, language=language, country_hint=context.country_hint
        )
        ctx = self._render_context(state, context, last_message=None, is_greeting=True)
        reply, phrasing, calls = await self._phraser.phrase(
            action, ctx, self._deadline(), conversation_id=conversation_id
        )
        extraction = ExtractionTrace(outcome="skipped", skipped_reason="event")
        trace = self._trace(None, action, extraction, phrasing, calls, began)
        return TurnResult(state=state, reply=reply, trace=trace, summary_due=False)

    async def handle_message(
        self,
        state: ConversationState,
        message: InboundMessage,
        history: Sequence[TranscriptEntry],
        *,
        today: date,
        context: TurnContextIn = _NO_CONTEXT,
        conversation_id: str | None = None,
    ) -> TurnResult:
        began, deadline = self._clock.monotonic(), self._deadline()
        pending = pending_view(state, self._engine_config, self._catalog, context.slot_map())
        result, extraction, calls = await self._extractor.extract(
            message,
            history,
            pending,
            state.language,
            self._turn_context(context),
            deadline,
            conversation_id=conversation_id,
        )
        if isinstance(result, Skipped):  # a voice note: ask them to write; state unchanged
            reply, phrasing = self._media_reply(state)
            trace = self._trace(None, None, extraction, phrasing, calls, began)
            return TurnResult(state=state, reply=reply, trace=trace, summary_due=False)
        return await self._step_and_phrase(
            state,
            result.turn_input,
            today=today,
            context=context,
            last_message=message.text,
            recent_agent=tuple(e.text for e in history if e.role == "agent")[-NAME_REST:],
            extraction=extraction,
            calls=calls,
            began=began,
            deadline=deadline,
            conversation_id=conversation_id,
        )

    async def handle_event(
        self,
        state: ConversationState,
        event: Event,
        *,
        today: date,
        context: TurnContextIn = _NO_CONTEXT,
        conversation_id: str | None = None,
    ) -> TurnResult:
        """Timers (008) and calendars (010): no text, so no extraction (FR-3)."""
        return await self._step_and_phrase(
            state,
            event,
            today=today,
            context=context,
            last_message=None,
            extraction=ExtractionTrace(outcome="skipped", skipped_reason="event"),
            calls=[],
            began=self._clock.monotonic(),
            deadline=self._deadline(),
            conversation_id=conversation_id,
        )

    async def summarise(
        self,
        record: CandidateRecord,
        transcript: Sequence[TranscriptEntry],
        language: Language | None = None,
        *,
        conversation_id: str | None = None,
    ) -> tuple[Summary, list[CallTelemetry]]:
        return await self._summarizer.summarise(
            record, transcript, language, conversation_id=conversation_id
        )

    # --- one turn ------------------------------------------------------------------------

    async def _step_and_phrase(
        self,
        state: ConversationState,
        turn_input: TurnInput,
        *,
        today: date,
        context: TurnContextIn,
        last_message: str | None,
        recent_agent: tuple[str, ...] = (),
        extraction: ExtractionTrace,
        calls: list[CallTelemetry],
        began: float,
        deadline: Deadline,
        conversation_id: str | None,
    ) -> TurnResult:
        new_state, action = step(state, turn_input, self._engine_config, today)  # never raises
        ctx = self._render_context(
            new_state, context, last_message=last_message, recent_agent=recent_agent
        )
        reply, phrasing, phrase_calls = await self._phraser.phrase(
            action, ctx, deadline, conversation_id=conversation_id
        )
        trace = self._trace(turn_input, action, extraction, phrasing, calls + phrase_calls, began)
        due = summary_due(state.status, new_state.status)
        return TurnResult(state=new_state, reply=reply, trace=trace, summary_due=due)

    # --- helpers -------------------------------------------------------------------------

    def _deadline(self) -> Deadline:
        return Deadline(self._clock, self._config.turn_budget_s)

    def _turn_context(self, context: TurnContextIn) -> TurnContext:
        slot_ids = [slot.id for slot in context.slots] if context.slots else None
        return TurnContext(country_hint=context.country_hint, offered_slots=slot_ids)

    def _render_context(
        self,
        state: ConversationState,
        context: TurnContextIn,
        *,
        last_message: str | None,
        recent_agent: tuple[str, ...] = (),
        is_greeting: bool = False,
    ) -> RenderContext:
        name = state.profile.full_name.value or ""
        return RenderContext(
            privacy_url=str(self._config.privacy_url),
            first_name=display_name(name).split()[0] if name.strip() else None,
            last_candidate_message=last_message,
            slots=context.slot_map(),
            is_greeting=is_greeting,
            recent_agent_messages=recent_agent,
        )

    def _media_reply(self, state: ConversationState) -> tuple[OutboundMessage, PhrasingTrace]:
        location = state.profile.location.value
        register = register_for(
            state.language,
            location.country if location else None,
            state.country_hint,
            default_country=self._engine_config.screening.default_country,
        )
        text = self._catalog.for_register(register).templates.media_not_supported
        reply = OutboundMessage(
            text=text, quick_replies=[], language=state.language, register=register
        )
        return reply, PhrasingTrace(outcome="skipped", template_key="media_not_supported")

    def _trace(
        self,
        turn_input: TurnInput | None,
        action: EngineAction | None,
        extraction: ExtractionTrace,
        phrasing: PhrasingTrace,
        calls: list[CallTelemetry],
        began: float,
    ) -> TurnTrace:
        roles = (Role.extraction, Role.phrasing)
        return TurnTrace(
            turn_input=turn_input,
            action=action,
            extraction=extraction,
            phrasing=phrasing,
            calls=calls,
            prompts={role: self._prompt_version(role) for role in roles},
            models={role: self._config.roles[role].model for role in roles},
            client=self._client.name,
            cost_usd=sum(call.cost_usd for call in calls),
            latency_ms=round((self._clock.monotonic() - began) * 1000),
        )

    def _prompt_version(self, role: Role) -> str:
        prompt = self._prompts.load(self._config.roles[role].prompt)
        return f"{prompt.id}@{prompt.sha}"


def build_agent(settings: Settings | None = None) -> ScreeningAgent:
    """Wire everything from the environment and `config/`, failing fast on any problem."""
    settings = settings or load_settings()
    engine_config = load_config(settings.config_dir)
    return ScreeningAgent(
        client=make_client(settings, engine_config=engine_config),
        engine_config=engine_config,
        llm_config=load_llm_config(settings.config_dir),
        catalog=load_catalog(settings.config_dir / "messages"),
        prompts=PromptRegistry(),
    )
