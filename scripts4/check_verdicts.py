"""Is any finished pre-registered run still sitting without a verdict?

The stacking run had all six of its blocks recorded for days before anyone ran
``stack_verdict.py`` against them. Nothing was wrong with the data and nothing
was wrong with the script; the two had simply never been introduced. A finished
experiment with no verdict looks exactly like a running one from the outside,
which is why this is a check and not a habit.

It also catches the opposite: a verdict file OLDER than the results file it
summarises, which is a stale conclusion rather than a missing one, and reads
just as convincingly.

Usage: python scripts4/check_verdicts.py
Exit status is 1 if any run is finished-but-unanalysed or stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"

#: (label prefix, expected blocks, verdict file, the script that writes it).
#: Sourced from the POOLS list in check_seeds.py, which is what the analyses
#: actually pool -- keeping a second hand-written list would just be one more
#: thing to drift.
RUNS = [
    ("SETTLE lookahead d3 w0.25 block", 6,
     "settle_verdict.json", "scripts4/settle_verdict.py"),
    ("PRECISION n_draws 480 vs 160 block", 6,
     "precision_verdict.json", "scripts4/precision_verdict.py 1"),
    ("AT_ASK g1.0 vs champion block", 6,
     "at_ask_verdict.json", "scripts4/at_ask_verdict.py"),
    ("STACK lookahead on top of n_draws 480 block", 6,
     "stack_verdict.json", "scripts4/stack_verdict.py"),
    ("RETAKE GATE w0.30 depth>=2 vs champion block", 2,
     "retake_verdict.json", "scripts4/retake_verdict.py"),
    ("PRECISION2 n_draws 1440 vs 480 block", 6,
     "precision2_verdict.json", "scripts4/precision_verdict.py 2"),
    ("CLAIM THRESHOLD 0.90 vs 0.97 block", 2,
     "claim_threshold_verdict.json", "scripts4/claim_verdict.py"),
    ("LEARNED WEIGHTS v2 vs champion block", 2,
     "learned_weights_verdict.json", "(no verdict script yet)"),
    ("RETAKE BONUS w-0.30 vs champion block", 2,
     "retake_bonus_verdict.json", "scripts4/retake_bonus_verdict.py"),
    ("COMBINED 480+lookahead vs champion block", 2,
     "combined_verdict.json", "scripts4/combined_verdict.py"),
]

#: Pools that are NOT runs in their own right, because another run's verdict
#: analyses them as a secondary pool. Named explicitly rather than left to fall
#: through the coverage test, so that "this pool has no verdict" stays a failure
#: for every pool that is not on this list.
SUBSUMED = {
    "lookahead, four unselected cells":
        ("settle_verdict.json", "secondary",
         "the four unselected cells are settle_verdict.py's secondary pool, "
         "reported beside the pre-registered six and explicitly not decisive"),
}


def main() -> int:
    if not DUELS.exists():
        print(f"{DUELS} is missing")
        return 1
    labels = [json.loads(l).get("label", "") for l in
              DUELS.read_text(encoding="utf-8").splitlines() if l.strip()]
    duels_mtime = DUELS.stat().st_mtime

    print("is any finished pre-registered run still without a verdict?\n")
    print(f"{'run':<44}{'blocks':>8}   verdict")
    stale, unanalysed = [], []
    for prefix, want, vfile, how in RUNS:
        have = sum(1 for k in labels if k.startswith(prefix))
        v = ROOT / "results" / vfile
        name = prefix.replace(" block", "")[:42]
        if have < want:
            print(f"{name:<44}{have:>3}/{want:<4}   still running")
            continue
        if not v.exists():
            print(f"{name:<44}{have:>3}/{want:<4}   *** FINISHED, NO VERDICT")
            unanalysed.append((name, how))
            continue
        # A verdict written before the last block landed summarises a run that
        # had not finished. Compare against the block's own timestamp rather
        # than the file's, since the file grows for other runs too.
        last = max((json.loads(l).get("timestamp", 0)
                    for l in DUELS.read_text(encoding="utf-8").splitlines()
                    if l.strip() and json.loads(l).get("label", "").startswith(prefix)),
                   default=0)
        if v.stat().st_mtime < last:
            print(f"{name:<44}{have:>3}/{want:<4}   *** STALE (predates its "
                  f"last block)")
            stale.append((name, how))
            continue
        print(f"{name:<44}{have:>3}/{want:<4}   ok")

    print()
    if not unanalysed and not stale:
        print("Every finished run has a verdict, and no verdict predates the "
              "run it\nsummarises.")
        return 0
    for name, how in unanalysed:
        print(f"FINISHED BUT UNANALYSED: {name}\n  run: {how}")
    for name, how in stale:
        print(f"STALE VERDICT: {name}\n  re-run: {how}")
    print("\nA finished experiment with no verdict looks exactly like a running "
          "one from\nthe outside, and a stale verdict reads exactly like a "
          "fresh one. Both are\nwhy this check exists.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
