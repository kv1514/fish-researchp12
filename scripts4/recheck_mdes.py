"""Does using each cell's own noise change any verdict already reported?

The nulls table quotes, for every cell, the smallest effect that cell could have
resolved at 80% power, computed from a single per-pair standard deviation of
3.869 sets. ``results/pair_sd_model.json`` shows that figure is a property of a
pair of maximally-different policies rather than of the game, and that cells
whose arms rarely diverge are quieter --- as low as 2.33.

That correction is conservative in direction: the constant over-states the noise,
so every published interval is at least as wide as it should be. But
``conservative'' is a claim about direction and says nothing about size, and the
question that matters is whether any cell reported as an uninformative null was
in fact resolvable. That is checkable, so it is checked here rather than argued.

TWO CRITERIA, and the first version of this script used only the stricter one.
``|est| > MDE`` is a test at alpha ~ 0.005, because ``MDE = 2.8016 * se`` and
2.8016 is ``z_{0.975} + z_{0.80}``. Everywhere else this project defines a cell
as having resolved something when its **95% interval excludes zero**, which is
``|est| > 1.96 * se`` -- that is what both verdict scripts say and what the duel
harness prints. Checking revisions against a bar 43% higher than the project's
own definition made "no verdict changes" nearly automatic, and it was: the band
between the two MDEs is a median 8% of the MDE wide.

Both are reported below. The second is the one that matters, and it changes
several cells.

Only cells that stored their per-pair differentials can be re-examined; the
earlier ones recorded a mean and an interval only, and no re-derivation can
recover what was not written down. That limit is reported rather than hidden.

Usage: python scripts4/recheck_mdes.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

Z = 1.959964
Z_BETA = 0.8416212
#: The single figure the nulls table's MDE column was computed from. The
#: lookahead pre-registration later replaced it with 3.796 measured over 4800
#: A/A pairs, but the table in the paper was built with this one, so this is the
#: number a recheck of that table has to start from.
CONSTANT_SD = 3.869
#: The project's own definition of "this cell resolved something".
Z95 = 1.959964


def mde(sd: float, n: int) -> float:
    return (Z + Z_BETA) * sd / np.sqrt(n)


def main():
    rows = [json.loads(l) for l in
            (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines()
            if l.strip()]
    total = len(rows)
    cells = []
    for r in rows:
        d = r.get("diffs")
        if not d:
            continue
        a = np.array(d, dtype=float)
        own = float(a.std(ddof=1))
        ci = r.get("diff_ci") or [float("nan"), float("nan")]
        cells.append({
            "label": r["label"], "n": int(a.size), "sd": own,
            "est": float(a.mean()), "se": float(own / np.sqrt(a.size)),
            # The interval the harness recorded, built with a t critical on
            # n-1 df. Used as-is rather than reconstructed: the question is
            # what this cell REPORTED, and reconstructing it with a normal
            # critical would answer a slightly different one.
            "lo": float(ci[0]), "hi": float(ci[1]),
            "mde_constant": float(mde(CONSTANT_SD, a.size)),
            "mde_own": float(mde(own, a.size)),
        })
    if not cells:
        print("no cell stores its per-pair differentials")
        return

    ratio = np.array([c["mde_own"] / c["mde_constant"] for c in cells])
    print("does each cell's own noise change what it could resolve?\n")
    print(f"cells recorded            {total}")
    print(f"cells with per-pair data  {len(cells)}  "
          f"(the rest predate storing it and cannot be re-examined)")
    print(f"\nMDE ratio, own over constant:  median {np.median(ratio):.2f}   "
          f"range [{ratio.min():.2f}, {ratio.max():.2f}]")
    print(f"  The constant over-states the resolvable effect by up to "
          f"{100 * (1 - ratio.min()):.0f}% in the\n  quietest cell and never "
          f"under-states it by more than "
          f"{100 * (ratio.max() - 1):.0f}%.")

    flipped = [c for c in cells
               if abs(c["est"]) < c["mde_constant"]
               and abs(c["est"]) > c["mde_own"]]
    print(f"\nunder the strict bar (|est| > MDE, alpha ~ 0.005): "
          f"{len(flipped)} change")
    for c in flipped:
        print(f"  {c['label'][:52]:<52} est {c['est']:+.3f}   "
              f"MDE {c['mde_constant']:.3f} -> {c['mde_own']:.3f}")
    if not flipped:
        print("  None -- and the band between the two MDEs is a median "
              f"{100 * (1 - np.median(ratio)):.0f}% of the\n  MDE wide, so "
              "that was close to guaranteed. This is the check being vacuous,\n"
              "  not the correction being harmless.")

    # The criterion the rest of the project actually uses.
    resolved = [c for c in cells if c["lo"] > 0 or c["hi"] < 0]
    called_null = [c for c in cells if abs(c["est"]) < c["mde_constant"]]
    both = [c for c in resolved if abs(c["est"]) < c["mde_constant"]]
    print(f"\nunder the project's own bar (95% interval excludes zero): "
          f"{len(both)} change")
    for c in sorted(both, key=lambda c: -abs(c["est"])):
        print(f"  {c['label'][:46]:<46} {c['est']:>+7.3f} "
              f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
    print(f"\n  {len(called_null)} cells sit below the MDE the nulls table "
          f"quotes for them, and {len(both)} of\n  those have intervals that "
          f"exclude zero. The table's MDE column is a\n  statement about what "
          f"the cell could DETECT at 80% power, which is a\n  different and "
          f"stricter thing than what it did resolve -- and reading the\n  "
          f"column as 'this cell found nothing' understates several cells. One "
          f"of\n  them, the retake penalty at -0.340, is treated as an "
          f"established effect by\n  jobs/PREREGISTRATION_retake_gate.md, "
          f"which is the contradiction that made\n  this worth re-checking.")

    cells.sort(key=lambda c: c["mde_own"] / c["mde_constant"])
    print(f"\n{'cell':<46}{'n':>6}{'sd':>7}{'MDE con':>9}{'MDE own':>9}"
          f"{'est':>8}")
    for c in cells[:6] + cells[-3:]:
        print(f"{c['label'][:46]:<46}{c['n']:>6}{c['sd']:>7.2f}"
              f"{c['mde_constant']:>9.3f}{c['mde_own']:>9.3f}{c['est']:>+8.3f}")

    out = {"constant_sd": CONSTANT_SD, "cells_recorded": total,
           "cells_with_pair_data": len(cells),
           "ratio_median": float(np.median(ratio)),
           "ratio_min": float(ratio.min()), "ratio_max": float(ratio.max()),
           "verdicts_changed_strict": len(flipped),
           "verdicts_changed_project_bar": len(both),
           "changed_strict": flipped,
           "changed_project_bar": [c["label"] for c in both],
           "cells": cells}
    dest = ROOT / "results" / "mde_recheck.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
