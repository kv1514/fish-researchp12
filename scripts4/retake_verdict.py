"""The pre-registered verdict on the gated retake penalty.

Does what ``jobs/PREREGISTRATION_retake_gate.md`` says and nothing else.

  PRIMARY. Fixed-effect pool of the two blocks; the estimate and its 95%
  interval.

  THE CONTRAST THAT MATTERS. This estimate against the ungated -0.340. The gate
  is vindicated to the extent the difference is positive; it is refuted if the
  two are indistinguishable, because then the exemption changed nothing.

  HOMOGENEITY. Cochran's Q across the two, diagnostic only.

  THE PRIOR, restated because it decides how to read a positive. Five screening
  cells have measured this family and all five failed, two decisively and
  monotonically in the penalty. The pre-registration commits a positive result
  to a replication rather than to a paragraph, and this script prints that
  rather than letting it be forgotten.

  A CEILING, fixed in advance. The gate un-flags 47% of what the ungated
  penalty flags, so if the harm is proportional to what is flagged the most it
  can recover is +0.159. An estimate above the UNGATED value is what the gate
  predicts; an estimate above zero is more than it claims.

    py scripts4/retake_verdict.py
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

BLOCKS = [f"RETAKE GATE w0.30 depth>=2 vs champion block {i}" for i in range(2)]

#: The ungated penalty at the same weight, over 200 pairs. Fixed in the
#: pre-registration; not re-estimated here.
UNGATED = -0.340
UNGATED_CI = (-0.665, -0.015)

#: The most the gate can recover if the harm is proportional to what it flags,
#: from results/duel_depth_base_rate.json under the CORRECTED duel statistic.
#: The pre-amendment figure was +0.098; the correction raised it.
CEILING = 0.159

#: Per-pair sd from the divergence model rather than the A/A 3.796, as
#: pre-registered. Recorded here so the power statement is reproducible.
PER_PAIR_SD = 1.77

#: How many cells in this family have already been measured and lost.
PRIOR_FAILURES = 5


def main() -> int:
    cs = cells(BLOCKS)
    print("does withholding help once it only fires on a real duel?")
    print(f"\nblocks recorded: {len(cs)}/2")
    for c in cs:
        print(f"  block {c['label'][-1]}  n={c['n']:>5}  {c['est']:>+7.3f} "
              f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
    if len(cs) < 2:
        print("\nBoth blocks are not in, so there is no verdict to print. "
              "Looking at a partial\npool of a pre-registered run and then "
              "deciding whether to continue is exactly\nwhat pre-registering "
              "was for. Re-run when they land.")
        return 1

    n_tot = sum(c["n"] for c in cs)
    se_design = PER_PAIR_SD / math.sqrt(n_tot)
    mde = (Z + 0.8416212) * se_design
    print(f"\ntotal pairs {n_tot}")
    print(f"  MDE at 80% power        {mde:.3f}")
    print(f"  95% interval half-width {Z * se_design:.3f}")
    print(f"  ceiling on what the gate can recover {CEILING:+.3f}")

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

    print("\nTHE CONTRAST THAT MATTERS -- gated against ungated")
    d = est - UNGATED
    d_se = math.hypot(se, (UNGATED_CI[1] - UNGATED_CI[0]) / (2 * Z))
    print(f"  ungated penalty, w=0.30   {UNGATED:+.3f} "
          f"[{UNGATED_CI[0]:+.3f}, {UNGATED_CI[1]:+.3f}]")
    print(f"  gated on duel_depth >= 2  {est:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    print(f"  difference                {d:+.3f} +/- {d_se:.3f}  "
          f"({d / d_se:+.1f} SE)")
    vindicated = d - Z * d_se > 0
    if vindicated:
        print("  The gated form is better than the ungated one by a margin "
              "this design\n  resolves, so the exemption is doing the work the "
              "argument said it would.")
        if d > CEILING:
            print(f"\n  But the recovery is {d:+.3f} where the gate's own "
                  f"model caps it at {CEILING:+.3f}. A gate\n  cannot recover "
                  f"more harm than it removes flags for, so one of the two "
                  f"numbers\n  is wrong, and the likelier one is the ungated "
                  f"{UNGATED:+.3f}: it comes from a 200-pair\n  screen whose "
                  f"interval [{UNGATED_CI[0]:+.3f}, {UNGATED_CI[1]:+.3f}] "
                  f"barely clears zero, which is exactly the\n  setup that "
                  f"inflates an effect. Read this contrast as the gate "
                  f"removing the\n  harm AND that harm having been "
                  f"overstated, not as the gate earning "
                  f"{d:+.3f}.")
    else:
        print("  The two are not distinguishable, so the exemption did not "
              "change what\n  mattered. Note the ungated figure comes from a "
              "200-pair screen and carries\n  a wide interval of its own, "
              "which is most of this contrast's noise.")

    print("\n" + "=" * 70)
    if excludes and est > 0:
        print("VERDICT: the gated penalty BEATS the champion.")
        print(f"This is the {PRIOR_FAILURES + 1}th cell of a family with "
              f"{PRIOR_FAILURES} failures, and the pre-registration\ncommits a "
              f"positive to a REPLICATION at the same size on fresh seeds, not "
              f"to a\nparagraph. Nothing is claimed and no default moves until "
              f"a replication agrees.")
        if est > CEILING:
            print(f"\nNote also that {est:+.3f} exceeds the {CEILING:+.3f} "
                  f"ceiling this gate can recover if the\nharm is "
                  f"proportional to what it flags. Beating the ceiling means "
                  f"the model\nbehind the ceiling is wrong, which is a reason "
                  f"for more suspicion, not less.")
    elif excludes:
        print("VERDICT: the gated penalty LOSES to the champion.")
        print(f"The sixth entry in a family of {PRIOR_FAILURES} failures, and "
              f"the first tested in the form\nits own argument describes. "
              f"Withholding the re-take does not pay even when\nit only fires "
              f"on a repeated exchange.")
    else:
        print("VERDICT: NO EFFECT RESOLVED AT THIS SIZE.")
        print(f"The interval contains zero. The gate can recover at most "
              f"{CEILING:+.3f} on its own\nmodel, against an MDE of "
              f"{mde:.3f} here, so this run could see an effect of the\nsize "
              f"claimed and did not. Reported as the sixth entry in the table; "
              f"no blocks\nare added to chase it.")
    print("=" * 70)

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot, "mde_80": mde,
           "ungated": UNGATED, "ceiling": CEILING,
           "contrast_vs_ungated": {"delta": d, "se": d_se},
           "excludes_zero": bool(excludes),
           "beats_ungated": bool(vindicated)}
    dest = ROOT / "results" / "retake_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
