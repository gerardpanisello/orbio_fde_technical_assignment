"""Interview slots as the caller (010 later; the demo for now) describes them.

The engine only knows slot ids. Their human labels ("martes 10:00") are display data,
used by extraction (to map "el martes" to an id) and by phrasing (to list them).
"""

from pydantic import BaseModel, ConfigDict

from sazon_screening.vocab import Language


class SlotDisplay(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    labels: dict[Language, str]

    def label(self, language: Language) -> str:
        return self.labels.get(language) or self.id
