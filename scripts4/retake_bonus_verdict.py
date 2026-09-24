"""The pre-registered verdict on rewarding the re-take.

Does what ``jobs/PREREGISTRATION_retake_bonus.md`` says and nothing else.

  PRIMARY. Fixed-effect pool of the two blocks; demonstrated if and only if the
  95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the two, diagnostic only.

  THE CONTRAST WORTH REPORTING. This estimate against the gated PENALTY's
  -0.004. The two act on disjoint slices of the same situation in opposite
  directions, so a positive here beside a null there would say the asymmetry is
  real; two nulls say the re-take decision does not repay any policy at all.

  WHAT THE WEIGHT CAN ACTUALLY REACH, measured before the run rather than
  assumed. A re-take is a CERTAIN ask, so the objective already scores it at
  P(success)=1 and it is already the chosen ask at 69% of the positions where
  it is legal. A bonus can act at 3.5% of positions, and where it can, the
  median score gap to the leader is 0.000 -- it breaks an exact tie. Breaking a
  tie has expected value zero unless the objective is systematically wrong in a
  way correlated with re-taking. This run tests that, and the pre-registration
  says so, so a null here is a null about TIE-BREAKING and not about the folk
  advice to trade hard.

  THE PRIOR, restated because it decides how to read a positive. Six cells of
  this family have been measured and none has paid. The pre-registration
  commits a positive to one replication at the same size on fresh seeds and to
  nothing else -- no default moves.

    py scripts4/retake_bonus_verdict.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))
sys.path.insert(0, str(ROOT))

from pool_cells import Z, cells, pool                            # noqa: E402

BLOCKS = [f"RETAKE BONUS w-0.30 vs champion block {i}" for i in range(2)]

#: The gated penalty over 2000 pairs -- the same situation, the opposite
#: policy, on a disjoint slice. From results/retake_verdict.json, read at run
#: time so the two cannot drift apart.
GATED_PENALTY_FILE = "retake_verdict.json"

#: Per-pair sd the design assumed, from scaling the ungated penalty's measured
#: divergence share by the ratio of reachable positions. Recorded so the power
#: statement is reproducible and so the realised value can be checked against
#: it, which is where the claim-threshold run's design came apart.
PLANNED_SD = 1.57
PLANNED_MDE = 0.098

#: How many cells of this family have been measured and lost.
PRIOR_FAILURES = 6


def main() -> int:
    cs = cells(BLOCKS)
    print("does trading hard inside a duel pay?")
    print(f"\nblocks recorded: {len(cs)}/2")
    for c in cs:
        print(f"  block {c['label'][-1]}  n={c['n']:>5}  {c['est']:>+7.3f} "
              f"[{c['lo']:+.3f}, {c['hi']:+.3f}]   per-pair sd {c['sd']:.3f}")
    if len(cs) < 2:
        print("\nBoth blocks are not in, so there is no verdict to print. "
              "Looking at a partial\npool of a pre-registered run and then "
              "deciding whether to continue is exactly\nwhat pre-registering "
              "was for. Re-run when they land.")
        return 1

    rows = [json.loads(l) for l in
            (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines()
            if l.strip()]
    diffs: list[float] = []
    for label in BLOCKS:
        r = next(r for r in rows if r.get("label") == label)
        d = r.get("diffs")
        if not d or len(d) != int(r["n_pairs"]):
            print(f"\n{label} has no per-pair differentials, so the realised "
                  f"sd and the\ndivergence share cannot be computed. Refusing "
                  f"to guess them.", file=sys.stderr)
            return 2
        diffs.extend(float(x) for x in d)

    n_tot = len(diffs)
    sd = statistics.stdev(diffs)
    mde = (Z + 0.8416212) * sd / math.sqrt(n_tot)
    n_div = sum(1 for x in diffs if x != 0.0)
    share = n_div / n_tot

    p = pool(cs)
    est, se = p["fe"], p["fe_se"]
    lo, hi = est - Z * se, est + Z * se
    excludes = lo > 0 or hi < 0
    print("\nPRIMARY -- fixed-effect pool of the two blocks")
    print(f"  {est:+.4f}  95% [{lo:+.4f}, {hi:+.4f}]   "
          f"{'EXCLUDES ZERO' if excludes else 'INCLUDES ZERO'}")

    print("\nhomogeneity across the two (diagnostic only)")
    print(f"  Cochran Q  {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2        {100 * p['i2']:.1f}%")
    if p["q_p"] < 0.05:
        print("  Heterogeneous. The fixed-effect pool was named primary before "
              "any of this\n  was known and stays primary; this is a note on "
              "it, not a replacement.")

    print("\nTHE SIZING, checked against what the run actually had")
    print(f"  planned per-pair sd     {PLANNED_SD:.3f}  -> MDE "
          f"{PLANNED_MDE:.3f}")
    print(f"  realised per-pair sd    {sd:.3f}  -> MDE {mde:.3f}")
    print(f"  divergence share        {n_div}/{n_tot} = {100 * share:.2f}%  "
          f"(design assumed 16.2%)")
    if mde > PLANNED_MDE * 1.05:
        print(f"  The realised MDE is {mde / PLANNED_MDE:.2f}x the planned "
              f"one, so this run resolves LESS\n  than the design claimed and "
              f"the null is reported against {mde:.3f}.")
    elif mde < PLANNED_MDE * 0.95:
        print(f"  The realised MDE is {mde / PLANNED_MDE:.2f}x the planned "
              f"one: the run resolves MORE\n  than the design claimed.")
    else:
        print("  The design's per-pair sd held, so the planned power statement "
              "is the one\n  that applies.")

    gp = json.loads((ROOT / "results" / GATED_PENALTY_FILE).read_text())
    g_est = float(gp["pooled"]["fe"])
    g_se = float(gp["pooled"]["fe_se"])
    print("\nTHE CONTRAST WORTH REPORTING -- bonus against the gated penalty")
    print(f"  gated penalty, w=+0.30   {g_est:+.3f} "
          f"[{g_est - Z * g_se:+.3f}, {g_est + Z * g_se:+.3f}]")
    print(f"  bonus, w=-0.30           {est:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    d = est - g_est
    d_se = math.hypot(se, g_se)
    print(f"  difference               {d:+.3f} +/- {d_se:.3f}  "
          f"({d / d_se:+.1f} SE)")
    g_null = (g_est - Z * g_se) <= 0 <= (g_est + Z * g_se)
    if not excludes and g_null:
        print("  Both directions are null on disjoint slices of the same "
              "situation. The\n  re-take decision does not repay ANY policy "
              "here -- neither withholding nor\n  trading -- which is a "
              "stronger statement than either null alone.")
    elif excludes and g_null:
        print("  A resolved effect here beside a null there says the asymmetry "
              "is real: the\n  two slices of the same decision do not behave "
              "the same way.")

    print("\n" + "=" * 70)
    if excludes and est > 0:
        print("VERDICT: rewarding the re-take BEATS the champion.")
        print(f"This is the {PRIOR_FAILURES + 1}th cell of a family with "
              f"{PRIOR_FAILURES} failures, and the pre-registration\ncommits a "
              f"positive to ONE REPLICATION at the same size on fresh seeds "
              f"and to\nnothing else. No default moves on this.")
        print("\nNote what the base rate says it can be: the weight reaches "
              "3.5% of positions,\nand at the median reachable position the "
              "score gap to the leader is 0.000. An\neffect this large from "
              "tie-breaking would mean the objective is systematically\nwrong "
              "in a way correlated with re-taking, which is a claim about the "
              "objective\nand should be tested as one.")
    elif excludes:
        print("VERDICT: rewarding the re-take LOSES to the champion.")
        print(f"The {PRIOR_FAILURES + 1}th failure in this family, and the "
              f"first in the trading direction. Both\ndirections of the "
              f"re-take decision have now been measured and both cost.")
    else:
        print("VERDICT: NO EFFECT RESOLVED AT THIS SIZE.")
        print(f"Reported as the {PRIOR_FAILURES + 1}th entry in the table, and "
              f"specifically as a null about\nTIE-BREAKING: the base rate "
              f"measured before the run says the weight can act at\n3.5% of "
              f"positions and that the median reachable position is an exact "
              f"tie. This\nrun did not test 'trade hard in a duel' as a human "
              f"would mean it, and the\npre-registration said so before the "
              f"first pair.")
    print("=" * 70)

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot,
           "estimate": est, "se": se, "ci": [lo, hi],
           "excludes_zero": bool(excludes),
           "realised_sd": sd, "mde_80": mde,
           "planned_sd": PLANNED_SD, "planned_mde": PLANNED_MDE,
           "divergence": {"n": n_div, "share": share},
           "contrast_vs_gated_penalty": {"gated": g_est, "gated_se": g_se,
                                         "delta": d, "se": d_se},
           "prior_failures": PRIOR_FAILURES}
    dest = ROOT / "results" / "retake_bonus_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
