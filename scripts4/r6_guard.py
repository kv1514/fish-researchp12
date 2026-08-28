"""R6 stage 3: does a knob that beats Dylan also survive an unrelated engine?

The deception ladder shipped rung after rung on sibling duels and had to be
withdrawn wholesale when cross-play showed the rungs were exploiting one
opponent's model rather than playing better. Stage 3 exists so that cannot
happen again through a different door: an arm that wins stage 1 and stage 2
has only ever been measured against ONE foreign engine, and a knob tuned to
Dylan's particular weaknesses is exactly what those two stages cannot tell
from strength.

The guard duels the candidate arm against the v0.3 champion -- an engine
that shares no lineage with Dylan and predates every mechanism under test --
and asks only that the arm not COLLAPSE there. It is deliberately a
one-sided bar: the registered condition is that the interval must not sit
entirely below zero. A knob may reasonably be neutral against an engine it
was never aimed at; what it may not be is a trade that buys Dylan-specific
points by giving away general strength.

    py scripts4/r6_guard.py <arm>          # writes jobs/r6_guard_*.json
    py scripts4/r6_guard.py <arm> --pool   # pools the finished blocks

``arm`` is a key of scripts4.r6_contest_sweep.ARMS, e.g. "c+1.0".
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.r6_contest_sweep import ARMS

V03 = ["tuned", {"w_turn": 0.6, "w_scarce": 0.2}]
RULES = {"wrong_distribution_outcome": "opponent"}
N_BLOCKS = 8
PAIRS = 25
BLOCK = re.compile(r"^R6-guard-\d{2}$")


def write_jobs(arm: str) -> None:
    spec = dict(ARMS[arm])
    for b in range(N_BLOCKS):
        job = [{"label": f"R6-guard-{b:02d}",
                "x": ["fishbot4", spec], "y": V03,
                "n_pairs": PAIRS, "base_seed": 450_000 + 1000 * b,
                "agent_seed": 6700 + b, "rules": RULES}]
        (ROOT / "jobs" / f"r6_guard_{b:02d}.json").write_text(
            json.dumps(job, indent=1))
    print(f"wrote {N_BLOCKS} guard job files for arm {arm!r}")
    print("run:  for f in jobs/r6_guard_*.json; do "
          "python scripts4/duel.py $f 3; done")


def pool(arm: str) -> int:
    cells = {}
    for line in (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if BLOCK.match(r.get("label") or ""):
            cells[r["label"]] = r
    if not cells:
        print("no guard blocks found")
        return 1
    digs = {(c.get("engine") or {}).get("digest") for c in cells.values()}
    rules = {json.dumps(c.get("rules"), sort_keys=True) for c in cells.values()}
    if len(digs) != 1 or len(rules) != 1:
        print(f"REFUSING to pool: {len(digs)} engines, {len(rules)} rule sets")
        return 1
    diffs = []
    for c in cells.values():
        diffs.extend(c["diffs"])
    n = len(diffs)
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = m - 1.96 * se, m + 1.96 * se
    verdict = "COLLAPSES" if hi < 0 else "passes"
    print(f"{len(cells)} blocks, {n} pairs, arm {arm!r} vs the v0.3 champion:")
    print(f"  {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  -> {verdict}")
    if hi < 0:
        print("  The interval sits entirely below zero: the arm buys its "
              "Dylan-specific points by giving up general strength. Per the "
              "pre-registration it does NOT ship.")
    else:
        print("  Not a collapse. With stages 1 and 2 also passed, the arm "
              "may ship.")
    (ROOT / "results" / "r6_guard.json").write_text(json.dumps({
        "arm": arm, "n_pairs": n, "n_blocks": len(cells), "estimate": m,
        "ci": [lo, hi], "se": se, "rules": json.loads(next(iter(rules))),
        "engine": next(iter(digs)), "verdict": verdict}, indent=1))
    print("wrote results/r6_guard.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ARMS or a[0] == "base":
        raise SystemExit(
            f"usage: r6_guard.py <arm> [--pool]; arms: "
            f"{[k for k in ARMS if k != 'base']}")
    if len(a) > 1 and a[1] == "--pool":
        raise SystemExit(pool(a[0]))
    write_jobs(a[0])
