"""Every acceptance criterion in spec 009 has at least one test marked `009:AC-n`.

AC-7 also has a frontend half (the "Preguntas frecuentes" card); the backend half (the
analytics fields) is covered here.
"""

import re

from tests.paths import BACKEND_DIR

SPEC = BACKEND_DIR.parent / "docs" / "specs" / "009-faq-rag" / "spec.md"
AC_IN_SPEC = re.compile(r"^- (AC-\d+) ", re.MULTILINE)
AC_MARKER = re.compile(r"""mark\.ac\(\s*["']009:(AC-\d+)["']\s*\)""")


def test_every_acceptance_criterion_has_a_test() -> None:
    in_spec = set(AC_IN_SPEC.findall(SPEC.read_text(encoding="utf-8")))
    marked = {
        ac
        for path in (BACKEND_DIR / "tests").rglob("test_*.py")
        for ac in AC_MARKER.findall(path.read_text(encoding="utf-8"))
    }
    assert in_spec == {f"AC-{n}" for n in range(1, 9)}
    assert not in_spec - marked, f"no test for {sorted(in_spec - marked)}"
    assert not marked - in_spec, f"markers for unknown ACs {sorted(marked - in_spec)}"
