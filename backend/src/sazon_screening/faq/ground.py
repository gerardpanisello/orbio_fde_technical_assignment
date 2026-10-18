"""From the candidate's question to the approved text Sofi may use (FR-3, FR-4, FR-6).

`answer_question` searches the base for the candidate's country, keeps only confident
hits and returns both the trace (always) and the grounding (only when answered). The
first entry's text is the approved answer: the template, the fake's reply and the
fallback when the model's wording fails the guard. All kept entries go to the model.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from sazon_screening.faq.retrieve import FaqHit, FaqRetriever
from sazon_screening.vocab import Country, Language, Register


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FaqTrace(_Frozen):
    """Per turn with a question: what was asked, what the search found, what we did."""

    question: str
    country: Country | None
    hits: list[FaqHit]  # top-k with scores, best first (whether or not used)
    outcome: Literal["answered", "unanswered"]  # unanswered: flagged for a recruiter
    entry_ids: list[str] = []  # the entries given to phrasing, best first
    entry_question: str | None = None  # the best entry's own question, for analytics
    error: str | None = None  # retrieval itself failed (a bug): answered as unanswered
    # Why it is unanswered: nothing scored high enough, or (FR-8) the phrasing model
    # said the retrieved entries do not answer it. None when answered (or old traces).
    reason: Literal["no_match", "not_relevant", "error"] | None = None

    def not_relevant(self) -> "FaqTrace":
        """FR-8: the entries shared words with the question but did not answer it."""
        return self.model_copy(update={"outcome": "unanswered", "reason": "not_relevant"})


class FaqGrounding(_Frozen):
    answer: str  # the best entry, verbatim: template, fake reply and guard fallback
    approved: tuple[str, ...]  # every kept entry: what the model may answer from


def answer_question(
    retriever: FaqRetriever,
    question: str,
    *,
    country: Country | None,
    register: Register,
    language: Language,
) -> tuple[FaqTrace, FaqGrounding | None]:
    hits = retriever.search(question, country)
    kept = [retriever.base.entry(hit.entry_id) for hit in retriever.confident(hits)]
    if not kept:
        trace = FaqTrace(
            question=question, country=country, hits=hits, outcome="unanswered", reason="no_match"
        )
        return trace, None
    trace = FaqTrace(
        question=question,
        country=country,
        hits=hits,
        outcome="answered",
        entry_ids=[entry.id for entry in kept],
        entry_question=kept[0].first_question(language.fallback),  # ca: recruiters read es
    )
    approved = tuple(entry.answer_for(register) for entry in kept)
    return trace, FaqGrounding(answer=approved[0], approved=approved)


def unanswered(question: str, country: Country | None, error: str | None = None) -> FaqTrace:
    """No knowledge base configured, or the search failed: hold and flag."""
    return FaqTrace(
        question=question,
        country=country,
        hits=[],
        outcome="unanswered",
        error=error,
        reason="error" if error else "no_match",
    )
