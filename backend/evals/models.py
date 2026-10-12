"""Data the eval produces: transcripts, judge verdicts, per-persona results, the run summary.

Everything is a Pydantic model so the JSON report is just `model_dump_json()`.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TurnLog(_Model):
    """One exchange: what the candidate sent (None for Sofi's greeting) and what came back."""

    n: int
    candidate: str | None
    sofi: str | None  # None: Sofi sent nothing
    buttons: list[str] = []
    status: str
    stage: str
    action: str | None  # the engine's primary action type
    extraction: str  # ok / failed / skipped
    phrasing: str  # ok / fallback / skipped
    violations: list[str] = []
    engine_input: dict[str, Any] | None = None  # what extraction gave the engine (debugging)
    cost_usd: float
    latency_ms: int


class Criterion(_Model):
    score: int = Field(ge=1, le=5, description="1 = poor, 5 = excellent")
    reason: str = Field(description="One short sentence; cite the turn number when relevant.")


class JudgeVerdict(_Model):
    """The judge's structured output (spec 001 §7 rubric)."""

    one_question: Criterion
    brevity: Criterion
    tone_persona: Criterion
    language_register: Criterion
    faithfulness: Criterion
    edge_case: Criterion
    worst_turn: int | None = Field(description="Turn number of Sofi's weakest message, if any.")
    worst_comment: str = Field(description="The single most important problem, or 'none'.")


CRITERIA: tuple[str, ...] = (
    "one_question",
    "brevity",
    "tone_persona",
    "language_register",
    "faithfulness",
    "edge_case",
)


class FieldCheck(_Model):
    field: str
    expected: Any
    actual: Any
    ok: bool


class Costs(_Model):
    agent: float = 0.0  # Sofi's turns (extraction + phrasing), from the turn traces
    simulator: float = 0.0
    judge: float = 0.0

    @property
    def total(self) -> float:
        return self.agent + self.simulator + self.judge


class PersonaResult(_Model):
    persona: str
    title: str
    expected_status: str
    actual_status: str
    expected_reason: str | None = None
    actual_reason: str | None = None
    outcome_ok: bool
    field_checks: list[FieldCheck] = []
    candidate_turns: int
    hit_turn_cap: bool = False
    error_flags: list[str] = []  # engine_error / system_failure flags or review reasons
    phrased_turns: int = 0
    fallback_turns: int = 0
    extraction_failures: int = 0
    latencies_ms: list[int] = []
    costs: Costs = Field(default_factory=Costs)
    judge: JudgeVerdict | None = None
    judge_error: str | None = None
    transcript: list[TurnLog] = []
    record: dict[str, Any] = {}
    run_error: str | None = None

    @property
    def field_accuracy(self) -> float | None:
        if not self.field_checks:
            return None
        return sum(c.ok for c in self.field_checks) / len(self.field_checks)


class WorstComment(_Model):
    persona: str
    criterion: str
    score: int
    reason: str


class RunSummary(_Model):
    personas: int
    outcome_pass: int
    field_accuracy: float | None  # micro-average over all scored fields
    mean_turns: float
    fallback_rate: float
    extraction_failure_rate: float
    error_flag_personas: int
    judge_means: dict[str, float]
    judge_overall: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    cost: Costs
    worst: list[WorstComment]


class RunReport(_Model):
    started_at: str
    mode: Literal["fake", "anthropic"]
    today: str
    models: dict[str, str]
    prompts: dict[str, str]
    config_versions: dict[str, str]
    summary: RunSummary
    results: list[PersonaResult]
