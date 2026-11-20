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

WHY THIS HAS NEVER RUN, which is a different thing from having been skipped.

R6 died at stage 1. The screen in ``results/r6_screen.json`` put all seven
arms BELOW the base at 500 pairs each -- c-1.0 -0.420 [-0.714, -0.126],
c-0.3 -0.240 [-0.509, +0.029], c+0.3 -0.320 [-0.579, -0.061], c+1.0 -0.292
[-0.626, +0.042], c+3.0 -1.124 [-1.473, -0.775], d0.7 -0.196 [-0.477,
+0.085], d0.9 -0.288 [-0.488, -0.088]. Four exclude zero on the losing side
and not one point estimate is positive, so nothing was ever nominated for
stage 2, let alone stage 3. Both knobs sit at their neutral defaults in the
engine (``w_contest=0.0``, ``silence_delta=1.0``), bit-identical, the same
discipline as ``endgame_m=0``.

None of that is an oversight, and the note exists because it LOOKS like one.
Nothing in the repository names this file -- though that alone means little,
since a dozen one-shot scripts under ``scripts4/`` are named by nothing either
and are simply finished. What makes this one worth a paragraph is that it
implements a numbered STAGE of a protocol whose earlier stage did run, so a
reader who finds stage 1's results and no stage 3 has real cause to wonder
whether stage 3 was skipped. It was not.
``prereg/rules_award_baseline.md`` sets out all three R6 stages before any pair
was played, gates stage 2 on the screen CI clearing zero, and commits in
advance to the branch that fired:
"no screening arm clears -> both knobs stay at defaults and the negative is
reported". The knobs stayed at defaults and the negative is reported, in
the paper's contestation table (``tab:contestation``) -- all seven arms,
every interval above, and the dose-response called out.

So stage 3 is unrun because stage 1 said stop, which is the protocol working.
If an R6 arm is ever revived, stage 3 is still required and this still runs it.
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
