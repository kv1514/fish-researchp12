"""The cover note quotes the retraction. Check it still quotes it correctly.

WHY THIS TEST EXISTS. `paper/cover_note.tex` is the two pages that go out ahead
of the 124-page report -- it is the part a stranger actually reads, and it is
the part most likely to be sent on its own. It restates the retraction and the
figures behind it, which means it is a SECOND copy of numbers that live in
`results/`, and second copies go stale.

`scripts4/check_paper_numbers.py` guards the report by anchoring each figure to
a phrase near it. That machinery does not transfer here: the cover note is a
different file with different prose and no anchors, and inventing anchors for a
two-page document is more apparatus than the document. So this checks the
handful of figures that carry the retraction, by value, against the same
artifacts -- which is the whole risk. A cover note that says +3.14 after the
price has been re-measured is worse than no cover note, because it is the copy
that travels.

WHAT IT DOES NOT CHECK. Prose, structure, or figures that are stable properties
of the study rather than outputs of a run (the game's rules, the $\\#P$
reduction). Those cannot drift under a re-run, and pinning them would be
ceremony.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.check_paper_numbers import _get, _load   # noqa: E402

NOTE = ROOT / "paper" / "cover_note.tex"

#: (results file, dotted path, format, what it is). The format strings are the
#: cover note's own rounding, which is coarser than the report's on purpose --
#: two pages quote +3.14, not +3.1400.
FIGURES = [
    ("bridge_statefulness_price.json", "cost_to_them", "{:+.2f}",
     "the price of the bridge"),
    ("bridge_statefulness_price.json", "ci95.0", "{:+.2f}",
     "the price's lower bound"),
    ("bridge_statefulness_price.json", "ci95.1", "{:+.2f}",
     "the price's upper bound"),
    ("bridge_statefulness_price.json", "margin_persistent", "{:+.2f}",
     "our corrected margin through the persistent bridge"),
    ("bridge_statefulness_price.json", "their_wrong_declarations_stateless",
     "{:.3f}", "their wrong declarations through the stateless bridge"),
    ("bridge_statefulness_price.json", "their_wrong_declarations_persistent",
     "{:.3f}", "their wrong declarations through the persistent bridge"),
    ("reverse_arbiter_v07.json", "cells.0.meanSetsA-cells.0.meanSetsB",
     "{:+.2f}", "our corrected margin inside their arbiter"),
    ("statefulness_dylan_v04.json", "divergence_rate", "{:.2f}%",
     "the v0.4 divergence rate"),
    ("statefulness_dylan_v05.json", "divergence_rate", "{:.2f}%",
     "the v0.5 divergence rate"),
    ("statefulness_dylan_v07.json", "divergence_rate", "{:.2f}%",
     "the v0.7 divergence rate"),
    ("v07_upstream_parity.json", "decisions_compared", "{:,d}",
     "the decisions replayed for the pin"),
]


def _text() -> str:
    # The same two normalisations `check_paper_numbers` applies, and for the
    # same reason: LaTeX writes "\%" and "6{,}329", and a literal search for
    # the formatted string misses both in a way that reads exactly like drift.
    return (NOTE.read_text(encoding="utf-8")
            .replace("\\%", "%").replace("{,}", ","))


def _present(needle: str, hay: str) -> bool:
    """Is the number in the text as a whole number, not as someone's prefix?

    "+0.62" must not be found inside "+0.6200" or "10.62"; the digit-boundary
    guard is what makes a passing check mean the cover note says this figure
    rather than something that starts the same way.
    """
    return re.search(r"(?<![\d.])" + re.escape(needle) + r"(?![\d.])",
                     hay) is not None


@pytest.mark.parametrize("fname,path,fmt,what", FIGURES,
                         ids=[f[3] for f in FIGURES])
def test_cover_note_figure_matches_artifact(fname, path, fmt, what):
    if not (ROOT / "results" / fname).exists():
        pytest.skip(f"{fname} not present")
    # A dotted path may be a DIFFERENCE of two of them. Their arbiter reports
    # each side's mean sets and no margin field, but the margin is what the
    # cover note quotes, so it is subtracted here rather than hand-copied into
    # the note as a third figure nothing checks.
    doc = _load(fname)
    if "-" in path:
        left, right = path.split("-", 1)
        val = _get(doc, left) - _get(doc, right)
    else:
        val = _get(doc, path)
    if fmt.endswith("%"):
        val = val * 100
        s = fmt[:-1].format(val) + "%"
    else:
        s = fmt.format(val)
    text = _text()
    # A signed figure may be written without its sign where the prose already
    # carries it ("loses to that engine by -0.69" keeps it; "worth 3.14"
    # does not), so the unsigned form is accepted too.
    assert _present(s, text) or _present(s.lstrip("+"), text), (
        f"{what} is {s} in results/{fname}, and the cover note does not say "
        f"it. The cover note is the copy that travels; fix it there.")


def test_cover_note_reports_the_paper_length():
    """The note announces the report's page count, so it must be the real one."""
    log = ROOT / "paper" / "kraken.log"
    if not log.exists():
        pytest.skip("paper not built in this checkout")
    m = re.findall(r"Output written on kraken\.pdf \((\d+) pages", log.read_text(
        encoding="utf-8", errors="replace"))
    if not m:
        pytest.skip("page count not in the build log")
    assert f"{m[-1]} pages" in _text(), (
        f"the report builds at {m[-1]} pages and the cover note says otherwise")


def test_cover_note_counts_the_preregistrations():
    """'Forty-two pre-registrations' has to be however many there are."""
    words = {38: "thirty-eight", 39: "thirty-nine", 40: "forty", 41: "forty-one",
             42: "forty-two", 43: "forty-three", 44: "forty-four"}
    n = len(list((ROOT / "prereg").glob("*")))
    assert n in words, (
        f"{n} pre-registrations; add the word for it to this test")
    assert words[n].capitalize() in _text() or words[n] in _text().lower(), (
        f"there are {n} pre-registrations and the cover note does not say "
        f"'{words[n]}'")


def test_cover_note_does_not_still_assert_the_withdrawn_result():
    """The withdrawn figure may be named, but never as a live claim.

    The failure this guards is a rewrite that trims the retraction paragraph
    for length and leaves the number standing. Mentioning +2.347 is required;
    mentioning it without 'withdrawn' nearby is the defect.
    """
    text = _text()
    for at in [m.start() for m in re.finditer(r"\+?2\.347", text)]:
        near = text[max(0, at - 400):at + 400].lower()
        assert "withdrawn" in near, (
            "the cover note names +2.347 without 'withdrawn' within 400 "
            "characters; that is the retracted figure stated as a live claim")
