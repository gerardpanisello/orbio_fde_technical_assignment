"""LLM layer (spec 003): extract -> engine step() -> phrase, plus the recruiter summary.

The engine decides everything (ADR 0002). This package only turns candidate text into
typed engine input and engine actions into text, and every LLM output is checked by
code before it is used (ADR 0006). I/O here is async; the engine stays sync (ADR 0007).
"""
