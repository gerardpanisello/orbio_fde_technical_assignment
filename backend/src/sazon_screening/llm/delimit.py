"""Delimiting conversation text inside a prompt (NFR-4)."""

_LT_LOOKALIKE = "\N{SINGLE LEFT-POINTING ANGLE QUOTATION MARK}"


def tagged(tag: str, text: str) -> str:
    """Wrap text in `<tag>...</tag>`, neutralising `<` inside it.

    Candidate text is data. A candidate typing `</candidate_message>` must not be able to
    close the block and write something that looks like our own instructions.
    """
    return f"<{tag}>{text.replace('<', _LT_LOOKALIKE)}</{tag}>"
