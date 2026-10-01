"""What is the strongest configuration worth, and has anyone actually played it?

Two changes in this version beat the champion by a pre-registered margin: the
tripled posterior sampling budget (+0.340) and the belief-space lookahead
(+0.104). Each was measured against the champion ALONE, so neither says what
their combination is worth, and ``fish4/registry4.py`` deliberately refused to
name that combination for exactly that reason.

The stacking run now lets the two be chained. It measured the lookahead ON TOP
OF 480 draws, so:

    (480 + lookahead)  vs  480          =  the stacking run
    480                vs  champion     =  the precision run
    ------------------------------------------------------------
    (480 + lookahead)  vs  champion     =  the sum

The two runs use disjoint deal seeds (``scripts4/check_seeds.py`` verifies no
pooled estimate shares a deal), so they are independent and their standard
errors add in quadrature.

WHAT THIS IS NOT. It is an INDIRECT estimate. The combination has never been
played against the champion in a single duel, and a chained estimate inherits
every assumption of both links -- in particular that the effect of one change
does not depend on the deal population the other was measured over. It is good
enough to name the configuration and to size a direct run; it is not good enough
to quote as a measured headline.

Usage: python scripts4/combined_estimate.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from pool_cells import Z                                        # noqa: E402

LINKS = [
    ("posterior precision, 160 -> 480 draws", "precision_verdict.json"),
    ("belief-space lookahead, on top of 480", "stack_verdict.json"),
]


def main() -> int:
    print("what is the strongest configuration worth against the champion?\n")
    est, var, rows = 0.0, 0.0, []
    for label, fname in LINKS:
        f = ROOT / "results" / fname
        if not f.exists():
            print(f"missing {fname}; run its verdict script first")
            return 1
        d = json.loads(f.read_text())
        e, se = d["pooled"]["fe"], d["pooled"]["fe_se"]
        n = d.get("n_pairs")
        rows.append((label, e, se, n))
        est += e
        var += se * se
    se = math.sqrt(var)
    lo, hi = est - Z * se, est + Z * se

    print(f"{'link':<40}{'estimate':>10}{'se':>9}{'pairs':>8}")
    for label, e, s, n in rows:
        print(f"{label:<40}{e:>+10.4f}{s:>9.4f}{n:>8}")
    print(f"{'-' * 67}")
    print(f"{'chained: 480 + lookahead vs champion':<40}"
          f"{est:>+10.4f}{se:>9.4f}{sum(r[3] for r in rows):>8}")
    print(f"\n  95% interval  [{lo:+.4f}, {hi:+.4f}]   "
          f"{'EXCLUDES ZERO' if (lo > 0 or hi < 0) else 'includes zero'}")

    # The honest caveats, printed rather than left to the reader.
    print()
    if lo > 0:
        print("So the combined configuration beats the champion, and by more "
              "than either\nchange alone. That is enough to NAME it. It is not "
              "enough to call it\nmeasured: the combination has never been "
              "played against the champion in a\nsingle duel, and this number "
              "inherits both links' assumptions -- in\nparticular that each "
              "change's effect does not depend on the deal population\nthe "
              "other was measured over.")
    else:
        print("The chained interval contains zero, so the combination is not "
              "demonstrably\nbetter than the champion and must not be named as "
              "though it were.")

    stack = json.loads((ROOT / "results" / "stack_verdict.json").read_text())
    slo = stack["pooled"]["fe"] - Z * stack["pooled"]["fe_se"]
    print(f"\nSeparately, and this is the part that stays unresolved: whether "
          f"the\ncombination beats PRECISION ALONE. That is the stacking run's "
          f"own estimate,\n{stack['pooled']['fe']:+.4f}, whose interval "
          f"{'excludes' if slo > 0 else 'contains'} zero at "
          f"{100 * stack['power_vs_alternative']:.0f}% power. Adding the "
          f"search on top of a\nsharper belief is not demonstrated to help, and "
          f"is not demonstrated not to.")

    # What a direct run would need.
    sd = 3.796
    for n in (2000, 4000, 6000):
        mde = (Z + 0.8416212) * sd / math.sqrt(n)
        mark = "  <- resolves the chained estimate" if mde < est else ""
        print(f"  a direct run at {n:>5} pairs resolves {mde:.3f}{mark}"
              if n == 2000 else
              f"                  {n:>5} pairs resolves {mde:.3f}{mark}")

    out = {"links": [{"label": l, "est": e, "se": s, "n_pairs": n}
                     for l, e, s, n in rows],
           "chained": {"est": est, "se": se, "lo": lo, "hi": hi,
                       "excludes_zero": bool(lo > 0 or hi < 0)},
           "indirect": True,
           "direct_run_played": False}
    dest = ROOT / "results" / "combined_estimate.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
