"""Is the rollout-target slope one number, or a few positions carrying it?

``scripts4/rollout_target.py`` reports a single within-position slope of
rollout value on P(success). That headline is the quantity the paper's
learning line depends on, so it gets the same treatment every headline in this
project now gets: split it, drop pieces of it, and look at its spread.

Three checks, none of which can be passed by being careful:

1. NESTED SPLIT. The 120-position run contains the earlier 40-position run as
   its first block -- same seeds, same positions, verifiably the same rows. If
   the two disagree by more than noise then "the slope" is not a single number
   and the pooled estimate is a weighted average of different things.

2. LEAVE-ONE-POSITION-OUT. A slope that moves a lot when one position is
   dropped is that position's slope, not the policy's.

3. THE SPREAD ITSELF. The clustered SE barely fell when the run tripled. That
   is a fact about between-position variance and it should be reported as one,
   not hidden inside an interval.

Usage: python scripts4/rollout_target_robust.py [results/rollout_target.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from rollout_target import PAPER_SLOPE, centred_slope   # noqa: E402

SPLIT_AT = 40          # where the earlier, smaller run stopped


def main(argv):
    src = Path(argv[0]) if argv else ROOT / "results" / "rollout_target.json"
    rows = json.loads(src.read_text())["rows"]
    positions = sorted({r["position"] for r in rows})

    print("how much of the rollout-target slope is one number?\n")
    full = centred_slope(rows)
    first = centred_slope([r for r in rows if r["position"] < SPLIT_AT])
    rest = centred_slope([r for r in rows if r["position"] >= SPLIT_AT])

    print(f"{'subset':<26}{'slope':>9}{'se':>9}{'asks':>7}{'pos':>6}")
    for name, s in (("all positions", full),
                    (f"first {SPLIT_AT} (the small run)", first),
                    (f"positions {SPLIT_AT}+", rest)):
        print(f"{name:<26}{s['slope']:>+9.4f}{s['se_clustered']:>9.4f}"
              f"{s['n_points']:>7}{s['n_positions']:>6}")

    gap = rest["slope"] - first["slope"]
    gap_se = float(np.hypot(rest["se_clustered"], first["se_clustered"]))
    print(f"\nsecond block minus first  {gap:+.4f} +/- {gap_se:.4f}  "
          f"({gap / gap_se:+.1f} SE)")

    # 2. leave-one-position-out
    infl = []
    for pid in positions:
        s = centred_slope([r for r in rows if r["position"] != pid])
        if s:
            infl.append((abs(s["slope"] - full["slope"]), pid, s["slope"]))
    infl.sort(reverse=True)
    print("\nmost influential positions:")
    for _, pid, s in infl[:5]:
        print(f"  drop pos {pid:>3}  ->  {s:+.4f}  ({s - full['slope']:+.4f})")
    max_move = infl[0][0] if infl else 0.0

    # 3. the spread of the per-position slopes
    per = []
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    for group in by.values():
        s = centred_slope(group)
        if s and s["se_clustered"] > 0:
            per.append(s["slope"])
    per = np.array(per)
    print(f"\nper-position slopes  k={per.size}  median={np.median(per):+.3f}"
          f"  IQR=[{np.percentile(per, 25):+.3f}, "
          f"{np.percentile(per, 75):+.3f}]  sd={per.std(ddof=1):.3f}")
    print(f"share above zero      {(per > 0).mean():.2f}")
    print(f"share above the paper {(per > PAPER_SLOPE).mean():.2f}")

    print()
    if max_move < 0.5 * full["se_clustered"]:
        print("No single position carries the result: the largest leave-one-out")
        print("move is a fraction of one standard error.")
    else:
        print("One position moves the slope by an appreciable share of its own")
        print("standard error. The headline is partly that position's.")
    if abs(gap) < 2 * gap_se:
        print("The two blocks agree within noise, so the pooled slope is a")
        print("slope and not an average of two different regimes.")
    else:
        print("The two blocks disagree. The pooled number averages two regimes")
        print("and should not be quoted as one.")
    print(f"\nThe spread is real: individual positions run from "
          f"{per.min():+.2f} to {per.max():+.2f}.")
    print("That between-position variance, not the number of asks scored, is")
    print("what sets the interval -- which is why tripling the run barely")
    print("narrowed it.")

    out = {
        "source": str(src),
        "split_at": SPLIT_AT,
        "full": full, "first_block": first, "second_block": rest,
        "block_gap": {"delta": gap, "se": gap_se, "z": gap / gap_se},
        "max_leave_one_out_move": max_move,
        "most_influential": [{"position": p, "slope": s} for _, p, s in infl[:5]],
        "per_position": {
            "k": int(per.size), "median": float(np.median(per)),
            "sd": float(per.std(ddof=1)),
            "min": float(per.min()), "max": float(per.max()),
            "share_positive": float((per > 0).mean()),
            "share_above_paper": float((per > PAPER_SLOPE).mean()),
        },
    }
    dest = ROOT / "results" / "rollout_target_robust.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
