"""Chat with Sofi in the terminal (spec 003 §3 "Where a real API key is needed").

    uv run python -m sazon_screening.llm.demo --lang es            # offline, rules mode
    uv run python -m sazon_screening.llm.demo --country MX --debug  # Mexico, show internals
    uv run --env-file ../.env python -m sazon_screening.llm.demo --mode anthropic

Type a reply, or the number of a button. Commands: /help /trace /state /silence
/summary [es|en] /quit. At the end it prints the candidate record and the summary.

This is the system's edge, like 004 will be: the only place in the layer that reads the
calendar (`today`) and the console.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import TextIO

import anyio

from sazon_screening.engine import CandidateTurn, ConversationState, SilenceExpired, build_record
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.phrasing.phraser import OutboundMessage
from sazon_screening.llm.pipeline import ScreeningAgent, build_agent
from sazon_screening.llm.settings import load_settings
from sazon_screening.llm.slots import SlotDisplay
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Country, Language

HELP = """Commands:
  /trace           the last turn's trace (JSON)
  /state           the conversation state (JSON)
  /silence         the candidate goes quiet (sends silence_expired)
  /summary [es|en] the recruiter summary now
  /quit            end: print the record and the summary
Type a number to tap a button."""

Reader = Callable[[str], str]


def demo_slots(today: date) -> list[SlotDisplay]:
    """Three interview slots on the next weekdays (010 will supply real ones)."""
    days = [today + timedelta(days=n) for n in range(1, 8)]
    weekdays = [d for d in days if d.weekday() < 5][:3]
    times = ("10:00", "12:30", "17:00")
    return [
        SlotDisplay(
            id=f"slot-{n}",
            labels={
                Language.es: f"{_ES_DAYS[day.weekday()]} {day:%d/%m}, {hour}",
                Language.en: f"{day:%a %d %b}, {hour}",
            },
        )
        for n, (day, hour) in enumerate(zip(weekdays, times, strict=True), start=1)
    ]


_ES_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


class Demo:
    def __init__(self, agent: ScreeningAgent, args: argparse.Namespace, read: Reader, out: TextIO):
        self.agent, self.args, self.read, self.out = agent, args, read, out
        country = Country(args.country) if args.country else None
        self.context = TurnContextIn(country_hint=country, slots=demo_slots(args.today))
        self.state: ConversationState | None = None
        self.last: TurnResult | None = None
        self.transcript: list[TranscriptEntry] = []

    async def run(self) -> int:
        language = Language(self.args.lang)
        self.show(await self.agent.start_conversation(language=language, context=self.context))
        while True:
            try:
                line = self.read("\nTú / You > ").strip()
            except EOFError:
                break
            if line in ("/quit", "/exit"):
                break
            if line.startswith("/"):
                await self.command(line)
            elif line:
                await self.message(line)
        await self.finish()
        return 0

    async def message(self, line: str) -> None:
        assert self.state is not None
        text = self.button_label(line) or line
        if text != line:
            self.print(f"  (→ {text})")
        result = await self.agent.handle_message(
            self.state,
            InboundMessage(text=text),
            self.transcript,
            today=self.args.today,
            context=self.context,
        )
        self.transcript.append(TranscriptEntry(role="candidate", text=text))
        self.show(result)

    async def command(self, line: str) -> None:
        name, _, argument = line.partition(" ")
        assert self.state is not None
        if name == "/trace" and self.last is not None:
            self.print(self.last.trace.model_dump_json(indent=2))
        elif name == "/state":
            self.print(self.state.model_dump_json(indent=2))
        elif name == "/silence":
            event = SilenceExpired()
            self.show(await self.agent.handle_event(self.state, event, today=self.args.today))
        elif name == "/summary":
            await self.summary(Language(argument.strip() or "es"))
        else:
            self.print(HELP)

    async def finish(self) -> None:
        assert self.state is not None
        record = build_record(self.state, self.agent.engine_config)
        self.print("\n=== Candidate record ===")
        self.print(json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False))
        await self.summary(Language.es)

    async def summary(self, language: Language) -> None:
        assert self.state is not None
        record = build_record(self.state, self.agent.engine_config)
        summary, _ = await self.agent.summarise(record, self.transcript, language)
        self.print(f"\n=== Recruiter summary ({language.value}, {summary.generated_by}) ===")
        self.print(summary.text)

    # --- output --------------------------------------------------------------------------

    def show(self, result: TurnResult) -> None:
        started = time.perf_counter()
        self.state, self.last = result.state, result
        if self.args.debug:
            self.debug(result)
        if result.reply is None:
            self.print("  (Sofi sends nothing)")
        else:
            self.transcript.append(TranscriptEntry(role="agent", text=result.reply.text))
            self.print_reply(result.reply)
        trace = result.trace
        elapsed = trace.latency_ms + round((time.perf_counter() - started) * 1000)
        self.print(
            f"  · {trace.client} · {elapsed} ms · ${trace.cost_usd:.4f} · {result.state.status}"
        )
        if result.summary_due:
            self.print("  · the conversation reached a final status: /summary or /quit")

    def print_reply(self, reply: OutboundMessage) -> None:
        self.print("\nSofi: " + reply.text.replace("\n", "\n      "))
        if reply.quick_replies:
            buttons = "  ".join(f"[{n}] {r.label}" for n, r in enumerate(reply.quick_replies, 1))
            self.print(f"      {buttons}")

    def debug(self, result: TurnResult) -> None:
        trace = result.trace
        turn = trace.turn_input
        if isinstance(turn, CandidateTurn):
            proposals = [p.model_dump(mode="json") for p in turn.proposals]
            signals = turn.signals.model_dump(mode="json", exclude_defaults=True)
            self.print(f"  extraction: {json.dumps(proposals, ensure_ascii=False)} {signals}")
        elif turn is not None:
            self.print(f"  extraction: {turn.model_dump_json()}")
        if trace.extraction.dropped:
            self.print(f"  dropped: {[d.model_dump() for d in trace.extraction.dropped]}")
        if trace.action is not None:
            prefaces = [p.type for p in trace.action.prefaces]
            primary = trace.action.primary.model_dump(mode="json", exclude={"profile"})
            self.print(f"  engine: {trace.action.primary.type} {primary} prefaces={prefaces}")
        self.print(f"  phrasing: {trace.phrasing.outcome} {trace.phrasing.violations or ''}")

    def button_label(self, line: str) -> str | None:
        """ "2" taps the second button: the demo sends its label, as a chat channel would."""
        reply = self.last.reply if self.last else None
        if reply is None or not line.isdigit():
            return None
        index = int(line) - 1
        return reply.quick_replies[index].label if 0 <= index < len(reply.quick_replies) else None

    def print(self, text: str) -> None:
        print(text, file=self.out)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with Sofi in the terminal.")
    parser.add_argument("--mode", choices=["fake", "anthropic"], help="overrides LLM_MODE")
    parser.add_argument("--lang", choices=["es", "en"], default="es", help="greeting language")
    parser.add_argument("--country", choices=["ES", "MX"], help="phone country (register)")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--debug", action="store_true", help="show extraction and engine action")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, read: Reader = input, out: TextIO = sys.stdout) -> int:
    args = parse_args(argv)
    environ = dict(os.environ)
    if args.mode:
        environ["LLM_MODE"] = args.mode
    agent = build_agent(load_settings(environ))
    if hasattr(out, "reconfigure"):  # a Windows console may not speak UTF-8: never crash on emoji
        out.reconfigure(errors="replace")
    demo = Demo(agent, args, read, out)
    return anyio.run(demo.run)


if __name__ == "__main__":
    sys.exit(main())
