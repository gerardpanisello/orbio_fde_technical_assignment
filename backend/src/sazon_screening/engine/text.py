"""Text normalisation shared by location and platform matching."""

import re
import unicodedata


def normalise(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form used to compare place names.

    "COYOACÁN" and "coyoacan" must be the same place; candidates type on phones.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    spaced = re.sub(r"[^\w\s]|_", " ", without_marks.casefold())
    return " ".join(spaced.split())
