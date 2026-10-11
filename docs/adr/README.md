# Architecture Decision Records

One file per significant decision: `NNNN-short-title.md`. Never rewrite history: if a decision changes, add a new ADR that supersedes the old one.

Format: **Status · Context · Decision · Alternatives considered · Consequences.**

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-llm-provider-claude.md) | Claude (Anthropic) as LLM | Accepted |
| [0002](0002-hybrid-state-machine.md) | Hybrid: deterministic state machine + LLM | Accepted |
| [0003](0003-stack-fastapi-react-sqlite.md) | FastAPI + React/Vite + SQLite | Accepted |
| [0004](0004-qualification-rules-and-scoring.md) | Hard disqualifiers + soft scoring | Accepted |
