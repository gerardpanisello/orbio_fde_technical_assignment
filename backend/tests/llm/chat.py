"""A test driver that talks to the agent the way a channel would."""

from dataclasses import dataclass, field

from sazon_screening.engine import ConversationState
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.phrasing.guard import check
from sazon_screening.llm.phrasing.templates import RenderContext
from sazon_screening.llm.pipeline import ScreeningAgent
from sazon_screening.llm.settings import LLMConfig
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Country, Language
from tests.llm.builders import SLOTS
from tests.llm.conftest import TODAY

MEXICAN_PHONE = TurnContextIn(country_hint=Country.MX, slots=list(SLOTS.values()))
SPANISH_SCRIPT = [
    "sí, acepto",
    "Me llamo Ana López",
    "tengo 25",
    "moto",
    "sí",
    "vivo en Coyoacán, CDMX",
    "tiempo completo",
    "flexible",
    "2 años de experiencia en Rappi",
    "el lunes",
    "sí, todo bien",
    "el 1",
]


@dataclass
class Chat:
    """Drives an agent like a channel would: keeps the state and the transcript."""

    agent: ScreeningAgent
    llm_config: LLMConfig
    context: TurnContextIn
    state: ConversationState | None = None
    history: list[TranscriptEntry] = field(default_factory=list)
    results: list[TurnResult] = field(default_factory=list)

    async def start(self, language: Language = Language.es) -> TurnResult:
        result = await self.agent.start_conversation(language=language, context=self.context)
        return self._keep(result)

    async def say(self, text: str) -> TurnResult:
        assert self.state is not None
        result = await self.agent.handle_message(
            self.state, InboundMessage(text=text), self.history, today=TODAY, context=self.context
        )
        self.history.append(TranscriptEntry(role="candidate", text=text))
        return self._keep(result)

    def _keep(self, result: TurnResult) -> TurnResult:
        self.state = result.state
        self.results.append(result)
        if result.reply is not None:
            self.history.append(TranscriptEntry(role="agent", text=result.reply.text))
            assert result.trace.action is not None
            ctx = RenderContext(privacy_url=str(self.llm_config.privacy_url))
            assert (
                check(result.reply.text, result.trace.action, ctx, self.llm_config.length_caps)
                == []
            )
        return result
