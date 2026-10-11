"""A deliberately conservative language check: Spanish or English, or "can't tell".

Used by the guard (FR-15, plan OQ-5) to catch a reply in the wrong language. It must
never reject short or mixed text ("¡Genial, Ana! ¿Tienes Glovo?"), so it only answers
when one language clearly dominates; otherwise it returns None and nothing fires.
"""

import re

from sazon_screening.vocab import Language

_WORDS = re.compile(r"[a-záéíóúñü]+")
_SPANISH = """
el la los las de del que y en un una por para con no se es tu te me mi lo al más pero
como ya muy sí está estás son qué cuál cuándo cómo dónde hay tienes puedes quieres
gracias hola perfecto vale
"""
_ENGLISH = """
the a an of to and in on for with is are you your do does what which when how where
there have has can will would please thanks thank hi hello it this that be we our i
"""
_STOPWORDS = {Language.es: frozenset(_SPANISH.split()), Language.en: frozenset(_ENGLISH.split())}
_MIN_HITS = 3  # fewer stopwords than this: too short to judge
_DOMINANCE = 3  # one language needs 3x the other's stopwords


def dominant_language(text: str) -> Language | None:
    words = _WORDS.findall(text.lower())
    hits = {lang: sum(word in stop for word in words) for lang, stop in _STOPWORDS.items()}
    es, en = hits[Language.es], hits[Language.en]
    if es >= _MIN_HITS and es >= _DOMINANCE * max(en, 1):
        return Language.es
    if en >= _MIN_HITS and en >= _DOMINANCE * max(es, 1):
        return Language.en
    return None
