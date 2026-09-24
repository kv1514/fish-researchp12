"""Which pre-registration records an OUTCOME that no results file backs?

``unwatched_claims.py`` inverts ``check_paper_numbers.py`` for the paper: it
finds the figures nobody thought to watch. This does the same one layer down,
for the pre-registrations --- which is where the decision rules live, and where
the paper and RESEARCH_FRONTIER.md both go to quote a settled number.

THE FAILURE THIS WAS WRITTEN FOR. `f8abe6d` recorded two outcomes --- the aimed
code book's replication and the locating book's --- and touched three files: the
two pre-registrations, and `results/v04_duels.jsonl`, which took two duel
records for the same direction. So it was not that the commit wrote no data. It
wrote the PLAY data and not the BELIEF data, and the belief data is what those
two OUTCOME sections are made of. The four figures that licensed the whole
convention direction existed in this repository only as prose in a prereg and a
commit message, and could not be re-derived by anyone, including the author.
They stayed that way for two days, across the two documents that gate the
direction.

That shape is worth naming, because it is what makes the gap survivable: a
commit that touches `results/` at all looks like a commit that recorded its
run.

Both documents named their INSTRUMENT, `scripts4/convention_posterior.py`, and
that was not enough, which is the reason this check is strict about what
counts. The instrument's default output file existed the whole time --- holding
a DIFFERENT run, the exploratory one those very documents exist to supersede.
A named script tells you how a number could be produced. Only a named file
tells you which run produced it, and only if the file is still there.

So the rule here is: **a section that records an outcome must name a results
file that exists.** Nothing weaker distinguishes the case above from a healthy
one.

This is a WORKLIST, not a correctness proof. It cannot tell you the file holds
the numbers the document quotes --- that is `check_paper_numbers.py`'s job, and
it only covers the paper. What it can tell you is when there is nothing to
check against at all, which is the strictly worse case and the one that has
actually happened.

Usage: python scripts4/check_prereg_backing.py [--strict]
``--strict`` exits 1 when any outcome-bearing prereg is unbacked, for CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT / "prereg"

#: A section that reports what a run found, rather than what it will look for.
#: CORRECTION and REPRODUCTION count: both restate a measured number, and a
#: restatement with no file behind it is the same defect as a first statement
#: with none.
OUTCOME = re.compile(
    r"^#{1,3}\s+.*\b(OUTCOME|CORRECTION|REPRODUCTION|RESULT)\b", re.M)

#: Results files as the documents write them. Bare filenames are not accepted:
#: the path is what makes the reference checkable.
RESULTS = re.compile(r"results/[A-Za-z0-9_./-]+\.jsonl?")

#: Outcome-bearing preregs that legitimately have no results file, with the
#: reason. A reason is required: an exemption without one is indistinguishable
#: from the oversight this module exists to find.
EXEMPT: dict[str, str] = {}


def outcome_sections(text: str) -> list[str]:
    return [m.group(0).strip() for m in OUTCOME.finditer(text)]


def audit() -> list[tuple[str, list[str], list[str], list[str]]]:
    """``(name, outcome headings, files named, files named but absent)``."""
    rows = []
    for path in sorted(PREREG.glob("*.md")):
        text = path.read_text()
        heads = outcome_sections(text)
        if not heads:
            continue
        named = sorted(set(RESULTS.findall(text)))
        absent = [f for f in named if not (ROOT / f).exists()]
        rows.append((path.name, heads, named, absent))
    return rows


def main(strict: bool = False) -> int:
    rows = audit()
    unbacked, broken, ok = [], [], []
    for name, heads, named, absent in rows:
        present = [f for f in named if f not in absent]
        if name in EXEMPT:
            ok.append((name, heads, present))
        elif not present:
            unbacked.append((name, heads, named))
        elif absent:
            broken.append((name, present, absent))
        else:
            ok.append((name, heads, present))

    print(f"{len(rows)} pre-registrations record an outcome.\n")

    if unbacked:
        print("UNBACKED -- records an outcome, names no results file that "
              "exists:")
        for name, heads, named in unbacked:
            print(f"  {name}")
            for h in heads:
                print(f"      {h}")
            if named:
                print(f"      names, but none exist: {', '.join(named)}")
        print()

    if broken:
        print("STALE REFERENCE -- names a results file that is not there:")
        for name, present, absent in broken:
            print(f"  {name}: missing {', '.join(absent)}")
        print()

    if not unbacked and not broken:
        print("Every outcome-bearing pre-registration names a results file "
              "that exists.\n")

    print("backed:")
    for name, heads, present in ok:
        why = f"  [exempt: {EXEMPT[name]}]" if name in EXEMPT else ""
        print(f"  {name:34} {', '.join(present)}{why}")

    bad = len(unbacked) + len(broken)
    if bad and strict:
        print(f"\n{bad} unbacked or stale. Exiting 1 (--strict).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--strict" in sys.argv[1:]))
