"""Conversation eval: simulated candidates talk to Sofi, then deterministic checks + a judge.

From `backend/`:

    uv run --env-file ../.env python -m evals.run --personas all --out evals/reports/
    uv run python -m evals.run --mode fake                 # offline smoke run, $0
    uv run --env-file ../.env python -m evals.run --personas tom-english,laura-opt-out

Writes `<out>/<timestamp>.md` and `.json`. "Today" is fixed so dates and slots are stable.
The simulated candidate cannot be seeded (the API has no seed), so expect some variance
between runs: compare runs on the summary numbers, not on single transcripts.
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

import anyio
from anthropic import AsyncAnthropic

from evals.judge import PROMPT_ID as JUDGE_PROMPT_ID
from evals.judge import FakeJudge, Judge, LLMJudge
from evals.models import Costs, PersonaResult, RunReport, TurnLog
from evals.personas import Persona, load_personas, select
from evals.report import render_markdown
from evals.scoring import check_fields, error_flags, outcome_ok, summarise
from evals.simulator import (
    SIMULATOR_MODEL,
    FakeSimulator,
    Line,
    LLMSimulator,
    SimReply,
    Simulator,
)
from sazon_screening.api.slots import load_slot_provider
from sazon_screening.engine import build_record
from sazon_screening.llm.client.base import Role
from sazon_screening.llm.extraction.extractor import InboundMessage, TranscriptEntry
from sazon_screening.llm.pipeline import ScreeningAgent, build_agent
from sazon_screening.llm.prompts import PromptRegistry
from sazon_screening.llm.settings import load_llm_config, load_settings
from sazon_screening.llm.trace import TurnContextIn, TurnResult
from sazon_screening.vocab import Status

TODAY = date(2026, 10, 13)  # a Tuesday, as in scripts/sample_conversations.py
MAX_TURNS = 16
DEFAULT_OUT = Path("evals/reports")


@dataclass
class Spend:
    """Running cost across concurrent conversations (one event loop: no lock needed)."""

    budget: float
    total: float = 0.0

    def add(self, amount: float) -> None:
        self.total += amount

    @property
    def exhausted(self) -> bool:
        return self.total >= self.budget


def _log(n: int, candidate: str | None, result: TurnResult) -> TurnLog:
    trace, reply = result.trace, result.reply
    return TurnLog(
        n=n,
        candidate=candidate,
        sofi=reply.text if reply else None,
        buttons=[q.label for q in reply.quick_replies] if reply else [],
        status=result.state.status.value,
        stage=result.state.stage.value,
        action=trace.action.primary.type if trace.action else None,
        extraction=trace.extraction.outcome,
        phrasing=trace.phrasing.outcome,
        violations=list(trace.phrasing.violations),
        engine_input=(
            trace.turn_input.model_dump(mode="json", exclude_none=True, exclude={"context"})
            if trace.turn_input is not None
            else None
        ),
        cost_usd=trace.cost_usd,
        latency_ms=trace.latency_ms,
    )


async def converse(
    agent: ScreeningAgent,
    simulator: Simulator,
    persona: Persona,
    context: TurnContextIn,
    spend: Spend,
) -> PersonaResult:
    """Play one persona to a final status (or the turn cap) and score it deterministically."""
    cid = f"eval-{persona.id}"
    costs = Costs()
    logs: list[TurnLog] = []
    chat: list[Line] = []
    history: list[TranscriptEntry] = []
    forced = {f.turn: SimReply(text=f.text, ended=False) for f in persona.forced}

    def keep(candidate: str | None, result: TurnResult) -> None:
        logs.append(_log(len(logs), candidate, result))
        costs.agent += result.trace.cost_usd
        spend.add(result.trace.cost_usd)
        if result.reply is not None:
            buttons = tuple(q.label for q in result.reply.quick_replies)
            chat.append(Line("sofi", result.reply.text, buttons))
            history.append(TranscriptEntry(role="agent", text=result.reply.text))

    result = await agent.start_conversation(
        language=persona.language, context=context, conversation_id=cid
    )
    keep(None, result)
    turns, hit_cap, run_error = 0, False, None
    try:
        while result.state.status is Status.in_progress:
            if turns >= MAX_TURNS:
                hit_cap = True
                break
            sim = forced.get(turns + 1) or await simulator.reply(persona, chat, result.state)
            costs.simulator += sim.cost_usd
            spend.add(sim.cost_usd)
            if sim.ended or not sim.text:
                break
            chat.append(Line("candidate", sim.text))
            result = await agent.handle_message(
                result.state,
                InboundMessage(text=sim.text),
                history,
                today=TODAY,
                context=context,
                conversation_id=cid,
            )
            history.append(TranscriptEntry(role="candidate", text=sim.text))
            turns += 1
            keep(sim.text, result)
    except Exception as exc:  # a crash is a finding, not the end of the run
        run_error = f"{type(exc).__name__}: {exc}"

    record = build_record(result.state, agent.engine_config).model_dump(mode="json")
    return PersonaResult(
        persona=persona.id,
        title=persona.title,
        expected_status=persona.expect.status.value,
        actual_status=record["status"],
        expected_reason=persona.expect.reason.value if persona.expect.reason else None,
        actual_reason=record.get("disqualification_reason"),
        outcome_ok=outcome_ok(persona, record),
        field_checks=check_fields(persona.truth, persona.expect.fields, record, TODAY),
        candidate_turns=turns,
        hit_turn_cap=hit_cap,
        error_flags=error_flags(record),
        phrased_turns=sum(1 for t in logs if t.phrasing != "skipped"),
        fallback_turns=sum(1 for t in logs if t.phrasing == "fallback"),
        extraction_failures=sum(1 for t in logs if t.extraction == "failed"),
        latencies_ms=[t.latency_ms for t in logs[1:]],  # candidate turns only
        costs=costs,
        transcript=logs,
        record=record,
        run_error=run_error,
    )


async def evaluate(
    agent: ScreeningAgent,
    simulator: Simulator,
    judge: Judge | None,
    persona: Persona,
    context: TurnContextIn,
    spend: Spend,
) -> PersonaResult:
    result = await converse(agent, simulator, persona, context, spend)
    if judge is not None:
        judgement = await judge.grade(persona, result.transcript, result.record)
        result.judge, result.judge_error = judgement.verdict, judgement.error
        result.costs.judge = judgement.cost_usd
        spend.add(judgement.cost_usd)
    mark = "ok " if result.outcome_ok else "BAD"
    acc = result.field_accuracy
    print(
        f"  {mark} {persona.id:<24} {result.actual_status:<22} "
        f"fields {'-' if acc is None else f'{acc:.0%}':>4}  turns {result.candidate_turns:>2}  "
        f"${result.costs.total:.4f}   running total ${spend.total:.4f}",
        flush=True,
    )
    return result


async def run(args: argparse.Namespace) -> RunReport:
    environ = dict(os.environ)
    if args.mode:
        environ["LLM_MODE"] = args.mode
    settings = load_settings(environ)
    llm = load_llm_config(settings.config_dir)
    agent = build_agent(settings)
    personas = select(load_personas(), args.personas)
    # Spec 010: the Madrid agenda from the YAML, nothing booked (evals have no database).
    provider = load_slot_provider(settings.config_dir, agent.engine_config.service_areas)
    slots = provider.preview("madrid", datetime.combine(TODAY, time(9), tzinfo=UTC))
    live = settings.llm_mode == "anthropic"

    simulator: Simulator
    judge: Judge | None
    if live:
        sdk = AsyncAnthropic(max_retries=3)  # reads ANTHROPIC_API_KEY from the environment
        simulator = LLMSimulator(sdk, llm.prices.get(SIMULATOR_MODEL))
        judge_role = llm.roles[Role.judge]
        judge = LLMJudge(sdk, judge_role, llm.prices.get(judge_role.model))
    else:
        simulator, judge = FakeSimulator(), FakeJudge()
    if args.no_judge:
        judge = None

    started = datetime.now()
    spend = Spend(budget=args.budget)
    print(f"{len(personas)} personas, mode {settings.llm_mode}, budget ${args.budget:.2f}")
    results: dict[str, PersonaResult] = {}
    limiter = anyio.Semaphore(args.concurrency)

    async def one(persona: Persona) -> None:
        async with limiter:
            if spend.exhausted:
                print(f"  --- {persona.id}: skipped, budget reached")
                return
            context = TurnContextIn(country_hint=persona.country_hint, slots=slots)
            results[persona.id] = await evaluate(agent, simulator, judge, persona, context, spend)

    async with anyio.create_task_group() as group:
        for persona in personas:
            group.start_soon(one, persona)

    ordered = [results[p.id] for p in personas if p.id in results]
    prompts = {
        role.value: f"{prompt.id}@{prompt.sha}"
        for role in (Role.extraction, Role.phrasing)
        for prompt in [PromptRegistry().load(llm.roles[role].prompt)]
    } | {
        "judge": JUDGE_PROMPT_ID,
        "simulator": "simulator.v1",
    }
    models = {
        "extraction": llm.roles[Role.extraction].model,
        "phrasing": llm.roles[Role.phrasing].model,
        "simulator": SIMULATOR_MODEL if live else "fake",
        "judge": llm.roles[Role.judge].model if live and judge else "fake",
    }
    engine_version = ordered[0].record.get("config_version", "") if ordered else ""
    return RunReport(
        started_at=started.strftime("%Y-%m-%d %H:%M:%S"),
        mode=settings.llm_mode,
        today=TODAY.isoformat(),
        models=models,
        prompts=prompts,
        config_versions={"llm.yaml": llm.version, "screening.yaml": str(engine_version)},
        summary=summarise(ordered),
        results=ordered,
    )


def write(report: RunReport, out: Path) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.strptime(report.started_at, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d-%H%M%S")
    suffix = "" if report.mode == "anthropic" else "-fake"
    md, js = out / f"{stamp}{suffix}.md", out / f"{stamp}{suffix}.json"
    md.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    js.write_text(report.model_dump_json(indent=2), encoding="utf-8", newline="\n")
    return md, js


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the conversation eval.")
    parser.add_argument("--personas", default="all", help="'all' or comma-separated ids")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="report directory")
    parser.add_argument("--mode", choices=["fake", "anthropic"], help="overrides LLM_MODE")
    parser.add_argument("--budget", type=float, default=2.0, help="USD: stop starting personas")
    parser.add_argument("--concurrency", type=int, default=3, help="conversations at once")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM judge")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles may not speak UTF-8
        sys.stdout.reconfigure(errors="replace")
    report = anyio.run(run, args)
    md, js = write(report, args.out)
    s = report.summary
    print(
        f"\noutcomes {s.outcome_pass}/{s.personas} · fields "
        f"{'-' if s.field_accuracy is None else f'{s.field_accuracy:.0%}'} · judge "
        f"{'-' if s.judge_overall is None else f'{s.judge_overall:.2f}'} · "
        f"total ${s.cost.total:.4f}\n-> {md}\n-> {js}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
