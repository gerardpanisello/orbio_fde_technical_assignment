"""T28: the terminal demo runs offline end to end (spec 003 §3 "Where a key is needed")."""

import io
import json
from collections.abc import Callable, Iterator

from sazon_screening.llm.demo import main


def scripted_input(*lines: str) -> Callable[[str], str]:
    """Feeds the demo's prompt like a person typing; EOF after the last line."""
    queue: Iterator[str] = iter(lines)

    def read(prompt: str) -> str:
        try:
            return next(queue)
        except StopIteration:
            raise EOFError from None

    return read


def run(*args: str, lines: tuple[str, ...]) -> tuple[int, str]:
    out = io.StringIO()
    code = main(["--today", "2026-10-12", *args], read=scripted_input(*lines), out=out)
    return code, out.getvalue()


def test_consent_by_button_then_name_then_quit() -> None:
    code, output = run(lines=("1", "Me llamo Ana López", "/quit"))
    assert code == 0
    assert "Sofi" in output
    assert "[1] Sí" in output
    assert "¿Cuántos años tienes?" in output
    record = json.loads(output[output.index("{") : output.rindex("}") + 1])
    assert record["fields"]["full_name"]["value"] == "Ana López"
    assert "**Estado:** En curso" in output


def test_a_whole_screening_in_mexico_with_debug() -> None:
    lines = (
        "sí",
        "Ana López",
        "tengo 25",
        "moto",
        "sí",
        "vivo en Coyoacán, CDMX",
        "tiempo completo",
        "flexible",
        "2 años en Rappi",
        "ya",
        "sí",
        "1",
    )
    code, output = run("--country", "MX", "--debug", lines=lines)
    assert code == 0
    assert "licencia de manejo" in output
    assert "engine: offer_slots" in output
    assert "extraction:" in output
    assert '"status": "interview_scheduled"' in output


def test_english_start_and_commands() -> None:
    code, output = run("--lang", "en", lines=("/help", "/state", "/silence", "/summary en"))
    assert code == 0
    assert "I'm Sofi" in output
    assert "/trace" in output  # the help lists the commands
    assert '"status": "abandoned"' in output
    assert "**Status:** Abandoned" in output
