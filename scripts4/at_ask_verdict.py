"""The pre-registered verdict on at-ask-time depth with an exact normaliser.

Does what ``jobs/PREREGISTRATION_at_ask.md`` says and nothing else. Same shape
as the lookahead and precision verdicts, for the same reason.

  PRIMARY, and the only thing that decides. Fixed-effect pool of the six
  blocks. Every block is unselected, so none may be dropped for its result.
  Demonstrated if and only if the 95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the six, diagnostic only.

  CONTEXT, not decisive. All five screening cells, labelled as screens,
  including the four this run does not test. The design was argued from a
  likelihood fit and a normaliser measurement, not from any duel, so the screens
  were never load-bearing and the run was started before they could be.

  ONE CHANGE OR NONE. The pre-registration commits in advance that a
  demonstrated effect moves ``depth_mode`` and ``opponent_gamma`` together or
  not at all: they were argued for jointly and the screens cannot separate them,
  so claiming either alone would read a two-factor change as if it were one.
  This script therefore reports the pair and never a component.

    py scripts4/at_ask_verdict.py
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

BLOCKS = [f"AT_ASK g1.0 vs champion block {i}" for i in range(6)]

SCREENS = [
    "SCREEN at_ask depth g0.35 vs champion",
    "SCREEN at_ask depth g0.60 vs champion",
    "SCREEN at_ask depth g1.0 vs champion",
    "SCREEN gamma 1.0 exact normaliser (initial depth)",
    "SCREEN gamma profile under at_ask (prediction test)",
]

#: Fixed in the pre-registration before any of it ran.
MIN_INTERESTING = 0.15
PER_PAIR_SD = 3.796
PREREG_MDE = 0.137


def main() -> int:
    cs = cells(BLOCKS)
    print("does at-ask-time depth, at the exponent where the normaliser is "
          "exact, play better?")
    print(f"\nblocks recorded: {len(cs)}/6")
    for c in cs:
        print(f"  block {c['label'][-1]}  n={c['n']:>5}  {c['est']:>+7.3f} "
              f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
    if len(cs) < 6:
        print("\nNot all six blocks are in, so there is no verdict to print. "
              "Looking at a\npartial pool of a pre-registered run and then "
              "deciding whether to continue is\nexactly what pre-registering "
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
            print(f"  {c['label'][:46]:<46} n={c['n']:>4} {c['est']:>+7.3f} "
                  f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
        print("  Sized at 400 pairs, these resolve about +/-0.53, so every one "
              "of them is\n  uninformative rather than negative. That is why "
              "the run was started before\n  they finished and proceeds "
              "whatever they say.")

    print("\n" + "=" * 70)
    if demonstrated and est > 0:
        print("VERDICT: DEMONSTRATED.")
        print("The pre-registration binds depth_mode and opponent_gamma "
              "together, so what is\ndemonstrated is the PAIR: at-ask depth at "
              "gamma = 1.0. Neither component is\nclaimed on its own, and this "
              "script has no way to report one.")
    elif demonstrated:
        print("VERDICT: DEMONSTRATED, AND NEGATIVE.")
        print("The configuration is worse than the champion by a margin this "
              "run resolves.\nThat is a refutation of the argument from the "
              "normaliser, not a null, and it\nis worth more than a null: the "
              "exponent at which the model is correctly\nspecified is not the "
              "exponent at which it plays best.")
    else:
        print("VERDICT: NOT DEMONSTRATED.")
        print("Reported that way whatever the screens said, with no further "
              "run added to\nchase significance, and no substitution of a "
              "better-scoring arm into this\ndocument -- that would convert a "
              "fixed analysis into a chosen one.")
    print("=" * 70)

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot, "mde_80": mde,
           "half_width": half, "min_interesting": MIN_INTERESTING,
           "demonstrated": bool(demonstrated), "screens": sc}
    dest = ROOT / "results" / "at_ask_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
