"""Interview slots as the caller (spec 010's scheduling) describes them.

The engine only knows slot ids. Their human labels ("martes 10:00") are display data,
used by extraction (to map "el martes" to an id) and by phrasing (to list them). `place`
is where the interview is: the confirmation names it.
"""

from pydantic import BaseModel, ConfigDict

from sazon_screening.vocab import Language


class SlotDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    labels: dict[Language, str]
    place: str | None = None

    def label(self, language: Language) -> str:
        """Catalan without its own label reads the Spanish one ("dimarts" vs "martes")."""
        return self.labels.get(language) or self.labels.get(language.fallback) or self.id
