"""Do two different experiments share deals they should not?

Duplicate-deal cells are indexed by ``base_seed`` and a cell consumes
``2 * n_pairs`` consecutive seeds. Two cells whose ranges intersect play some of
the same deals, and that means two very different things:

WITHIN one job file it is the design. A gamma sweep runs every value on
identical deals so the cells are comparable to each other -- common random
numbers one level up, used deliberately here since the first opponent-model
sweep.

ACROSS two job files it is a mistake, and a quiet one. Every pre-registration in
this project says "fresh seeds throughout". Two runs that share deals are
correlated, so they are not the independent evidence they are presented as, and
reading one as a check on the other overstates what they jointly say.

This script reports the second kind. It splits them into collisions among work
already RUN -- history, unfixable, worth knowing -- and collisions involving
work still QUEUED, which are bugs that can still be fixed before they cost
anything.

It exists because exactly that happened: the retake-gate cells were checked
against every recorded result and passed, having never been compared against the
other jobs waiting in the same queue, and they shared a thousand deals with the
stacking run's last block.

Usage: python scripts4/check_seeds.py
Exit status is 1 if any QUEUED cell collides across experiments.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The cell sets that any analysis here AVERAGES. Correlation between two cells
#: that are pooled shrinks the pooled standard error below its true value, so
#: these are the sets where a shared deal is a wrong interval and not a note.
#: Kept in step with scripts4/settle_verdict.py and scripts4/precision_verdict.py.
POOLS = {
    "lookahead, six settling blocks":
        [f"SETTLE lookahead d3 w0.25 block {i}" for i in range(6)],
    "lookahead, four unselected cells": [
        "REPLICATE lookahead d3 w0.25 vs champion (fresh seeds)",
        "REPLICATE lookahead d3 w0.25 vs champion (second fresh set)",
        "DECISIVE lookahead d3 w0.25 vs champion (A)",
        "DECISIVE lookahead d3 w0.25 vs champion (B)"],
    "precision, six blocks":
        [f"PRECISION n_draws 480 vs 160 block {i}" for i in range(6)],
    "at-ask, six blocks":
        [f"AT_ASK g1.0 vs champion block {i}" for i in range(6)],
    "stack, six blocks":
        [f"STACK lookahead on top of n_draws 480 block {i}" for i in range(6)],
    "retake gate, two blocks":
        [f"RETAKE GATE w0.30 depth>=2 vs champion block {i}" for i in range(2)],
    "precision rung 2, six blocks":
        [f"PRECISION2 n_draws 1440 vs 480 block {i}" for i in range(6)],
}


def load():
    """``(source, label, lo, hi, queued)`` for every cell that names a seed."""
    by_label = {}
    files = {}
    for j in sorted((ROOT / "jobs").glob("*.json")):
        if "resume" in j.name:
            continue                  # a resume file is a subset of its parent
        try:
            cells = json.loads(j.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(cells, list):
            continue
        files[j.name] = cells
        for k in cells:
            if isinstance(k, dict) and k.get("label"):
                by_label[k["label"]] = j.name

    done = set()
    out = []
    src = ROOT / "results" / "v04_duels.jsonl"
    if src.exists():
        for line in src.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("base_seed") is None:
                continue
            done.add(r["label"])
            n = 2 * int(r.get("n_pairs") or 0)
            out.append((by_label.get(r["label"], "legacy"), r["label"],
                        int(r["base_seed"]), int(r["base_seed"]) + n, False))
    for name, cells in files.items():
        for k in cells:
            if not isinstance(k, dict) or k.get("base_seed") is None:
                continue
            if k["label"] in done:
                continue              # already counted from the results file
            n = 2 * int(k.get("n_pairs") or 0)
            out.append((name, k["label"], int(k["base_seed"]),
                        int(k["base_seed"]) + n, True))
    return sorted(out, key=lambda t: (t[2], t[3]))


def main() -> int:
    cells = load()
    within = 0
    hist, live = [], []
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            if b[2] >= a[3]:
                break                 # sorted by start: nothing further overlaps
            if a[1] == b[1]:
                continue
            if a[0] == b[0] and a[0] != "legacy":
                within += 1           # same job file: shared deals by design
                continue
            (live if (a[4] or b[4]) else hist).append((a, b))

    print(f"cells with a seed range: {len(cells)}  "
          f"({sum(1 for c in cells if c[4])} still queued)")
    print(f"shared deals within one job file (by design):  {within}")
    print(f"shared deals across experiments, already run:  {len(hist)}")
    print(f"shared deals across experiments, still queued: {len(live)}")

    if hist:
        fam = sorted({(a[0], b[0]) for a, b in hist})
        print("\nhistorical, unfixable, listed by the pair of sources:")
        for x, y in fam:
            print(f"  {x} <-> {y}")

    # The claim that matters is not "the collisions are old", it is "no two
    # cells that get AVERAGED TOGETHER share deals". A pooled estimate of
    # correlated cells has a standard error that is too small, and that is a
    # wrong interval rather than a note. So check the pools rather than say it.
    print("\npublished pools, checked for internal overlap:")
    bad = 0
    for name, labels in POOLS.items():
        members = [c for c in cells if c[1] in labels]
        clashes = [(a, b) for i, a in enumerate(members) for b in members[i + 1:]
                   if a[2] < b[3] and b[2] < a[3]]
        mark = "OK" if not clashes else f"{len(clashes)} OVERLAPPING PAIRS"
        print(f"  {name:<34} {len(members):>2}/{len(labels)} cells   {mark}")
        for a, b in clashes:
            print(f"      {a[1][:44]} [{a[2]},{a[3]})")
            print(f"      {b[1][:44]} [{b[2]},{b[3]})")
        bad += len(clashes)
    if not bad:
        print("  No pooled estimate averages two cells that share a deal, so "
              "every\n  interval published from these pools is the interval "
              "it claims to be.")

    if live:
        print("\nQUEUED COLLISIONS -- fixable now:")
        for a, b in live:
            print(f"  {a[0]:<24} {a[1][:40]:<40} [{a[2]},{a[3]})")
            print(f"  {b[0]:<24} {b[1][:40]:<40} [{b[2]},{b[3]})\n")
        return 1
    print("\nNo queued cell shares deals with another experiment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
