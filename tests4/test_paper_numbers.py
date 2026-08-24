"""The paper's most drift-prone figures must match the results files.

Not a style check. Several of these figures are derived from
``results/v04_duels.jsonl``, which grows every time a block lands, so a number
written into the paper on Tuesday is quietly wrong on Wednesday and reads
exactly the same. That happened three times in one session: a cell count went
28 -> 31 -> 34 -> 35, a conditional standard deviation 3.88 -> 3.91, and a
correlation +0.858 -> +0.862 -> +0.865, each while the prose around it stayed
put.

The gate is deliberately crude -- format the current value the way the paper
formats it and require that string to appear. It cannot silently pass, and a
failure is a prompt to refresh the figure or to say in the text when it was
taken, not necessarily a bug.

WHAT IT DOES NOT COVER, stated so nobody trusts it further than it goes: this
compares the paper against the RESULTS FILES, not against the raw data those
files were derived from. A results file that is itself stale -- generated before
the last blocks landed -- passes happily. Catching that would mean regenerating
every analysis on every test run, which is hours of compute, so the check stops
where it stops.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from check_paper_numbers import (PAPER, WATCH,                  # noqa: E402
                                 _present)


def test_every_watched_figure_matches_the_results_file():
    r = subprocess.run([sys.executable, "scripts4/check_paper_numbers.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_manifest_points_at_files_that_exist():
    """A watch on a missing file is a check that never fires."""
    missing = sorted({row[0] for row in WATCH
                      if not (ROOT / "results" / row[0]).exists()})
    assert not missing, f"watched results files absent: {missing}"


def test_every_watched_figure_has_an_anchor_that_is_in_the_paper():
    """An anchor that has drifted out of the text makes its row unfired.

    Checking a formatted number appears somewhere in a 3700-line paper is close
    to useless -- "0.340" occurs for unrelated reasons -- so each row names a
    phrase the number must sit near. That only works while the phrase exists,
    and one of them did not on the first run: the abstract had been rewritten
    around it.
    """
    text = PAPER.read_text(encoding="utf-8")
    gone = [row[3] for row in WATCH if len(row) > 4 and row[4] not in text]
    assert not gone, f"anchors no longer in the paper: {gone}"


def test_the_paper_is_where_the_manifest_says():
    assert PAPER.exists()


def test_the_match_can_actually_fail():
    """A check that cannot report a miss is not a check.

    The rule was a bare ``value in window``. Over a 1400-character window that
    passes on any digit string that happens to occur inside a longer number, so
    the two continuation-length rows -- which share an anchor -- each passed on
    the OTHER's value, and swapping the two figures in the paper reported
    clean. This pins the boundary rule that fixed it.
    """
    near = r"the heuristic needs $181$ plies where the engine needs $26$"
    assert _present("181", near)
    assert _present("26", near)
    for fragment in ("18", "8", "1", "2", "6"):
        assert not _present(fragment, near), \
            f"{fragment!r} matched as a substring of a longer number"
    # A decimal must not match a truncation of itself, in either direction.
    assert _present("0.340", "the pooled estimate is $0.340$")
    assert not _present("0.34", "the pooled estimate is $0.340$")
    assert not _present("0.3401", "the pooled estimate is $0.340$")


def test_short_integer_formats_are_not_free_passes():
    """The row the module docstring names as its motivating example.

    ``n_cells`` was written 28, then 31, then 34 while runs kept landing. Under
    the old rule "35" still passed against a window containing 28 or 32, so the
    check would have reported clean on precisely the drift it was written for.
    """
    stale = r"across the $28$ cells of this study that store per-pair values"
    assert not _present("35", stale)
    assert _present("28", stale)
