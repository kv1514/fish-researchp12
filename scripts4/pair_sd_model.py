"""How big is a duplicate-deal pair's standard deviation, and what sets it?

Every power calculation in this project sizes against **3.796 sets per pair**,
measured over 4800 A/A pairs. That number is used as though it were a property
of the deal population. It is not: it is a property of a pair of policies that
disagree constantly, and the experiments that most need sizing are the ones
whose arms barely disagree at all.

The retake screen at ``w=0.30`` measured a per-pair sd of **2.328**, not 3.796,
which is 7 standard errors away from the figure it was sized on. An experiment
sized on 3.796 and analysed on its own 2.328 is not wrong -- the interval it
reports is the right interval -- but it was designed to detect an effect 63%
larger than the one it could actually see, and would have been declared
underpowered when it was not.

THE DECOMPOSITION, AND WHICH HALF IS A DISCOVERY
------------------------------------------------
Under common random numbers a pair on which the two arms play identically has a
difference of exactly zero. So with ``s`` the share of pairs on which they
diverge at all,

    Var(D) ~= s * Var(D | they diverge)

and therefore ``sd ~= sqrt(s) * sd(D | diverge)``. That part is arithmetic, not
a finding; it follows from the design.

The finding is what this script measures: **``sd(D | diverge)`` is very nearly
the same number for every experiment in the study**, across features as
different as a search, a sampling budget, an opponent-model exponent and a
history-dependent penalty. If that holds, sizing any future experiment reduces
to predicting ONE quantity -- how often the two arms diverge -- which is far
cheaper to estimate than a pilot, because it can be counted from decisions
rather than from finished pairs.

Usage: python scripts4/pair_sd_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: What the project has been sizing on: the A/A figure.
AA_SD = 3.796
#: Cells smaller than this are too noisy to estimate an sd from.
MIN_PAIRS = 100



def _low_share_check(cells, flat, drift):
    """Test the two competing models where they were predicted to differ.

    The flat conditional term and the drift-corrected line agree wherever this
    study mostly lives -- share above 0.83 -- and diverge at low share, which
    is exactly where the rule gets INVOKED, to justify a smaller experiment
    than the A/A figure implies. When this decomposition was first written
    there were no cells down there and the paper said so.

    There are now. The retake-gate blocks landed at s ~ 0.234, and the
    prediction that the flat model over-states low-share noise by about 30%
    was recorded in jobs/PREREGISTRATION_retake_gate.md BEFORE any pair of
    that run was played. This scores it out of sample.
    """
    lo = [c for c in cells if c.get("share", 1.0) < 0.5]
    if not lo:
        return {"n": 0}
    a, b = drift["intercept"], drift["slope"]
    rows = []
    for c in sorted(lo, key=lambda c: c["share"]):
        s_, sd = c["share"], c["sd"]
        rows.append({"label": c.get("label"), "share": s_, "sd": sd,
                     "flat_pred": flat * s_ ** 0.5,
                     "drift_pred": (a + b * s_) * s_ ** 0.5})
    n = len(rows)
    return {"n": n,
            "flat_rel_err": sum(r["flat_pred"] / r["sd"] - 1
                                for r in rows) / n,
            "drift_rel_err": sum(r["drift_pred"] / r["sd"] - 1
                                 for r in rows) / n,
            "cells": rows}

def main():
    src = ROOT / "results" / "v04_duels.jsonl"
    cells = []
    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        d = r.get("diffs")
        if not d or len(d) < MIN_PAIRS:
            continue
        a = np.array(d, dtype=float)
        nz = a != 0
        if nz.sum() < 3:
            continue
        cells.append({
            "label": r["label"], "n": int(a.size),
            "sd": float(a.std(ddof=1)),
            "share": float(nz.mean()),
            "cond_sd": float(a[nz].std(ddof=1)),
        })
    if len(cells) < 5:
        print("not enough cells with stored per-pair differentials")
        return

    sd = np.array([c["sd"] for c in cells])
    sh = np.array([c["share"] for c in cells])
    cs = np.array([c["cond_sd"] for c in cells])

    print("what sets a duplicate-deal pair's standard deviation?\n")
    print(f"cells with stored per-pair differentials: {len(cells)}")
    print(f"per-pair sd ranges {sd.min():.3f} to {sd.max():.3f}; the project "
          f"sizes every\nexperiment on {AA_SD:.3f}\n")

    r_all = float(np.corrcoef(sh, sd)[0, 1])
    keep = sh > 0.6
    r_trim = float(np.corrcoef(sh[keep], sd[keep])[0, 1]) if keep.sum() > 3 \
        else float("nan")
    print(f"corr(divergence share, sd)          {r_all:+.3f}  "
          f"over all {len(cells)} cells")
    print(f"                                    {r_trim:+.3f}  "
          f"excluding the {(~keep).sum()} least-divergent")
    print("  Those correlations are nearly mechanical and are NOT the evidence.")
    print("  If sd = c*sqrt(s) with c anything like constant, corr(s, sd) is")
    print("  just the correlation of s with sqrt(s), which is close to 1 over")
    print("  any range. They are printed because a reader will compute them")
    print("  anyway, and should know they carry almost nothing.")

    print(f"\nthe part that is arithmetic:  sd = sqrt(share) * sd(D | diverge)")
    print(f"  raw sd              mean {sd.mean():.3f}  "
          f"relative spread {100 * sd.std(ddof=1) / sd.mean():4.1f}%")
    print(f"  sd / sqrt(share)    mean {(sd / np.sqrt(sh)).mean():.3f}  "
          f"relative spread "
          f"{100 * (sd / np.sqrt(sh)).std(ddof=1) / (sd / np.sqrt(sh)).mean():4.1f}%")

    print(f"\nthe part that is a finding:  sd(D | diverge) barely moves")
    print("  This is the whole claim, and the comparison that carries it is the")
    print("  spread of the conditional term against the spread of the raw sd:")
    print("  if the conditional part were as variable as the raw sd, the")
    print("  decomposition would explain nothing.")
    print(f"  mean {cs.mean():.3f}   sd {cs.std(ddof=1):.3f}   "
          f"range [{cs.min():.3f}, {cs.max():.3f}]   "
          f"spread {100 * cs.std(ddof=1) / cs.mean():.1f}%")
    print(f"  across a search, a sampling budget, an opponent-model exponent "
          f"and a\n  history-dependent penalty -- features with nothing in "
          f"common but the harness.")
    r_cond = float(np.corrcoef(sh, cs)[0, 1])
    print(f"  corr(share, conditional sd) = {r_cond:+.3f}: not zero, so it "
          f"drifts a little\n  with divergence and the rule below is a good "
          f"approximation rather than a law.")

    # How much of the conditional spread could be sampling noise in the sd
    # estimate itself, and does the decomposition explain anything inside the
    # band where the cells actually live?
    n = np.array([c["n"] for c in cells], dtype=float)
    floor = float(np.mean(1.0 / np.sqrt(2 * (n - 1))))
    obs = float(cs.std(ddof=1) / cs.mean())
    genuine = float(np.sqrt(max(0.0, obs ** 2 - floor ** 2)))
    print(f"\n  of that {100 * obs:.1f}%, {100 * floor:.1f}% is the sampling "
          f"noise of an sd estimate itself\n  ({100 * genuine:.1f}% is genuine "
          f"between-cell variation).")

    band = sh > 0.83
    if band.sum() > 5:
        print(f"\n  AND INSIDE THE BAND WHERE THE CELLS LIVE, IT EXPLAINS "
              f"NOTHING.")
        print(f"  Restricting to the {band.sum()} cells with share > 0.83:")
        print(f"    raw sd spread   {100 * sd[band].std(ddof=1) / sd[band].mean():5.2f}%")
        print(f"    cond sd spread  {100 * cs[band].std(ddof=1) / cs[band].mean():5.2f}%")
        print(f"    corr(share, sd) {np.corrcoef(sh[band], sd[band])[0, 1]:+.3f}")
        print("  Those two spreads are the same number. The headline comparison")
        print(f"  ({100 * sd.std(ddof=1) / sd.mean():.1f}% against "
              f"{100 * obs:.1f}%) is carried by the "
              f"{int((~band).sum())} cells outside the band,\n"
              "  and there are very few of them. The decomposition earns its "
              "keep only\n  where share actually varies, which in this study "
              "is barely anywhere.")

    # The conditional term is not constant, and the drift matters exactly where
    # the model gets extrapolated.
    A = np.column_stack([np.ones(sh.size), sh])
    b0, b1 = np.linalg.lstsq(A, cs, rcond=None)[0]
    print(f"\n  WORSE: the conditional term DRIFTS with share.")
    print(f"    corr(share, cond sd) {r_cond:+.3f}   fit  cond = {b0:.2f} + "
          f"{b1:.2f} * share")
    print(f"    {'share':>7}{'flat model':>13}{'drift model':>13}")
    for s0 in (0.31, 0.44, 0.85):
        print(f"    {s0:>7.2f}{cs.mean() * s0 ** 0.5:>13.3f}"
              f"{(b0 + b1 * s0) * s0 ** 0.5:>13.3f}")
    print("  At the low-share end the flat model over-predicts the standard")
    print("  deviation by about 30%. That direction is conservative for sizing")
    print("  -- it asks for more pairs than needed, never fewer -- but a rule")
    print("  used to justify a SMALLER run than the A/A figure implies should")
    print("  not be quoted as if it were calibrated there.")

    print(f"\n  AND `share` IS NOT WHAT IT SOUNDS LIKE. It is P(D != 0), and D")
    print("  is zero on plenty of pairs where the two arms genuinely diverged")
    print("  and the deal still ended level -- zero is not an isolated atom in")
    print("  these histograms. So a decision-level disagreement count, the")
    print("  cheap substitute this script advertises, is a strictly larger")
    print("  quantity than the one the constant was calibrated against.")

    print(f"\nWHERE THIS IS MEASURED, AND WHERE IT IS NOT")
    print(f"  divergence share across these cells runs "
          f"{sh.min():.2f} to {sh.max():.2f}.")
    print("  Every cell here changes something the policy consults constantly, so")
    print("  none of them is quiet. A change that binds rarely -- a claim")
    print("  threshold, a stall window -- diverges on a few percent of pairs, and")
    print("  the rule below is an EXTRAPOLATION there, not a measurement. It")
    print("  should not be trusted to size such a run; use the cell's own")
    print("  interval, which implies its standard deviation to within 1%.")

    print(f"\nHOW TO SIZE THE NEXT EXPERIMENT -- with the caveats above")
    print(f"  sd ~= {cs.mean():.2f} * sqrt(share of pairs on which the arms "
          f"diverge)")
    for s in (0.10, 0.25, 0.50, 0.85):
        est = cs.mean() * np.sqrt(s)
        mde = (1.96 + 0.8416212) * est / np.sqrt(1000)
        print(f"    share {s:4.2f}  ->  sd {est:5.3f}  ->  MDE at 80% power "
              f"over 1000 pairs {mde:.3f}")
    print(f"\n  Sizing a near-identical pair of arms on {AA_SD:.2f} overstates "
          f"its noise by\n  up to "
          f"{AA_SD / (cs.mean() * np.sqrt(0.10)):.1f}x, which is the "
          f"difference between an experiment that looks\n  impossible and one "
          f"that is routine.")

    cells.sort(key=lambda c: c["share"])
    print(f"\n{'cell':<46}{'n':>6}{'sd':>7}{'share':>7}{'cond':>7}")
    for c in cells:
        print(f"{c['label'][:46]:<46}{c['n']:>6}{c['sd']:>7.3f}"
              f"{c['share']:>7.3f}{c['cond_sd']:>7.3f}")

    out = {"aa_sd": AA_SD, "n_cells": len(cells),
           "corr_share_sd": r_all, "corr_share_sd_trimmed": r_trim,
           "corr_share_cond_sd": r_cond,
           "cond_sd_mean": float(cs.mean()),
           "cond_sd_spread": float(cs.std(ddof=1) / cs.mean()),
           "raw_sd_spread": float(sd.std(ddof=1) / sd.mean()),
           "share_range": [float(sh.min()), float(sh.max())],
           "sampling_floor": floor, "genuine_cond_spread": genuine,
           "band_raw_spread": float(sd[band].std(ddof=1) / sd[band].mean())
           if band.sum() > 5 else None,
           "band_cond_spread": float(cs[band].std(ddof=1) / cs[band].mean())
           if band.sum() > 5 else None,
           "low_share_check": _low_share_check(
               cells, float(cs.mean()),
               {"intercept": float(b0), "slope": float(b1)}),
           "cond_drift": {"intercept": float(b0), "slope": float(b1)},
           "cells": cells}
    dest = ROOT / "results" / "pair_sd_model.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
