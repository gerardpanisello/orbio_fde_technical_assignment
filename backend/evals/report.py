"""Render a run as Markdown (for people) next to the JSON (for diffs and tooling)."""

from evals.models import CRITERIA, PersonaResult, RunReport, TurnLog
from evals.scoring import percentile

_SHORT = {
    "one_question": "1Q",
    "brevity": "Brev",
    "tone_persona": "Tone",
    "language_register": "Lang",
    "faithfulness": "Faith",
    "edge_case": "Edge",
}


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value / 1000:.1f} s"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _scores(result: PersonaResult) -> list[str]:
    if result.judge is None:
        return ["-"] * len(CRITERIA)
    return [str(getattr(result.judge, c).score) for c in CRITERIA]


def _row(result: PersonaResult) -> str:
    lat = [float(x) for x in result.latencies_ms]
    status = result.actual_status
    if result.actual_reason:
        status += f" ({result.actual_reason})"
    cells = [
        f"`{result.persona}`",
        "✓" if result.outcome_ok else "✗",
        f"{result.expected_status} → {status}",
        _pct(result.field_accuracy),
        str(result.candidate_turns) + (" (cap)" if result.hit_turn_cap else ""),
        *_scores(result),
        f"{result.costs.agent:.4f}",
        _ms(percentile(lat, 50)),
        _ms(percentile(lat, 95)),
    ]
    return "| " + " | ".join(cells) + " |"


def _transcript(turns: list[TurnLog]) -> list[str]:
    out = []
    for t in turns:
        if t.candidate is not None:
            out.append(f"- **T{t.n} Candidate:** {_cell(t.candidate)}")
        sofi = "_(nothing)_" if t.sofi is None else _cell(t.sofi)
        extras = [f"`{t.action}`" if t.action else "", f"status `{t.status}`"]
        if t.phrasing == "fallback":
            extras.append(f"**fallback** {', '.join(t.violations)}")
        if t.extraction == "failed":
            extras.append("**extraction failed**")
        buttons = f" [{' \\| '.join(t.buttons)}]" if t.buttons else ""
        meta = " · ".join(e for e in extras if e)
        out.append(f"- **T{t.n} Sofi:** {sofi}{buttons}  \n  <sub>{meta}</sub>")
    return out


def render_markdown(report: RunReport) -> str:
    s = report.summary
    header = ["Persona", "Outcome", "Expected → actual", "Fields", "Turns"]
    header += [_SHORT[c] for c in CRITERIA] + ["Sofi $", "p50", "p95"]
    out = [
        f"# Conversation eval, {report.started_at}",
        "",
        f"Mode `{report.mode}` · today = {report.today} · "
        + " · ".join(f"{role} `{model}`" for role, model in report.models.items()),
        "",
        "Prompts: "
        + ", ".join(f"`{p}`" for p in report.prompts.values())
        + " · config: "
        + ", ".join(f"{k} `{v}`" for k, v in report.config_versions.items()),
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Outcome correct | **{s.outcome_pass}/{s.personas}** |",
        f"| Field accuracy (all scored fields) | **{_pct(s.field_accuracy)}** |",
        f"| Mean candidate turns | {s.mean_turns:.1f} |",
        f"| Phrasing fallback rate | {_pct(s.fallback_rate)} |",
        f"| Extraction failure rate | {_pct(s.extraction_failure_rate)} |",
        f"| Personas with engine_error / system_failure | {s.error_flag_personas} |",
        f"| Turn latency p50 / p95 | {_ms(s.latency_p50_ms)} / {_ms(s.latency_p95_ms)} |",
        "| Judge mean (1-5) | "
        + ("-" if s.judge_overall is None else f"**{s.judge_overall:.2f}**")
        + " |",
        f"| Cost: Sofi / simulator / judge / total | ${s.cost.agent:.4f} / "
        f"${s.cost.simulator:.4f} / ${s.cost.judge:.4f} / **${s.cost.total:.4f}** |",
        "",
        "## Per persona",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
        *[_row(r) for r in report.results],
    ]
    if s.judge_means:
        means = [f"{s.judge_means[c]:.1f}" for c in CRITERIA]
        out.append("| **mean** | | | | | " + " | ".join(means) + " | | | |")
    out += [
        "",
        "Judge criteria: 1Q one question per message, Brev brevity, Tone tone and persona, "
        "Lang language and register, Faith no invented facts or promises, Edge handled the "
        "persona's edge case. Sofi $ = extraction + phrasing cost of the conversation.",
        "",
        "## Worst judge comments",
        "",
    ]
    out += [f"- `{w.persona}` · {w.criterion} = {w.score}: {w.reason}" for w in s.worst] or [
        "_(no judge verdicts)_"
    ]
    misses = [(r.persona, c) for r in report.results for c in r.field_checks if not c.ok]
    out += ["", "## Field mismatches", ""]
    out += [
        f"- `{p}` · {c.field}: expected `{c.expected}`, got `{c.actual}`" for p, c in misses
    ] or ["_(none)_"]
    problems = [r for r in report.results if r.judge_error or r.run_error]
    if problems:
        out += ["", "## Errors", ""]
        out += [f"- `{r.persona}`: {r.run_error or ''} {r.judge_error or ''}" for r in problems]
    out += ["", "## Transcripts", ""]
    for r in report.results:
        out += [f"<details><summary><code>{r.persona}</code>: {r.title}</summary>", ""]
        if r.judge is not None:
            out += [f"Judge, worst turn T{r.judge.worst_turn}: {r.judge.worst_comment}", ""]
            out += [
                f"- {c}: {getattr(r.judge, c).score} · {getattr(r.judge, c).reason}"
                for c in CRITERIA
            ]
            out.append("")
        out += _transcript(r.transcript)
        out += ["", "</details>", ""]
    return "\n".join(out).rstrip() + "\n"
