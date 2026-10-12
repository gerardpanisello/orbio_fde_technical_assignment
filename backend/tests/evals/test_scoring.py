"""The eval's deterministic scoring and aggregation (evals/), offline and with fake inputs.

The live run itself is a manual dev tool (`python -m evals.run`); these tests make sure
the numbers it reports are computed correctly and that the persona file stays valid.
"""

from datetime import date
from typing import Any

import anyio
import pytest

from evals.judge import FakeJudge
from evals.models import Costs, Criterion, JudgeVerdict, PersonaResult, RunReport, TurnLog
from evals.personas import Persona, Truth, load_personas
from evals.report import render_markdown
from evals.scoring import check_fields, error_flags, outcome_ok, percentile, summarise
from evals.simulator import Line, to_messages

TODAY = date(2026, 10, 13)


def record(status: str = "interview_scheduled", **values: Any) -> dict[str, Any]:
    return {
        "status": status,
        "disqualification_reason": None,
        "flags": [],
        "needs_review_reasons": [],
        "fields": {name: {"status": "confirmed", "value": v} for name, v in values.items()},
    }


def verdict(score: int, reason: str = "r") -> JudgeVerdict:
    c = Criterion(score=score, reason=reason)
    return JudgeVerdict(
        one_question=c,
        brevity=c,
        tone_persona=c,
        language_register=c,
        faithfulness=Criterion(score=max(1, score - 1), reason=f"faith {reason}"),
        edge_case=c,
        worst_turn=None,
        worst_comment="none",
    )


def test_field_checks_tolerate_spelling_order_and_birth_years() -> None:
    truth = Truth.model_validate(
        {
            "full_name": "Lucía Fernández Ruiz",
            "age": 28,
            "location": {"city": "madrid", "zone": "mad-chamberi"},
            "availability": ["part_time", "weekends"],
            "experience": {"years": 2, "platforms": ["glovo", "rappi"]},
            "start_date": ["2026-10-19", "2026-10-20"],
        }
    )
    rec = record(
        full_name="lucia  FERNANDEZ ruiz",
        age={"is_adult": None, "age": None, "birth_year": 1998},  # 2026 - 1998 = 28
        location={"city": "madrid", "zone": "mad-chamberi", "in_service_area": True},
        availability=["weekends", "part_time"],
        experience={"years": 2, "platforms": ["rappi", "glovo"]},
        start_date="2026-10-20",
    )
    fields = ["full_name", "age", "location", "availability", "experience", "start_date"]

    checks = check_fields(truth, fields, rec, TODAY)

    assert [c.field for c in checks if not c.ok] == []


def test_field_checks_catch_wrong_and_missing_values() -> None:
    truth = Truth.model_validate(
        {
            "location": {"out_of_area": True},
            "experience": {"years": 1, "platforms": ["uber_eats"]},
            "has_license": False,
            "start_date": ["2026-10-19", "2026-10-19"],
        }
    )
    rec = record(
        location={"city": "madrid", "zone": None, "in_service_area": True},
        experience={"years": 1, "platforms": []},  # platform lost
        start_date="2026-10-26",  # a week late
    )  # has_license never captured

    checks = check_fields(
        truth, ["location", "experience", "has_license", "start_date"], rec, TODAY
    )

    assert [c.ok for c in checks] == [False, False, False, False]
    assert checks[2].actual is None


def test_outcome_needs_status_and_reason_and_flags_errors() -> None:
    persona = next(p for p in load_personas() if p.id == "marcos-no-license")
    wrong_reason = record("disqualified") | {"disqualification_reason": "out_of_area"}
    right = record("disqualified") | {
        "disqualification_reason": "no_license",
        "flags": ["engine_error", "surname_missing"],
        "needs_review_reasons": ["system_failure"],
    }

    assert not outcome_ok(persona, wrong_reason)
    assert outcome_ok(persona, right)
    assert error_flags(right) == ["engine_error", "system_failure"]


def test_opt_out_passes_only_when_the_record_holds_no_personal_data() -> None:
    persona = next(p for p in load_personas() if p.expect.status.value == "opted_out")

    assert outcome_ok(persona, record("opted_out", full_name=None, age=None))
    assert not outcome_ok(persona, record("opted_out", full_name="Laura Pons Vidal"))


def test_percentile_is_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]  # 1..20
    assert percentile(values, 50) == 10
    assert percentile(values, 95) == 19
    assert percentile([], 50) is None


def test_summary_aggregates_across_personas() -> None:
    good = PersonaResult.model_validate(
        {
            "persona": "a",
            "title": "A",
            "expected_status": "interview_scheduled",
            "actual_status": "interview_scheduled",
            "outcome_ok": True,
            "field_checks": [{"field": f, "expected": 1, "actual": 1, "ok": True} for f in "xyz"],
            "candidate_turns": 10,
            "phrased_turns": 11,
            "fallback_turns": 1,
            "latencies_ms": [1000, 2000],
            "costs": {"agent": 0.02, "simulator": 0.001, "judge": 0.03},
            "judge": verdict(5).model_dump(),
        }
    )
    bad = good.model_copy(
        update={
            "persona": "b",
            "outcome_ok": False,
            "field_checks": [good.field_checks[0].model_copy(update={"ok": False})],
            "candidate_turns": 16,
            "phrased_turns": 9,
            "fallback_turns": 0,
            "extraction_failures": 2,
            "error_flags": ["engine_error"],
            "latencies_ms": [3000, 9000],
            "judge": verdict(2, "too long"),
        }
    )

    s = summarise([good, bad])

    assert (s.personas, s.outcome_pass, s.error_flag_personas) == (2, 1, 1)
    assert s.field_accuracy == pytest.approx(3 / 4)  # micro-average over 4 checks
    assert s.mean_turns == 13
    assert s.fallback_rate == pytest.approx(1 / 20)
    assert s.extraction_failure_rate == pytest.approx(2 / 26)
    assert (s.latency_p50_ms, s.latency_p95_ms) == (2000, 9000)
    assert s.judge_means["brevity"] == pytest.approx(3.5)
    assert s.cost.total == pytest.approx(2 * 0.051)
    worst = s.worst[0]
    assert (worst.persona, worst.criterion, worst.score) == ("b", "faithfulness", 1)
    assert all(w.persona == "b" for w in s.worst)


def test_shipped_personas_are_valid_and_cover_the_edge_cases() -> None:
    personas = load_personas()
    statuses = {p.expect.status.value for p in personas}

    assert len(personas) >= 10
    assert {"interview_scheduled", "disqualified", "opted_out"} <= statuses
    assert {p.expect.reason.value for p in personas if p.expect.reason} == {
        "no_license",
        "out_of_area",
    }
    assert any(p.language.value == "en" for p in personas)


def test_simulator_messages_put_sofi_on_the_user_side_and_end_on_her() -> None:
    chat = [Line("sofi", "¿Aceptas?", ("Sí", "No")), Line("candidate", "sí")]

    messages = to_messages(chat)

    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert "[Buttons: Sí | No]" in str(messages[0]["content"])


def test_report_renders_a_fake_run() -> None:
    persona: Persona = load_personas()[0]
    turns = [
        TurnLog(
            n=0,
            candidate=None,
            sofi="¡Hola! ¿Aceptas?",
            buttons=["Sí", "No"],
            status="in_progress",
            stage="consent",
            action="ask_field",
            extraction="skipped",
            phrasing="fallback",
            violations=["too_long"],
            cost_usd=0.0,
            latency_ms=5,
        )
    ]
    judgement = anyio.run(FakeJudge().grade, persona, turns, record())
    result = PersonaResult(
        persona=persona.id,
        title=persona.title,
        expected_status="interview_scheduled",
        actual_status="in_progress",
        outcome_ok=False,
        candidate_turns=16,
        hit_turn_cap=True,
        costs=Costs(),
        judge=judgement.verdict,
        transcript=turns,
    )
    report = RunReport(
        started_at="2026-10-13 10:00:00",
        mode="fake",
        today="2026-10-13",
        models={"phrasing": "fake"},
        prompts={"judge": "judge.v1"},
        config_versions={"llm.yaml": "x"},
        summary=summarise([result]),
        results=[result],
    )

    md = render_markdown(report)

    assert "| Outcome correct | **0/1** |" in md
    assert f"| `{persona.id}` | ✗ |" in md
    assert "16 (cap)" in md
    assert "**fallback** too_long" in md
