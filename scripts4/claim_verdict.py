"""The pre-registered verdict on lowering the claim threshold to 0.90.

Does what ``jobs/PREREGISTRATION_claim_threshold.md`` says and nothing else.

  PRIMARY. Fixed-effect pool of the two blocks; demonstrated if and only if the
  95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the two, diagnostic only.

  THE SCREEN, LABELLED AS ONE. The +0.035 that motivated this run was selected
  out of 103 cells for excluding zero, so it is inadmissible as evidence and
  sized nothing here. It is printed as a contrast so the decay is visible.

  THE RECORDED PREDICTION. The pre-registration states, in advance, that the
  divergence share should come out SUBSTANTIALLY ABOVE the 0.5% that
  results/pair_sd_model.json implies at this per-pair sd, because a threshold
  change alters one decision rather than the whole line of play. That
  prediction is scored here against what the run actually did. Nothing in the
  primary analysis depends on it.

  THE SIZING, CHECKED AFTER THE FACT. The design assumed a per-pair sd of
  0.286, derived from the screening cell's own interval. This prints the sd the
  run actually had and the MDE that follows from it, because a design that
  missed its power target should say so rather than quote the planned number.

    py scripts4/claim_verdict.py
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

BLOCKS = [f"CLAIM THRESHOLD 0.90 vs 0.97 block {i}" for i in range(2)]

#: The 400-pair screening cell that motivated this run, and the entire reason a
#: confirmatory run was required. Selected out of 103 cells for excluding zero.
SCREEN = 0.035
SCREEN_CI = (0.007377, 0.062623)
SCREEN_N = 400

#: Minimum interesting effect, fixed in the pre-registration before any pair.
MIE = 0.02

#: Per-pair sd the design assumed, derived from the screening cell's interval.
PLANNED_SD = 0.286
PLANNED_MDE = 0.018

#: The divergence model's constant conditional term AS THE PRE-REGISTRATION
#: RECORDED IT. The file has since grown and now holds 3.859 over 46 cells;
#: this run is scored against both, because the prediction was written against
#: the first and the model that exists is the second. The pre-registration
#: declines to USE either to size this run -- the run sits an order of
#: magnitude below where the model was fitted -- and records what they would
#: have implied so the extrapolation can be scored.
PREREG_COND_SD = 3.88

#: The behavioural difference between the two arms, measured before the run
#: over 998 decisions carrying a claim candidate.
EXTRA_CLAIMS_PER_998 = 1


def _t(n: int) -> float:
    from fish4.match import _t_critical
    return _t_critical(n - 1, 0.95)


def main() -> int:
    cs = cells(BLOCKS)
    print("is the claim threshold worth lowering from 0.97 to 0.90?")
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
            print(f"\n{label} has no per-pair differentials, so the divergence "
                  f"share\nand the realised sd cannot be computed. Refusing to "
                  f"guess them.", file=sys.stderr)
            return 2
        diffs.extend(float(x) for x in d)

    n_tot = len(diffs)
    sd = statistics.stdev(diffs)
    mde = (Z + 0.8416212) * sd / math.sqrt(n_tot)

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

    print("\nTHE SCREEN, printed as the selected cell it is")
    print(f"  screen, n={SCREEN_N}          {SCREEN:+.3f} "
          f"[{SCREEN_CI[0]:+.3f}, {SCREEN_CI[1]:+.3f}]")
    print(f"  confirmatory, n={n_tot}    {est:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    s_se = (SCREEN_CI[1] - SCREEN_CI[0]) / (2 * _t(SCREEN_N))
    d = est - SCREEN
    d_se = math.hypot(se, s_se)
    print(f"  decay                   {d:+.3f} +/- {d_se:.3f}  "
          f"({d / d_se:+.1f} SE)")
    if d + Z * d_se < 0:
        print("  The confirmatory estimate is below the screen by more than "
              "the joint noise\n  allows. That is selection inflation measured "
              "directly, not inferred: the\n  screen was chosen out of 103 "
              "cells FOR excluding zero, and the unselected\n  re-run does not "
              "reproduce it.")
    else:
        print("  The two are not distinguishable, so this run neither "
              "reproduces the screen\n  nor convicts it of inflation.")

    print("\nTHE RECORDED PREDICTION -- divergence share at the thin end")
    n_div = sum(1 for x in diffs if x != 0.0)
    share = n_div / n_tot
    cond = [x for x in diffs if x != 0.0]
    cond_sd = statistics.stdev(cond) if len(cond) > 1 else float("nan")
    model = json.loads(
        (ROOT / "results" / "pair_sd_model.json").read_text())
    cond_now = float(model["cond_sd_mean"])
    s_lo, s_hi = model["share_range"]
    drift = model["cond_drift"]
    drift_pred = drift["intercept"] + drift["slope"] * share
    implied = (sd / PREREG_COND_SD) ** 2
    print(f"  measured divergence     {n_div}/{n_tot} = {100 * share:.2f}%")
    print(f"  model would imply       {100 * implied:.2f}%  "
          f"(from sd {sd:.3f} and the pre-registered {PREREG_COND_SD})")
    print(f"  measured conditional sd {cond_sd:.3f}, against the "
          f"pre-registered {PREREG_COND_SD}")
    if share > 2 * implied and cond_sd < PREREG_COND_SD:
        print("  Both halves of the prediction hold: the share is far above "
              "what the model\n  implies, and it is above BECAUSE the "
              "conditional differences are smaller.\n  A threshold change "
              "moves one decision, not the line of play, so the model's\n  "
              "constant conditional term does not extend to this end. It was "
              "recorded in\n  advance that it would not, and it does not.")
    else:
        print("  The prediction recorded in advance does not hold. It decides "
              "nothing here,\n  and it is printed because it was written down "
              "to be scored either way.")

    print(f"\n  and the model as it stands now, {model['n_cells']} cells "
          f"fitted over shares {s_lo:.3f}-{s_hi:.3f}:")
    flat_err = cond_now / cond_sd - 1.0
    drift_err = drift_pred / cond_sd - 1.0
    print(f"    flat conditional term   {cond_now:.3f}  "
          f"({flat_err:+.1%} against the measured {cond_sd:.3f})")
    print(f"    drift-corrected         {drift_pred:.3f}  "
          f"({drift_err:+.1%})")
    print(f"  This run's share is {s_lo / share:.0f}x BELOW the low end of "
          f"the range the drift term\n  was fitted on, so this is "
          f"extrapolation, not interpolation. The correction\n  is "
          f"{abs(flat_err) / max(abs(drift_err), 1e-9):.1f}x closer than the "
          f"flat term it replaces at a share it never saw.")

    print("\nTHE SIZING, checked against what the run actually had")
    print(f"  planned per-pair sd     {PLANNED_SD:.3f}  -> MDE "
          f"{PLANNED_MDE:.3f}")
    print(f"  realised per-pair sd    {sd:.3f}  -> MDE {mde:.3f}")
    print(f"  minimum interesting     {MIE:.3f}")
    if mde > MIE:
        print(f"  The realised MDE is ABOVE the effect this run was built to "
              f"detect. The sd\n  derived from the screening cell's interval "
              f"came in {100 * (sd / PLANNED_SD - 1):.0f}% low, so the design "
              f"is\n  under-powered for {MIE:+.3f} by its own standard. That "
              f"widens what a null here\n  is allowed to mean, and it is "
              f"stated rather than quoting the planned number.")
    else:
        print("  The realised MDE is at or below the minimum interesting "
              "effect, so a null\n  here rules out an effect of the size this "
              "run was built to detect.")

    print("\n" + "=" * 70)
    if excludes and est > 0:
        print("VERDICT: lowering the threshold to 0.90 BEATS the default.")
        print("The pre-registration commits, in advance, that a demonstrated "
              "effect moves\nthe default here -- uniquely among this study's "
              "changes, because this one is\none constant and costs nothing to "
              "run.")
    elif excludes:
        print("VERDICT: lowering the threshold to 0.90 LOSES to the default.")
        print("The screen had the sign backwards as well as the magnitude.")
    else:
        print("VERDICT: NO EFFECT RESOLVED AT THIS SIZE.")
        print(f"The interval contains zero, and the point estimate {est:+.4f} "
              f"is a fifth of the\nscreen's {SCREEN:+.3f}. The header of "
              f"fish4/claim4.py argued that waiting to claim is\nclose to "
              f"free; the one cell that contradicted it does not survive an "
              f"unselected\nre-run at five times the size.")
        print(f"\nThe behavioural change was {EXTRA_CLAIMS_PER_998} extra "
              f"claim in 998 candidate decisions, and\n{100 * share:.1f}% of "
              f"pairs diverged at all. This is a null with a mechanism, not\n"
              f"a null from thin data.")
        if mde > MIE:
            print(f"\nRead it against the realised MDE of {mde:.3f}, not the "
                  f"planned {PLANNED_MDE:.3f}: an effect of\nexactly "
                  f"{MIE:+.3f} would have been missed more often than the "
                  f"design intended.")
    print("=" * 70)

    out = {
        "blocks": cs, "pooled": p, "n_pairs": n_tot,
        "estimate": est, "se": se, "ci": [lo, hi],
        "excludes_zero": bool(excludes),
        "realised_sd": sd, "mde_80": mde,
        "planned_sd": PLANNED_SD, "planned_mde": PLANNED_MDE,
        "minimum_interesting_effect": MIE,
        "screen": {"est": SCREEN, "ci": list(SCREEN_CI), "n": SCREEN_N,
                   "decay": d, "decay_se": d_se},
        "divergence": {"n": n_div, "share": share,
                       "conditional_sd": cond_sd,
                       "model_implied_share": implied,
                       "prereg_cond_sd": PREREG_COND_SD,
                       "model_cond_sd_now": cond_now,
                       "model_share_range": [s_lo, s_hi],
                       "model_n_cells": model["n_cells"],
                       "drift_pred_cond_sd": drift_pred,
                       "flat_rel_err": flat_err,
                       "drift_rel_err": drift_err},
    }
    dest = ROOT / "results" / "claim_threshold_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
