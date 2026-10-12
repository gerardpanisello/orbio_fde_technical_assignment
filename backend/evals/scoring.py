"""Deterministic checks (no LLM): field accuracy against ground truth, outcome, aggregation.

Pure functions over the record JSON (`CandidateRecord.model_dump(mode="json")`) and the
result models, so they are unit-tested offline (tests/evals/test_scoring.py).
"""

import math
import unicodedata
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from evals.models import (
    CRITERIA,
    Costs,
    FieldCheck,
    PersonaResult,
    RunSummary,
    WorstComment,
)
from evals.personas import Persona, Truth
from sazon_screening.vocab import Status

ERROR_MARKERS = frozenset({"engine_error", "system_failure"})


def fold(text: str) -> str:
    """Case-, accent- and whitespace-insensitive form, for comparing names."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def _value(record: dict[str, Any], name: str) -> Any:
    fields = record.get("fields") or {}
    entry = fields.get(name) or {}
    return entry.get("value")


def _age_ok(expected: int, actual: Any, today: date) -> bool:
    if not isinstance(actual, dict):
        return False
    if actual.get("age") is not None:
        return bool(actual["age"] == expected)
    year = actual.get("birth_year")
    if year is not None:  # the birthday may not have passed yet this year
        return today.year - int(year) in (expected, expected + 1)
    return False


def _location_ok(expected: Any, actual: Any) -> bool:
    if not isinstance(actual, dict):
        return False
    if expected.out_of_area:
        return actual.get("in_service_area") is False
    return bool(actual.get("city") == expected.city and actual.get("zone") == expected.zone)


def _experience_ok(expected: Any, actual: Any) -> bool:
    if not isinstance(actual, dict):
        return False
    return bool(
        actual.get("years") == expected.years
        and set(actual.get("platforms") or []) == set(expected.platforms)
    )


def _start_ok(expected: tuple[date, date], actual: Any) -> bool:
    if not isinstance(actual, str):
        return False
    try:
        day = date.fromisoformat(actual)
    except ValueError:
        return False
    return expected[0] <= day <= expected[1]


def _same_set(expected: Sequence[str], actual: Any) -> bool:
    return isinstance(actual, list) and set(actual) == set(expected)


def _comparators(today: date) -> dict[str, Callable[[Any, Any], bool]]:
    return {
        "full_name": lambda e, a: isinstance(a, str) and fold(a) == fold(e),
        "age": lambda e, a: _age_ok(e, a, today),
        "vehicle_type": lambda e, a: a == e,
        "has_license": lambda e, a: a is e,
        "location": _location_ok,
        "availability": _same_set,
        "schedule": _same_set,
        "experience": _experience_ok,
        "start_date": _start_ok,
    }


def _plain(value: Any) -> Any:
    """JSON-friendly form of a truth value, for the report."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_defaults=True)
    if isinstance(value, tuple):
        return [v.isoformat() if isinstance(v, date) else v for v in value]
    return value


def check_fields(
    truth: Truth, fields: Sequence[str], record: dict[str, Any], today: date
) -> list[FieldCheck]:
    """One check per scored field: does the record hold the ground-truth value?"""
    compare = _comparators(today)
    checks = []
    for name in fields:
        expected = getattr(truth, name)
        actual = _value(record, name)
        checks.append(
            FieldCheck(
                field=name,
                expected=_plain(expected),
                actual=actual,
                ok=compare[name](expected, actual),
            )
        )
    return checks


def outcome_ok(persona: Persona, record: dict[str, Any]) -> bool:
    if record.get("status") != persona.expect.status.value:
        return False
    reason = persona.expect.reason
    if reason is not None and record.get("disqualification_reason") != reason.value:
        return False
    if persona.expect.status is Status.opted_out:  # an opt-out keeps no personal data
        return all(_value(record, name) is None for name in record.get("fields") or {})
    return True


def error_flags(record: dict[str, Any]) -> list[str]:
    """engine_error / system_failure markers, from flags or review reasons."""
    found = set(record.get("flags") or []) | set(record.get("needs_review_reasons") or [])
    return sorted(found & ERROR_MARKERS)


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile; None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return float(ordered[rank - 1])


def _ratio(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def worst_comments(results: Sequence[PersonaResult], limit: int = 3) -> list[WorstComment]:
    """The lowest-scored judge criteria across the run (ties: run order)."""
    items = [
        WorstComment(
            persona=r.persona,
            criterion=c,
            score=getattr(r.judge, c).score,
            reason=getattr(r.judge, c).reason,
        )
        for r in results
        if r.judge is not None
        for c in CRITERIA
    ]
    return sorted(items, key=lambda w: w.score)[:limit]


def summarise(results: Sequence[PersonaResult]) -> RunSummary:
    checks = [c for r in results for c in r.field_checks]
    phrased = sum(r.phrased_turns for r in results)
    turns = sum(r.candidate_turns for r in results)
    judged = [r for r in results if r.judge is not None]
    judge_means = {
        c: sum(getattr(r.judge, c).score for r in judged) / len(judged) for c in CRITERIA if judged
    }
    latencies = [float(ms) for r in results for ms in r.latencies_ms]
    return RunSummary(
        personas=len(results),
        outcome_pass=sum(r.outcome_ok for r in results),
        field_accuracy=_ratio(sum(c.ok for c in checks), len(checks)) if checks else None,
        mean_turns=turns / len(results) if results else 0.0,
        fallback_rate=_ratio(sum(r.fallback_turns for r in results), phrased),
        extraction_failure_rate=_ratio(sum(r.extraction_failures for r in results), turns),
        error_flag_personas=sum(1 for r in results if r.error_flags),
        judge_means=judge_means,
        judge_overall=sum(judge_means.values()) / len(judge_means) if judge_means else None,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        cost=Costs(
            agent=sum(r.costs.agent for r in results),
            simulator=sum(r.costs.simulator for r in results),
            judge=sum(r.costs.judge for r in results),
        ),
        worst=worst_comments(results),
    )
