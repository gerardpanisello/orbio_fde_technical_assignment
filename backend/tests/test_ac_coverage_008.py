"""Every backend acceptance criterion in spec 008 has at least one test marked `008:AC-n`.

AC-9 (chat shows reminders, "Avanzar tiempo" button, detail, analytics card) is a
frontend criterion: it is covered by the frontend tests, so it is excluded here, and a
backend marker for it would be an error.
"""

import re

from tests.paths import BACKEND_DIR

SPEC = BACKEND_DIR.parent / "docs" / "specs" / "008-reengagement" / "spec.md"
AC_IN_SPEC = re.compile(r"^- (AC-\d+) ", re.MULTILINE)
AC_MARKER = re.compile(r"""mark\.ac\(\s*["']008:(AC-\d+)["']\s*\)""")
FRONTEND_ONLY = {"AC-9"}


def test_every_backend_acceptance_criterion_has_a_test() -> None:
    in_spec = set(AC_IN_SPEC.findall(SPEC.read_text(encoding="utf-8")))
    marked = {
        ac
        for path in (BACKEND_DIR / "tests").rglob("test_*.py")
        for ac in AC_MARKER.findall(path.read_text(encoding="utf-8"))
    }
    assert in_spec == {f"AC-{n}" for n in range(1, 10)}
    backend = in_spec - FRONTEND_ONLY
    assert not backend - marked, f"no test for {sorted(backend - marked)}"
    assert not marked - backend, f"markers for unknown or frontend ACs {sorted(marked - backend)}"
