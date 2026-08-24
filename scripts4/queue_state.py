"""What the duel queue is still waiting on, and what it has deliberately left.

``widen_rollout.sh`` restarts the rollout pass on more workers once the duel
queue stops competing for cores, and it decided that by a HAND-MAINTAINED list
of five job files. A sixth (``j30_retake_bonus.json``) was queued after that
list was written, so widening would have fired while 2000 pre-registered pairs
were still to play and oversubscribed the box.

Deriving the list from ``jobs/*.json`` instead is not free either, and the two
traps are worth naming:

  - ``j8`` and ``j9`` hold labels from screens that were abandoned and will
    never be recorded, so "wait for every pending label" waits forever;
  - ``j29`` is gated on the rollout pass FINISHING, and widening exists to make
    that pass finish sooner. Waiting on j29 would be a livelock: widen waits for
    j29, j29 waits for the rollout, and the rollout stays on one worker.

So the list stays explicit, and every exclusion has to say why. What this module
adds is that an UNDECLARED job file is an error rather than a silent omission --
which is the failure that started it.

Usage: python scripts4/queue_state.py [--wait-labels]
Exit status is 1 if some job file with pending labels is neither waited on nor
explicitly excluded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Job files whose completion the rollout widening waits for.
WAIT_FOR = (
    "j24_at_ask_confirm.json",
    "j25_stack.json",
    "j26_retake_gate.json",
    "j27_precision2.json",
    "j28_claim_threshold.json",
    "j30_retake_bonus.json",
)

#: Job files deliberately NOT waited on, and why. An exclusion without a reason
#: is the same thing as an omission.
EXCLUDED = {
    "j8_value_objective.json":
        "abandoned screen; its labels were never recorded and never will be",
    "j9_signals.json":
        "abandoned screen; same",
    "j29_learned_weights.json":
        "gated on the rollout pass finishing, which is what widening exists to "
        "accelerate -- waiting on it would livelock",
}


def _done() -> set:
    f = ROOT / "results" / "v04_duels.jsonl"
    if not f.exists():
        return set()
    return {json.loads(l).get("label")
            for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}


def pending_by_file() -> dict:
    """{job file: [labels not yet recorded]} over every non-resume job file."""
    done = _done()
    out = {}
    for p in sorted((ROOT / "jobs").glob("j*.json")):
        if "resume" in p.name:
            continue                  # a resume file is a subset of its parent
        try:
            jobs = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out[p.name] = ["<unreadable>"]
            continue
        if isinstance(jobs, dict):
            jobs = [jobs]
        miss = [j.get("label") for j in jobs if j.get("label") not in done]
        if miss:
            out[p.name] = miss
    return out


def waited_labels() -> list:
    """Every label the widening is still waiting for, in queue order."""
    done = _done()
    out = []
    for name in WAIT_FOR:
        p = ROOT / "jobs" / name
        if not p.exists():
            continue
        jobs = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(jobs, dict):
            jobs = [jobs]
        out += [j["label"] for j in jobs if j.get("label") not in done]
    return out


def main(argv) -> int:
    pend = pending_by_file()
    if "--wait-labels" in argv:
        # Machine-readable: one pending label per line, for the shell.
        for lab in waited_labels():
            print(lab)
        return 0

    print("what is the duel queue still waiting on?\n")
    undeclared = []
    for name, labels in sorted(pend.items()):
        if name in WAIT_FOR:
            tag = "waited on"
        elif name in EXCLUDED:
            tag = f"excluded: {EXCLUDED[name]}"
        else:
            tag = "*** UNDECLARED"
            undeclared.append(name)
        print(f"  {name:<32} {len(labels):>2} pending   {tag}")
    if not pend:
        print("  (every job file's labels are recorded)")

    n = len(waited_labels())
    print(f"\nwidening waits on {n} more block(s)")
    if undeclared:
        print(f"\n{len(undeclared)} job file(s) have pending blocks and appear "
              f"in neither WAIT_FOR nor\nEXCLUDED: {undeclared}\n"
              f"Add them to one or the other. A queued experiment nobody waits "
              f"for gets its\ncores stolen; an abandoned one nobody excludes "
              f"blocks the wait forever.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
