"""A run in flight must not make the repository look dirty, or lose its place.

Every paired runner journals each played row so a killed container resumes
from disk. That works and has one cost nobody designed for: the journal is a
tracked file that changes on every flush, so a repository with a run in flight
is never clean and "commit your changes" becomes a prompt to commit a
half-finished measurement.

The fix is a `.partial` name that is ignored while the run goes and promoted
when it completes. Three properties have to hold, and the third is the one
that would quietly destroy data if it did not.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts4.journal import finish, in_flight, to_read


def test_a_run_in_flight_resumes_from_its_partial():
    d = Path(tempfile.mkdtemp())
    dest = d / "j.jsonl"
    in_flight(dest).write_text("a\nb\n")
    assert to_read(dest) == in_flight(dest)


def test_a_completed_run_promotes_and_leaves_no_partial():
    d = Path(tempfile.mkdtemp())
    dest = d / "j.jsonl"
    in_flight(dest).write_text("a\nb\n")
    finish(dest)
    assert dest.read_text() == "a\nb\n"
    assert not in_flight(dest).exists()
    assert to_read(dest) == dest


def test_a_second_block_appends_and_never_clobbers_the_first():
    """Two runs of one experiment on disjoint seed blocks are a thing to want.

    A rename would silently discard the older journal, which is the failure
    this project already had once when a sibling process overwrote G1's.
    """
    d = Path(tempfile.mkdtemp())
    dest = d / "j.jsonl"
    in_flight(dest).write_text("a\nb\n")
    finish(dest)
    in_flight(dest).write_text("c\n")
    finish(dest)
    assert dest.read_text() == "a\nb\nc\n"
    assert not in_flight(dest).exists()


def test_finishing_nothing_is_not_an_error():
    d = Path(tempfile.mkdtemp())
    finish(d / "never-existed.jsonl")


def test_the_partial_name_is_the_one_gitignore_covers():
    """The pattern in .gitignore is `*.jsonl.partial`; if the helper ever
    stopped producing that name the tree would silently go dirty again."""
    assert str(in_flight(Path("results/x_journal.jsonl"))).endswith(
        ".jsonl.partial")
    ignore = Path(ROOT, ".gitignore").read_text()
    assert "*.jsonl.partial" in ignore
