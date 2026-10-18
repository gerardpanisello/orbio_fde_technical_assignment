"""Every acceptance criterion in spec 017 has at least one test marked `017:AC-n`."""

import re

from tests.paths import BACKEND_DIR

SPEC = BACKEND_DIR.parent / "docs" / "specs" / "017-catalan" / "spec.md"
AC_IN_SPEC = re.compile(r"^- (AC-\d+) ", re.MULTILINE)
AC_MARKER = re.compile(r"""mark\.ac\(\s*["']017:(AC-\d+)["']\s*\)""")


def test_every_acceptance_criterion_has_a_test() -> None:
    in_spec = set(AC_IN_SPEC.findall(SPEC.read_text(encoding="utf-8")))
    marked = {
        ac
        for path in (BACKEND_DIR / "tests").rglob("test_*.py")
        for ac in AC_MARKER.findall(path.read_text(encoding="utf-8"))
    }
    assert in_spec == {f"AC-{n}" for n in range(1, 7)}
    assert not in_spec - marked, f"no test for {sorted(in_spec - marked)}"
    assert not marked - in_spec, f"markers for unknown ACs {sorted(marked - in_spec)}"
