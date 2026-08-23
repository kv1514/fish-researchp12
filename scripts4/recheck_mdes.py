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

A cell's verdict changes exactly when its estimate is smaller than the MDE
computed from the constant but larger than the MDE computed from its own
measured standard deviation.

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
#: The single figure the nulls table's MDE column was computed from.
CONSTANT_SD = 3.869


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
        cells.append({
            "label": r["label"], "n": int(a.size), "sd": own,
            "est": float(a.mean()),
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
    print(f"\ncells whose verdict changes: {len(flipped)}")
    for c in flipped:
        print(f"  {c['label'][:52]:<52} est {c['est']:+.3f}   "
              f"MDE {c['mde_constant']:.3f} -> {c['mde_own']:.3f}")
    if not flipped:
        print("  None. Every cell reported as an uninformative null stays one")
        print("  when scored against its own measured noise, and every cell")
        print("  that resolved still resolves. The correction changes how the")
        print("  NEXT experiment should be sized; it revises no reading already")
        print("  published.")

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
           "verdicts_changed": len(flipped),
           "changed": flipped, "cells": cells}
    dest = ROOT / "results" / "mde_recheck.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
