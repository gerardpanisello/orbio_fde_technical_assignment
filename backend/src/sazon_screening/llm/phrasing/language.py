"""A deliberately conservative language check: Spanish, English, Catalan or "can't tell".

Used by the guard (FR-15, plan OQ-5) to catch a reply in the wrong language. It must
never reject short or mixed text ("¡Genial, Ana! ¿Tienes Glovo?"), so it only answers
when one language clearly dominates; otherwise it returns None and nothing fires.

Catalan (spec 017) shares many short words with Spanish ("de", "la", "que", "en") and a
few with English ("a", "i", "on"). So Catalan is told apart by words only Catalan has
("amb", "els", "teva", "què"), against words only Spanish has ("con", "los", "qué").
Text with some Catalan evidence that does not clearly dominate is "can't tell": a
Catalan reply is never rejected as Spanish, and Spanish/English answers are unchanged
for text without Catalan-only words.
"""

import re

from sazon_screening.vocab import Language

_WORDS = re.compile(r"[a-záéíóúñüàèòïç·]+")
_SPANISH = """
el la los las de del que y en un una por para con no se es tu te me mi lo al más pero
como ya muy sí está estás son qué cuál cuándo cómo dónde hay tienes puedes quieres
gracias hola perfecto vale
"""
_ENGLISH = """
the a an of to and in on for with is are you your do does what which when how where
there have has can will would please thanks thank hi hello it this that be we our i
"""
# Words only Catalan has (not Spanish, not English): function words and the verbs Sofi uses.
_CATALAN = """
els amb per perquè dels pel pels però com ja molt més està estàs són què quin quina
quins quines quan quant quants quanta hi ho tens pots vols vulguis gràcies perfecte
acord teu teva teus teves et em ens aquest aquesta aquests això doncs també fins
vull puc tinc ets sóc és bé avui demà mentre llavors entesos
"""
# Words Catalan shares with Spanish or English: no evidence either way against Catalan.
_SHARED_WITH_CATALAN = "el la les de del que en un una no es te me mi al sí hola tu a i on has"

_ES = frozenset(_SPANISH.split())
_EN = frozenset(_ENGLISH.split())
_CA_ONLY = frozenset(_CATALAN.split()) - _ES - _EN
_SHARED = frozenset(_SHARED_WITH_CATALAN.split())
_ES_ONLY = _ES - _CA_ONLY - _SHARED
_EN_ONLY = _EN - _CA_ONLY - _SHARED
_MIN_HITS = 3  # fewer stopwords than this: too short to judge
_DOMINANCE = 3  # one language needs 3x the other's stopwords


def dominant_language(text: str) -> Language | None:
    words = _WORDS.findall(text.lower())

    def hits(stop: frozenset[str]) -> int:
        return sum(word in stop for word in words)

    ca, es_only, en_only = hits(_CA_ONLY), hits(_ES_ONLY), hits(_EN_ONLY)
    if ca >= _MIN_HITS and ca >= _DOMINANCE * max(es_only, en_only, 1):
        return Language.ca
    if ca and max(es_only, en_only) < _DOMINANCE * ca:
        return None  # some Catalan, not enough to tell it from Spanish or English
    es, en = hits(_ES), hits(_EN)
    if es >= _MIN_HITS and es >= _DOMINANCE * max(en, 1):
        return Language.es
    if en >= _MIN_HITS and en >= _DOMINANCE * max(es, 1):
        return Language.en
    return None
