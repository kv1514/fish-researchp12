"""The pre-registered verdict on buying posterior precision.

Does what ``jobs/PREREGISTRATION_precision.md`` says and nothing else. Same
shape as ``scripts4/settle_verdict.py``, and for the same reason: the analysis
was fixed before the blocks existed, so it cannot be a choice about the numbers.

  PRIMARY, and the only thing that decides. Fixed-effect pool of the six
  blocks. Every block is unselected, so none may be dropped for its result.
  Demonstrated if and only if the 95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the six, diagnostic only.

  CONTEXT, not decisive. The two screening cells, explicitly labelled as
  screens. The pre-registration was written before either had a number and was
  sized against a threshold, so neither contributes to the design or the
  verdict.

  THE DEFAULT IS A SEPARATE DECISION. The pre-registration commits to this in
  advance: ``n_draws`` trades playing strength against inference latency, and
  the public table has a request budget. This script therefore prints the
  measured cost next to the measured effect and stops there. It does not change
  a default and there is no code path here that could.

    py scripts4/precision_verdict.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))
sys.path.insert(0, str(ROOT))

from pool_cells import Z, cells, pool                            # noqa: E402

BLOCKS = [f"PRECISION n_draws 480 vs 160 block {i}" for i in range(6)]

SCREENS = [
    "SCREEN precision half n_draws 80 vs 160",
    "SCREEN precision triple n_draws 480 vs 160",
]

#: Fixed in the pre-registration, before any of it ran.
MIN_INTERESTING = 0.15
PER_PAIR_SD = 3.796
PREREG_MDE = 0.137

LATENCY = ROOT / "results" / "precision_cost.json"


def _line(c):
    return (f"  block {c['label'][-1]}  n={c['n']:>5}  {c['est']:>+7.3f} "
            f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")


def main() -> int:
    cs = cells(BLOCKS)
    print("is posterior precision worth buying?")
    print(f"\nblocks recorded: {len(cs)}/6")
    for c in cs:
        print(_line(c))
    if len(cs) < 6:
        print("\nNot all six blocks are in, so there is no verdict to print. "
              "Looking at a\npartial pool of a pre-registered run and then "
              "deciding whether to continue\nis exactly what pre-registering "
              "was for. Re-run when they land.")
        return 1

    n_tot = sum(c["n"] for c in cs)
    half = Z * PER_PAIR_SD / math.sqrt(n_tot)
    mde = (Z + 0.8416212) * PER_PAIR_SD / math.sqrt(n_tot)
    print(f"\ntotal pairs {n_tot}")
    print(f"  MDE at 80% power        {mde:.3f}  "
          f"(pre-registered as {PREREG_MDE:.3f})")
    print(f"  95% interval half-width {half:.3f}")
    print(f"  minimum interesting effect, fixed in advance  "
          f"{MIN_INTERESTING:+.3f}")

    p = pool(cs)
    est, se = p["fe"], p["fe_se"]
    lo, hi = est - Z * se, est + Z * se
    demonstrated = lo > 0 or hi < 0
    print("\nPRIMARY -- fixed-effect pool of the six blocks")
    print(f"  {est:+.4f}  95% [{lo:+.4f}, {hi:+.4f}]   "
          f"{'EXCLUDES ZERO' if demonstrated else 'INCLUDES ZERO'}")

    print("\nhomogeneity across the six (diagnostic only)")
    print(f"  Cochran Q  {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2        {100 * p['i2']:.1f}%")
    print(f"  tau        {p['tau']:.4f} sets per pair")

    sc = cells(SCREENS)
    if sc:
        print("\nSCREENS -- context only, contributed nothing to the design")
        for c in sc:
            print(f"  {c['label']:<44} n={c['n']:>4} {c['est']:>+7.3f} "
                  f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
        trip = [c for c in sc if "triple" in c["label"]]
        if trip and demonstrated:
            d = est - trip[0]["est"]
            print(f"\n  The 400-pair screen of this same cell read "
                  f"{trip[0]['est']:+.3f}; the pre-registered\n"
                  f"  run reads {est:+.3f}, {d:+.3f} higher. The screen did "
                  f"not inflate this one --\n  which is what an unselected "
                  f"screen looks like, and is only worth saying\n  because the "
                  f"selected ones in this project inflated every time.")

    print("\n" + "=" * 70)
    if demonstrated:
        print("VERDICT: the effect is DEMONSTRATED by the pre-registered test.")
        if lo > MIN_INTERESTING:
            print(f"The whole interval clears the {MIN_INTERESTING:+.2f} "
                  f"threshold set in advance, so the")
            print("effect is not merely real, it is large enough to have been "
                  "worth finding.")
        else:
            print(f"The interval excludes zero but reaches below the "
                  f"{MIN_INTERESTING:+.2f} threshold set in")
            print("advance, so the effect is real and may still be too small "
                  "to be worth its price.")
    else:
        print("VERDICT: NOT DEMONSTRATED.")
        print("Reported that way whatever the screens said, with no further "
              "run added to\nchase significance.")
    print("=" * 70)

    print("\nTHE DEFAULT")
    if LATENCY.exists():
        cost = json.loads(LATENCY.read_text())
        b = cost["per_decision_ms"]
        print(f"  inference per decision   {b['160']:.1f} ms at 160 draws, "
              f"{b['480']:.1f} ms at 480")
        print(f"  ratio                    {b['480'] / b['160']:.2f}x")
        print(f"  measured on {cost['n_decisions']} decisions "
              f"({cost['host']})")
    else:
        print("  Cost not measured yet -- run scripts4/precision_cost.py.")
    print("  Whether to move the default is a separate decision from whether "
          "the effect\n  is real, and the pre-registration says so. This "
          "script does not make it.")

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot,
           "mde_80": mde, "half_width": half,
           "min_interesting": MIN_INTERESTING,
           "demonstrated": bool(demonstrated),
           "screens": sc}
    dest = ROOT / "results" / "precision_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
