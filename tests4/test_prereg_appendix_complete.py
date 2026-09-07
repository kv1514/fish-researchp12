"""Every registration in `prereg/` has a row in the appendix that claims to list them all.

WHY THIS EXISTS. Appendix~A says, in the paper's own words, that the
registrations returning ``nulls, refutations, withdrawals and non-results are
listed on exactly the same footing as the ones that returned effects, in the
same table''. It is the appendix whose stated purpose is to expose file-drawer
risk. So an incomplete table is not a formatting slip; it is the failure the
appendix was built to prevent, committed by the appendix.

It had already happened. The table was compiled with thirty-eight rows and four
registrations were written afterwards -- `signal_dose_law`,
`signal_dose_linearity`, `signal_generality`, `signal_matched_dose` -- all four
run, all four reported in the body of the paper, none of them in the table, and
the surrounding prose still saying ``thirty-eight'' while `prereg/` held
forty-two. Nothing failed, because nothing was checking.

WHAT IS CHECKED, AND WHY EACH PART. The set of `.md` files under `prereg/`
must equal the set of registrations the table names, exactly and in both
directions: a missing row hides a result, and a row naming a document that no
longer exists cites a threshold nobody can read. The written-out counts in the
prose are checked against the same number, because they are the sentences a
reader trusts instead of counting.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "prereg"
APPENDIX = ROOT / "paper" / "appendix_prereg.tex"
PAPER = ROOT / "paper" / "kraken.tex"

#: How the table opens a row: ``P17 & \path{some_registration.md} \newline``.
ROW = re.compile(r"^P(\d+) & \\path\{([a-z0-9_]+\.md)\}", re.MULTILINE)

#: The counts are written out rather than in digits, so they are matched as
#: words. Only the ones the appendix and the paper actually use.
NUMBER_WORDS = {
    38: "thirty-eight", 39: "thirty-nine", 40: "forty", 41: "forty-one",
    42: "forty-two", 43: "forty-three", 44: "forty-four", 45: "forty-five",
    46: "forty-six", 47: "forty-seven", 48: "forty-eight", 49: "forty-nine",
    50: "fifty",
}


def _rows() -> dict[int, str]:
    return {int(n): f for n, f in ROW.findall(APPENDIX.read_text())}


def test_every_registration_on_disk_has_a_row():
    on_disk = {p.name for p in PREREG.glob("*.md")}
    tabled = set(_rows().values())
    missing = sorted(on_disk - tabled)
    assert not missing, (
        "registrations with no row in the appendix that claims to list every "
        f"one of them: {missing}. Add a row per registration -- appending it "
        "after the last P-number, since the existing identifiers are cited "
        "throughout the prose and renumbering would move their referents.")


def test_no_row_cites_a_registration_that_is_not_there():
    on_disk = {p.name for p in PREREG.glob("*.md")}
    tabled = set(_rows().values())
    phantom = sorted(tabled - on_disk)
    assert not phantom, (
        f"the appendix quotes thresholds from documents that do not exist: "
        f"{phantom}")


def test_the_numbers_are_unique_and_contiguous():
    """A duplicate or a gap makes every P-reference in the prose ambiguous."""
    nums = sorted(_rows())
    assert len(nums) == len(set(nums)), "duplicate P-numbers in the table"
    assert nums == list(range(1, len(nums) + 1)), (
        f"P-numbers are not 1..{len(nums)}: {nums}")


def _counts(text: str, word: str) -> list[str]:
    """Every place ``word`` is used as a count OF REGISTRATIONS.

    Scoped rather than global on purpose. Both files use number words for
    ordinary quantities -- ``The other forty games``, ``sampled twenty to forty
    deep`` -- so a bare search for the word finds prose that has nothing to do
    with this table. The two shapes below are the ones the count is actually
    written in, and the boundary excludes the hyphen that ``\\b`` treats as a
    word break, so ``forty`` is not found inside ``forty-two``.
    """
    w = re.escape(word)
    shapes = [
        rf"(?<![\w-]){w}(?![\w-])\s+(?:documents|registrations|"
        rf"pre-registrations)",
        rf"(?:of|How)\s+the\s+(?<![\w-]){w}(?![\w-])",
    ]
    out = []
    for pat in shapes:
        out += [m.group(0) for m in re.finditer(pat, text, re.S)]
    return out


def test_the_written_out_counts_match_the_table():
    n = len(_rows())
    word = NUMBER_WORDS.get(n)
    assert word, f"no spelled-out form recorded for {n}; extend NUMBER_WORDS"
    stale = {w for k, w in NUMBER_WORDS.items() if k != n}
    for path in (APPENDIX, PAPER):
        text = path.read_text()
        assert _counts(text, word), (
            f"{path.name} never counts the registrations as '{word}', but the "
            f"table has {n} rows")
        for bad in sorted(stale):
            found = _counts(text, bad)
            assert not found, (
                f"{path.name} still counts the registrations as '{bad}' where "
                f"the table has {n} rows: {found}")
