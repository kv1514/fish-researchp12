"""The refuted impossibility claim must not come back.

``fish4/NEGATIVE_CLAIMS.md`` records that the belief tracker CAN attach to a
determinized mid-game position, against a docstring that said it could not. The
false sentence lived in two modules and the paper for a whole version, and the
objective-learning line was closed on it.

A docstring is not covered by any other test, so a future edit could reintroduce
it silently -- and this particular sentence is the kind that gets reintroduced,
because it reads like an explanation of why the code is shaped the way it is.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "fish4" / "NEGATIVE_CLAIMS.md"

#: Wordings of the refuted claim. Matching is loose on whitespace because these
#: sentences are wrapped differently in each file they appear in.
REFUTED = [
    r"posterior cannot be reconstructed",
    r"refuses to\s+attach to a mid-game position",
    r"strong v0\.4 policy cannot be used as a continuation",
]

SOURCES = sorted(
    p for p in (ROOT / "fish4").rglob("*.py")
    if "__pycache__" not in str(p)
)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


@pytest.mark.parametrize("pattern", REFUTED)
def test_the_refuted_claim_is_not_asserted_anywhere(pattern):
    rx = re.compile(_flat(pattern), re.I)
    offenders = []
    for p in SOURCES:
        flat = _flat(p.read_text(encoding="utf-8"))
        for m in rx.finditer(flat):
            # The correction paragraphs quote the false sentence in order to
            # retract it, and the retraction can sit on EITHER side of the
            # quotation -- "the claim that once stood here ... is false" puts it
            # after. Looking only backwards flagged a correct retraction, which
            # is how this window came to be two-sided.
            window = flat[max(0, m.start() - 400):m.end() + 200]
            if re.search(r"\bis false\b|\bwas false\b|used to|was wrong|"
                         r"it was said|once stood|correction", window, re.I):
                continue
            offenders.append(f"{p.relative_to(ROOT)}: ...{flat[m.start():m.end() + 80]}")
    assert not offenders, (
        "the refuted impossibility claim is asserted again:\n  "
        + "\n  ".join(offenders)
        + "\nSee fish4/NEGATIVE_CLAIMS.md.")


def test_the_register_exists_and_names_its_rule():
    assert REGISTER.exists()
    text = REGISTER.read_text(encoding="utf-8")
    for needed in ("Refuted", "a proof from the rules", "untested"):
        assert needed in text, f"the register lost its {needed!r} section"


def test_the_register_lists_every_status_it_claims_to():
    """A register that silently drops a row is worse than none."""
    text = REGISTER.read_text(encoding="utf-8")
    for claim in ("initial_hand", "_build_tilt", "claim4.py", "perpetual.py",
                  "learn/fit.py", "exact2_study.py"):
        assert claim in text, f"{claim} fell out of the register"
