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
          f"excluding the {(~keep).sum()} least-divergent, so it is not one "
          f"point")

    print(f"\nthe part that is arithmetic:  sd = sqrt(share) * sd(D | diverge)")
    print(f"  raw sd              mean {sd.mean():.3f}  "
          f"relative spread {100 * sd.std(ddof=1) / sd.mean():4.1f}%")
    print(f"  sd / sqrt(share)    mean {(sd / np.sqrt(sh)).mean():.3f}  "
          f"relative spread "
          f"{100 * (sd / np.sqrt(sh)).std(ddof=1) / (sd / np.sqrt(sh)).mean():4.1f}%")

    print(f"\nthe part that is a finding:  sd(D | diverge) barely moves")
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

    print(f"\nHOW TO SIZE THE NEXT EXPERIMENT")
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
           "cells": cells}
    dest = ROOT / "results" / "pair_sd_model.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
