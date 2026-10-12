"""The LLM judge: grades one whole conversation on the spec 001 §7 rubric.

The model, effort and token limit come from `config/llm.yaml` (role `judge`); the rubric
lives next to this file (`judge.v1.md`), because the product's `judge_phrasing.v1` prompt
grades single replies and is still a placeholder.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from anthropic import AsyncAnthropic

from evals.llm import cost_of
from evals.models import Criterion, JudgeVerdict, TurnLog
from evals.personas import Persona
from sazon_screening.llm.settings import ModelPrice, RoleConfig

PROMPT_FILE = Path(__file__).with_name("judge.v1.md")
PROMPT_ID = "judge.v1"


@dataclass(frozen=True)
class Judgement:
    verdict: JudgeVerdict | None
    error: str | None
    cost_usd: float


class Judge(Protocol):
    async def grade(
        self, persona: Persona, transcript: list[TurnLog], record: dict[str, Any]
    ) -> Judgement: ...


def render_case(persona: Persona, transcript: list[TurnLog], record: dict[str, Any]) -> str:
    """The user turn: the persona's challenge, the numbered transcript and the outcome."""
    lines = []
    for turn in transcript:
        if turn.candidate is not None:
            lines.append(f"T{turn.n} Candidate: {turn.candidate}")
        sofi = turn.sofi if turn.sofi is not None else "(sends nothing)"
        buttons = f"  [buttons: {' | '.join(turn.buttons)}]" if turn.buttons else ""
        lines.append(f"T{turn.n} Sofi: {sofi}{buttons}")
    outcome = {
        "status": record.get("status"),
        "disqualification_reason": record.get("disqualification_reason"),
        "needs_review_reasons": record.get("needs_review_reasons"),
        "language": record.get("language"),
    }
    challenge = f"{persona.title}. Style: {persona.style.strip()}"
    if persona.script.strip():
        challenge += f" Scripted behaviour: {persona.script.strip()}"
    return (
        f"<persona_challenge>\n{challenge}\n</persona_challenge>\n\n"
        f"<transcript>\n{chr(10).join(lines)}\n</transcript>\n\n"
        f"<final_outcome>\n{json.dumps(outcome, ensure_ascii=False)}\n</final_outcome>\n\n"
        "Grade Sofi's messages on the rubric."
    )


class LLMJudge:
    def __init__(self, sdk: AsyncAnthropic, role: RoleConfig, price: ModelPrice | None) -> None:
        self._sdk, self._role, self._price = sdk, role, price
        self._system = PROMPT_FILE.read_text(encoding="utf-8")

    async def grade(
        self, persona: Persona, transcript: list[TurnLog], record: dict[str, Any]
    ) -> Judgement:
        try:
            response = await self._sdk.messages.parse(
                model=self._role.model,
                max_tokens=max(self._role.max_tokens, 4096),  # adaptive thinking shares it
                system=self._system,
                messages=[{"role": "user", "content": render_case(persona, transcript, record)}],
                output_config={"effort": self._role.effort.value},
                output_format=JudgeVerdict,
                timeout=max(self._role.timeout_s, 120),
            )
        except Exception as exc:  # the eval reports a failed judgement, it never crashes
            return Judgement(verdict=None, error=f"{type(exc).__name__}: {exc}", cost_usd=0.0)
        cost = cost_of(response.usage, self._price)
        if response.stop_reason != "end_turn":
            return Judgement(None, f"stop_reason={response.stop_reason}", cost)
        if response.parsed_output is None:
            return Judgement(None, "no parsed output", cost)
        return Judgement(response.parsed_output, None, cost)


class FakeJudge:
    """Offline stand-in: a fixed, mid-scale verdict so the report pipeline can be exercised."""

    async def grade(
        self, persona: Persona, transcript: list[TurnLog], record: dict[str, Any]
    ) -> Judgement:
        mid = Criterion(score=3, reason="fake judge (offline smoke run)")
        verdict = JudgeVerdict(
            one_question=mid,
            brevity=mid,
            tone_persona=mid,
            language_register=mid,
            faithfulness=mid,
            edge_case=mid,
            worst_turn=None,
            worst_comment="none",
        )
        return Judgement(verdict, None, 0.0)
