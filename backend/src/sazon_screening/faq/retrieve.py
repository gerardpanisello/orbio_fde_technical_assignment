"""Lexical FAQ search: a small BM25 over each entry's question variants and tags (FR-2).

Deterministic and offline: the same question always gets the same entries and scores,
so tests need no model and a recruiter can see why an answer was chosen. Both sides
are normalised the same way: no accents or case, a few stopwords out, and a light
es/en stemmer that strips plural and verb endings ("pagan", "paga", "pago" -> "pag").
"""

import math
import re
import unicodedata
from collections import Counter

from pydantic import BaseModel, ConfigDict

from sazon_screening.faq.models import FaqBase, FaqEntry
from sazon_screening.vocab import Country

_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = (
    "a al como con de del el en es la las lo los me mi mis o para por que se si su te "
    "tu un una uno y yo hay hace cual cuales "
    "an and are as at be can do does for how i in is it my of on or the to what "
    "when which who will with you your there like s t"
)
_STOP = frozenset(_STOP_WORDS.split())
# Longer endings first, so "iendo" goes before "o". Only stripped if a 3-letter stem is left.
_SUFFIXES = (
    "aciones", "iendo", "ando", "amos", "emos", "imos", "aron", "ieron", "ados", "idos",
    "ing", "ado", "ido", "ar", "er", "ir", "an", "en", "as", "es", "os", "ed",
    "a", "e", "o", "s",
)  # fmt: skip


def fold(text: str) -> str:
    """Lowercase without accents: "¿Cuánto?" and "cuanto" are the same word."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(fold(text)) if w not in _STOP]


class FaqHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str
    score: float


class FaqRetriever:
    """Indexes the base once; `search` is a few dictionary lookups per query word."""

    def __init__(self, base: FaqBase) -> None:
        self._base = base
        self._docs = [Counter(_document(entry)) for entry in base.entries]
        self._avg_len = sum(d.total() for d in self._docs) / len(self._docs)
        df = Counter(word for doc in self._docs for word in doc)
        n = len(self._docs)
        self._idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    @property
    def base(self) -> FaqBase:
        return self._base

    def search(self, question: str, country: Country | None) -> list[FaqHit]:
        """The top-k entries for this country, best first, with their BM25 scores."""
        query = set(tokens(question))
        cfg = self._base.retrieval
        hits = []
        for entry, doc in zip(self._base.entries, self._docs, strict=True):
            if not entry.applies_to(country):
                continue
            score = sum(self._term(word, doc) for word in query)
            if score > 0 and entry.country != "all":
                score *= cfg.country_boost  # known country: its own entry first
            if score > 0:
                hits.append(FaqHit(entry_id=entry.id, score=round(score, 3)))
        hits.sort(key=lambda hit: (-hit.score, hit.entry_id))
        return hits[: cfg.top_k]

    def confident(self, hits: list[FaqHit]) -> list[FaqHit]:
        """Hits good enough to answer from: above the threshold and close to the best."""
        cfg = self._base.retrieval
        if not hits or hits[0].score < cfg.min_score:
            return []
        floor = max(cfg.min_score, hits[0].score * cfg.relative_min)
        return [hit for hit in hits if hit.score >= floor]

    def _term(self, word: str, doc: Counter[str]) -> float:
        tf = doc.get(word, 0)
        if not tf:
            return 0.0
        k1, b = self._base.retrieval.k1, self._base.retrieval.b
        norm = tf + k1 * (1 - b + b * doc.total() / self._avg_len)
        return self._idf[word] * tf * (k1 + 1) / norm


def _document(entry: FaqEntry) -> list[str]:
    texts = [q for variants in entry.questions.values() for q in variants] + entry.tags
    return [word for text in texts for word in tokens(text)]
