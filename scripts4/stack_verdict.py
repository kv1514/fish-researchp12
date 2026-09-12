"""The pre-registered verdict on whether the lookahead still pays on precision.

Does what ``jobs/PREREGISTRATION_stack.md`` says and nothing else. Written while
the run stood at 1 of 6 blocks, which is the only moment at which writing it
proves anything.

  PRIMARY, and the only thing that decides. Fixed-effect pool of the six
  blocks. Demonstrated if and only if the 95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the six, diagnostic only.

  THE ADDITIVITY CONTRAST, reported and not decisive. This estimate against the
  lookahead's +0.104 measured against the champion alone. Overlapping intervals
  mean the two features add as far as this study can tell; this one sitting
  below means they overlap in effect and the stack is worth less than the sum.

  AN INTERVAL CONTAINING ZERO IS NOT A NULL HERE, and the pre-registration says
  so in advance. At 6000 pairs this run has 68% power against its own stated
  alternative, so failing to exclude zero is a failure to resolve an effect of
  the size assumed -- not evidence that the lookahead stops paying. This script
  refuses to print the second sentence.

    py scripts4/stack_verdict.py
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

BLOCKS = [f"STACK lookahead on top of n_draws 480 block {i}" for i in range(6)]

#: Fixed in the pre-registration before any of it ran. The lookahead's own
#: measured effect against the champion, used as the alternative to size
#: against -- legitimate only because it came from an unselected pre-registered
#: run and is not being re-estimated here.
ALTERNATIVE = 0.104
#: Measured on the eight recorded lookahead-vs-champion cells, not the A/A 3.796.
PER_PAIR_SD = 3.323


def main() -> int:
    cs = cells(BLOCKS)
    print("does the belief-space search still pay once precision is bought?")
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
    se_design = PER_PAIR_SD / math.sqrt(n_tot)
    # power against the stated alternative, two-sided
    z = ALTERNATIVE / se_design
    power = 0.5 * (1 + math.erf((z - Z) / math.sqrt(2)))
    print(f"\ntotal pairs {n_tot}")
    print(f"  MDE at 80% power        {mde:.3f}")
    print(f"  95% interval half-width {half:.3f}")
    print(f"  alternative sized against {ALTERNATIVE:+.3f}, "
          f"power {100 * power:.0f}%")

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
    if p["q_p"] < 0.05:
        rlo = p["re"] - Z * p["re_se"]
        rhi = p["re"] + Z * p["re_se"]
        print(f"  Heterogeneous. Random-effects [{rlo:+.4f}, {rhi:+.4f}], "
              f"DIAGNOSTIC ONLY --\n  the fixed-effect pool was named primary "
              f"before any of this was known.")

    print("\nADDITIVITY -- reported, not decisive")
    d = est - ALTERNATIVE
    print(f"  the lookahead against the champion alone   {ALTERNATIVE:+.3f}")
    print(f"  the lookahead on top of 480 draws          {est:+.3f}")
    print(f"  difference                                 {d:+.3f}")
    if hi < ALTERNATIVE:
        print("  This run's whole interval sits below the lookahead's own "
              "effect, so the\n  two features overlap rather than add: buying "
              "precision removes part of\n  what the search was earning.")
    elif lo > ALTERNATIVE:
        print("  This run's whole interval sits above, so the search earns "
              "MORE on a sharper\n  belief than it did on the champion's.")
    else:
        print("  The intervals overlap, so as far as this study can tell the "
              "two features\n  add. With one point on each side that is a "
              "weak statement and is meant\n  as one.")

    print("\n" + "=" * 70)
    if demonstrated and est > 0:
        print("VERDICT: the lookahead STILL PAYS on top of precision.")
    elif demonstrated:
        print("VERDICT: the lookahead COSTS on top of precision.")
        print("A demonstrated negative, which is worth more than a null: the "
              "two features\ninterfere, and shipping both is worse than "
              "shipping the sampler alone.")
    else:
        print("VERDICT: NOT RESOLVED AT THIS SIZE.")
        print(f"The interval contains zero. With {100 * power:.0f}% power "
              f"against the {ALTERNATIVE:+.3f} this run\nwas sized against, "
              f"that is a failure to resolve an effect of the size assumed,\n"
              f"and it is NOT evidence that the lookahead stops paying. The "
              f"pre-registration\ncommits to reporting it this way, and to not "
              f"adding blocks to chase it.")
    print("=" * 70)
    print("\nNeither WEB_DRAWS nor V04_STRONGEST moves on this result in either")
    print("direction. Both features are already independently demonstrated; "
          "this run\nis about what may be CLAIMED, not about what ships.")

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot, "mde_80": mde,
           "alternative": ALTERNATIVE, "power_vs_alternative": power,
           "demonstrated": bool(demonstrated),
           "additivity_delta": d}
    dest = ROOT / "results" / "stack_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
