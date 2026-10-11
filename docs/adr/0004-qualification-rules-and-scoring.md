# ADR 0004 — Hard disqualifiers + soft scoring

**Status:** Accepted

## Context
80% of recruiter time goes to unqualified candidates, but rejecting good candidates on subjective criteria loses hires and creates fairness risk.

## Decision
- **Hard disqualifiers** (objective, configurable in `config/`): no driver's license, outside service areas, under minimum age (if collected). Candidate gets a kind closing message; recruiter can still override.
- **Everything else is scored**, not rejected: experience (years, platforms), availability breadth, schedule flexibility, start-date proximity. Score → priority bucket (high/medium/low) so recruiters call the best candidates first.
- Weights live in YAML, each score is explainable (list of contributing factors shown in the dashboard).

## Consequences
- Recruiters focus on the top of a ranked list instead of filtering by phone.
- Explainable, auditable scores; no "black box" rejection by the LLM.
- Weights need tuning with real hiring outcomes (future: learn from hired/not-hired).
