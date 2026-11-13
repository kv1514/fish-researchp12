"""Every queued experiment is either waited for or explicitly excluded.

``widen_rollout.sh`` restarts the rollout pass on more workers once the duel
queue stops competing for cores. It decided that from a hand-written list of
five job files, and the list had already gone stale: ``j30_retake_bonus.json``
was queued afterwards, so widening would have fired while 2000 pre-registered
pairs were still to play.

Deriving the list automatically is not the fix either -- two job files hold
labels from abandoned screens that will never be recorded, and one is gated on
the very rollout pass that widening exists to accelerate, so waiting on it is a
livelock. The list stays explicit; what these tests add is that an undeclared
job file fails loudly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from queue_state import EXCLUDED, WAIT_FOR, pending_by_file    # noqa: E402


def test_no_job_file_is_undeclared():
    r = subprocess.run([sys.executable, "scripts4/queue_state.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_pending_job_file_is_declared():
    """The same property, asserted directly rather than through exit status."""
    undeclared = [n for n in pending_by_file()
                  if n not in WAIT_FOR and n not in EXCLUDED]
    assert not undeclared, (
        f"job files with pending blocks in neither WAIT_FOR nor EXCLUDED: "
        f"{undeclared}")


def test_the_two_lists_do_not_overlap():
    """A file in both is a contradiction, and WAIT_FOR would silently win."""
    both = sorted(set(WAIT_FOR) & set(EXCLUDED))
    assert not both, f"job files both waited for and excluded: {both}"


def test_waited_files_exist():
    """Waiting on a file that is not there passes vacuously."""
    gone = [n for n in WAIT_FOR if not (ROOT / "jobs" / n).exists()]
    assert not gone, f"WAIT_FOR names job files that do not exist: {gone}"


def test_every_exclusion_gives_a_reason():
    thin = [n for n, why in EXCLUDED.items() if len(why.strip()) < 20]
    assert not thin, f"exclusions without a real reason: {thin}"


def test_the_widen_script_delegates_rather_than_duplicating_the_list():
    """The regression: a second copy of the list that drifts from the first."""
    s = (ROOT / "scripts4" / "widen_rollout.sh").read_text(encoding="utf-8")
    assert "queue_state.py" in s, \
        "widen_rollout.sh must ask queue_state.py, not carry its own list"
    for name in ("j24_at_ask_confirm.json", "j25_stack.json",
                 "j27_precision2.json"):
        assert name not in s, (
            f"widen_rollout.sh names {name} directly again -- that hard-coded "
            f"list is what went stale")


def test_pending_labels_are_real_labels():
    """A typo in a job file's label would make its block unwaitable forever."""
    for name, labels in pending_by_file().items():
        for lab in labels:
            assert lab and lab != "<unreadable>", \
                f"{name} has a job with no usable label"
