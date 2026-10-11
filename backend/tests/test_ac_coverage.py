"""T30: every acceptance criterion in spec 002 has at least one marked test (NFR-3)."""

import re

from tests.paths import BACKEND_DIR

SPEC = BACKEND_DIR.parent / "docs" / "specs" / "002-screening-engine" / "spec.md"
TESTS_DIR = BACKEND_DIR / "tests"

AC_IN_SPEC = re.compile(r"^- \[[ x]\] (AC-\d+[a-z]?):", re.MULTILINE)
AC_MARKER = re.compile(r"""mark\.ac\(\s*["'](AC-\d+[a-z]?)["']\s*\)""")


def spec_acs() -> set[str]:
    return set(AC_IN_SPEC.findall(SPEC.read_text(encoding="utf-8")))


def marked_acs() -> set[str]:
    return {
        ac
        for path in TESTS_DIR.rglob("test_*.py")
        for ac in AC_MARKER.findall(path.read_text(encoding="utf-8"))
    }


def test_spec_lists_the_acceptance_criteria() -> None:
    # Numbers must run 1..N without gaps; letter suffixes (AC-26b, AC-26c) are extras.
    numbers = {int(re.sub(r"\D", "", ac.removeprefix("AC-"))) for ac in spec_acs()}
    assert numbers == set(range(1, max(numbers) + 1))
    assert {"AC-1", "AC-26b"} <= spec_acs()


def test_every_acceptance_criterion_has_a_test() -> None:
    missing = sorted(spec_acs() - marked_acs(), key=lambda ac: (len(ac), ac))
    assert not missing, f"no @pytest.mark.ac test for: {', '.join(missing)}"


def test_markers_only_name_real_criteria() -> None:
    unknown = marked_acs() - spec_acs()
    assert not unknown, f"markers for ACs not in spec.md: {sorted(unknown)}"
