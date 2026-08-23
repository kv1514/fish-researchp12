"""The pre-registered verdict on the belief-space lookahead.

This script does what ``jobs/PREREGISTRATION_lookahead.md`` says and nothing
else. It was written before the blocks finished, which is the only way a fixed
analysis stays fixed: an analysis chosen after the numbers arrive is a choice
about the numbers.

  PRIMARY, and the only thing that decides. A fixed-effect pool of the six new
  blocks. Every block is unselected, so none may be dropped for its result.
  The effect is demonstrated if and only if the 95% interval excludes zero.

  SECONDARY, reported either way. The six new blocks pooled with the four
  existing unselected cells. Reported for the estimate, not for the verdict.

  HOMOGENEITY. Cochran's Q across the six new blocks, diagnostic only. The A/A
  study measured tau = 0 with coverage 23/24, so a significant Q here would be
  evidence of a deal-population-dependent effect rather than grounds to switch
  to random-effects pooling.

The 200-pair screening cell that resolved at +0.570 is excluded from the
secondary pool wherever it appears, because it was selected for having resolved.
That exclusion was decided before the retests, not now.

Refuses to print a verdict on fewer than six blocks. A partial pool of an
append-only run is an interim look, and taking an interim look at a
pre-registered test and then deciding whether to keep going is how a fixed
analysis stops being one.

    py scripts4/settle_verdict.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from pool_cells import Z, cells, pool                            # noqa: E402

SETTLE = [f"SETTLE lookahead d3 w0.25 block {i}" for i in range(6)]

#: The four cells that were run without being selected for their result. The
#: 200-pair screen is not among them: it was chosen for resolving, and pooling a
#: cell chosen for its size with cells that were not is the winner's curse with
#: extra steps.
UNSELECTED = [
    "REPLICATE lookahead d3 w0.25 vs champion (fresh seeds)",
    "REPLICATE lookahead d3 w0.25 vs champion (second fresh set)",
    "DECISIVE lookahead d3 w0.25 vs champion (A)",
    "DECISIVE lookahead d3 w0.25 vs champion (B)",
]

#: Written into the pre-registration before the run, and repeated here so the
#: report can be read without the other document open.
ASSUMED_EFFECT = 0.153
PER_PAIR_SD = 3.796


def _line(c):
    return (f"  {c['label'][-8:]:<9} n={c['n']:>5}  {c['est']:>+7.3f} "
            f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")


def _verdict(est, se, name):
    lo, hi = est - Z * se, est + Z * se
    out = "EXCLUDES ZERO" if (lo > 0 or hi < 0) else "INCLUDES ZERO"
    print(f"\n{name}")
    print(f"  {est:+.4f}  95% [{lo:+.4f}, {hi:+.4f}]   {out}")
    return lo > 0 or hi < 0


def main() -> int:
    cs = cells(SETTLE)
    print(f"blocks recorded: {len(cs)}/6")
    for c in cs:
        print(_line(c))
    if len(cs) < 6:
        print("\nNot all six blocks are in. The pre-registration fixes a pool "
              "of six, so\nthere is no verdict to print yet -- and looking at "
              "a partial pool and\nthen deciding whether to continue is "
              "precisely what pre-registering was\nfor. Re-run when the "
              "remaining blocks land.")
        return 1

    n_tot = sum(c["n"] for c in cs)
    mde = Z * PER_PAIR_SD / math.sqrt(n_tot)
    print(f"\ntotal pairs {n_tot}, MDE {mde:.3f} against an assumed effect of "
          f"{ASSUMED_EFFECT:+.3f}")

    p = pool(cs)
    demonstrated = _verdict(p["fe"], p["fe_se"],
                            "PRIMARY -- fixed-effect pool of the six new blocks")

    print(f"\nhomogeneity across the six (diagnostic only)")
    print(f"  Cochran Q  {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2        {100 * p['i2']:.1f}%")
    print(f"  tau        {p['tau']:.4f} sets per pair")
    if p["q_p"] < 0.05:
        print("  The blocks disagree by more than sampling noise allows. The "
              "A/A study\n  measured no between-run variance, so read this as "
              "an effect that depends\n  on the deal population, not as a "
              "reason to re-pool.")

    extra = cells(UNSELECTED)
    if len(extra) == len(UNSELECTED):
        allc = cs + extra
        p2 = pool(allc)
        n2 = sum(c["n"] for c in allc)
        print(f"\nsecondary -- all {len(allc)} unselected cells, {n2} pairs "
              f"(reported, not decisive)")
        for c in extra:
            print(f"  {c['label'][:52]:<52} n={c['n']:>4} {c['est']:>+7.3f}")
        _verdict(p2["fe"], p2["fe_se"], "  pooled")

    print("\n" + "=" * 68)
    if demonstrated:
        print("VERDICT: the effect is DEMONSTRATED by the pre-registered test.")
    else:
        print("VERDICT: NOT DEMONSTRATED.")
        print("The pre-registration commits to reporting it that way whatever "
              "the\nsecondary pool says, and to adding no further run to chase "
              "significance.\nIf 6000 pairs does not settle it, the effect is "
              "below what this project\ncan resolve at reasonable cost, and "
              "that is the finding.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
