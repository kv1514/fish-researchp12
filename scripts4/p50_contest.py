"""P50: the contest term at revision 3, and the untested tally hedge.

Registered in `prereg/p50_contest_rev3.md`, which fixes the arms, the seeds,
the bar and the predicted outcome before any game; this file executes it.

Both arms families are ONE FLAG on KRAKEN_V1 and bit-identical at their
incumbent values, so every difference is the named argument:

    C1  w_contest   0.0 -> +0.3 / +1.0 / -0.3   (fish4/adaptive.py)
    C2  count_mode  "linear" -> "sqrt" / "capped"   (fish4/oppmodel.py)

WHY C1 IS A REOPENING. Commit 03877d9 rejected this term over 4,000 games and
five doses -- against a baseline margin of +2.732 sets, which is BRIDGE_REV 2.
prereg/kraken_v12_vs_sestina.md fixes the rule: a knob rejected against a
handicapped opponent has not been tested against this one.

WHY C2 IS NOT A PATCH FOR AN ATTACK. SESTINA's own header describes the
tally-inflation exploit our linear count_mode is open to, but `selfTally` and
`tallyLie` are ZERO in the shipped spec, so it does not run it. C2 asks only
whether linear over-counting costs anything by itself.

    py scripts4/p50_contest.py [--deals 300] [--jobs 3] [--arms C1a,C2a]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import p46_screen                        # noqa: E402
from scripts4.p46_screen import _one, report           # noqa: E402

SEED0 = 12_900_000
AGENT0 = 129_000
PREREG = "prereg/p50_contest_rev3.md"

#: Registered arms, in registered order. Two families, scored separately.
ARMS = {
    "C1a_contest_p03": {"w_contest": 0.3},
    "C1b_contest_p10": {"w_contest": 1.0},
    "C1c_contest_m03": {"w_contest": -0.3},
    "C2a_count_sqrt": {"count_mode": "sqrt"},
    "C2b_count_capped": {"count_mode": "capped"},
}
FAMILY = {"C1a_contest_p03": "C1", "C1b_contest_p10": "C1",
          "C1c_contest_m03": "C1", "C2a_count_sqrt": "C2",
          "C2b_count_capped": "C2"}

p46_screen.ARMS.update({k: dict(v) for k, v in ARMS.items()})


def _job(job):
    assert p46_screen.ARMS.get(job[2]) == ARMS[job[2]], "arm lost in the fork"
    return _one(job)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    names = [x for x in a.arms.split(",") if x]
    bad = [x for x in names if x not in ARMS]
    if bad:
        print(f"not registered arms: {bad}", file=sys.stderr)
        return 2

    todo = [(SEED0 + i, ke, nm, AGENT0)
            for nm in names for i in range(a.deals) for ke in (True, False)]
    print(f"P50: {len(names)} arms x {a.deals} deals x 2 parities = "
          f"{len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {SEED0:,}", flush=True)
    for nm in names:
        print(f"  {nm:20} {ARMS[nm]}  family {FAMILY[nm]}", flush=True)

    rows, t0 = {}, time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_job, todo, chunksize=1)):
            rows.setdefault(r["arm"], []).append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    for v in rows.values():
        v.sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report(rows, "screen")
    out.update(registration="P50", prereg=PREREG, arm_specs=ARMS,
               families=FAMILY, seed_base=SEED0, agent0=AGENT0,
               deals=a.deals, seconds=round(time.time() - t0, 1),
               per_pair=rows)
    dest = a.out or str(ROOT / "results" / "p50_contest.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
