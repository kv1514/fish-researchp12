"""Does the rollout target's slope depend on how far into the deal we are?

``results/rollout_target.json`` measures a slope of +0.681 with the engine
finishing every rollout, on positions with at least four half-suits resolved.
The objective-learning line does not run on those positions: its harvest spans
the whole deal, median two resolved and only 29% at four or more. If the slope
climbs steeply with resolution, then a number measured at four-plus says little
about the target the fit will actually see, and the re-opened line is heading
for the same flat target that stopped it the first time -- which is worth
knowing before a ten-hour rollout pass, not after.

The positions are recoverable: ``harvest`` is deterministic given its seeds, so
replaying it in the same order recovers the resolved count for each position
index in the stored rows. Nothing is re-rolled out.

Usage: python scripts4/slope_by_resolution.py [source.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from rollout_target import centred_slope                       # noqa: E402

from ask_regret import harvest                                 # noqa: E402


def main(argv):
    src = Path(argv[0]) if argv else ROOT / "results" / "rollout_target.json"
    d = json.loads(src.read_text())
    rows = d["rows"]
    n_pos, min_res = d["n_positions"], d["min_resolved"]

    print("does the slope depend on how far into the deal the position is?\n")
    print(f"source {src.name}   continuation "
          f"{d.get('continuation', 'v04')}   >= {min_res} resolved\n")

    # Replay the harvest to recover each position index's resolved count.
    positions = harvest(80, min_res, n_pos)
    resolved = {i: sum(1 for w in sw if w is not None)
                for i, (_, _, sw, _, _, _) in enumerate(positions)}

    counts = sorted({resolved[r["position"]] for r in rows
                     if r["position"] in resolved})
    print(f"{'resolved':>9}{'slope':>10}{'se':>9}{'asks':>7}{'pos':>6}")
    pts = []
    for c in counts:
        sub = [r for r in rows if resolved.get(r["position"]) == c]
        s = centred_slope(sub)
        if s is None or s["n_positions"] < 3:
            continue
        pts.append((c, s["slope"], s["se_clustered"], s["n_positions"]))
        print(f"{c:>9}{s['slope']:>+10.4f}{s['se_clustered']:>9.4f}"
              f"{s['n_points']:>7}{s['n_positions']:>6}")

    if len(pts) < 3:
        print("\ntoo few distinct resolution levels to say anything")
        return

    x = np.array([p[0] for p in pts], dtype=float)
    y = np.array([p[1] for p in pts])
    w = 1.0 / np.array([p[2] for p in pts]) ** 2
    A = np.column_stack([np.ones(x.size), x])
    W = np.diag(w)
    beta = np.linalg.solve(A.T @ W @ A, A.T @ W @ y)
    cov = np.linalg.inv(A.T @ W @ A)
    trend, trend_se = float(beta[1]), float(np.sqrt(cov[1, 1]))
    print(f"\ntrend in slope per extra resolved half-suit  "
          f"{trend:+.4f} +/- {trend_se:.4f}  ({trend / trend_se:+.1f} SE)")

    target = 2.0          # the learning harvest's median
    pred = float(beta[0] + beta[1] * target)
    print(f"extrapolated to {target:.0f} resolved (the learning harvest's "
          f"median): {pred:+.3f}")
    print("  An extrapolation outside the measured range, and labelled as one.")

    print()
    if trend - 1.96 * trend_se > 0:
        print("The slope climbs with resolution, so +0.681 is a late-position")
        print("number and the learning harvest will see less signal than that.")
        print("How much less is what the re-run measures; this only says the")
        print("headline should not be read as the target the fit will get.")
    elif trend + 1.96 * trend_se < 0:
        print("The slope FALLS with resolution, so if anything the learning")
        print("harvest's earlier positions carry more signal, not less.")
    else:
        print("No detectable trend across the range measured. That is not")
        print("evidence the slope is flat all the way down to two resolved --")
        print("the range here is narrow and the per-level intervals are wide --")
        print("but it is no reason to expect a collapse either.")

    # The headline the paper makes is a DIFFERENCE between continuations at the
    # same positions, not a level. Heterogeneity in the level says nothing about
    # it, so the difference is binned the same way -- and because both arms
    # scored identical asks at identical positions, the difference of the two
    # within-slopes is the within-slope of the differenced outcome.
    pub = ROOT / "results" / "rollout_target_public.json"
    paired = []
    if pub.exists() and d.get("continuation", "v04") == "v04":
        b = json.loads(pub.read_text())["rows"]
        assert len(b) == len(rows)
        diff_rows = [{"position": ra["position"], "p_success": ra["p_success"],
                      "q": ra["q"] - rb["q"]}
                     for ra, rb in zip(rows, b)]
        print(f"\nthe engine MINUS the heuristic, at the same positions")
        print(f"{'resolved':>9}{'delta':>10}{'se':>9}{'pos':>6}")
        for c in counts:
            sub = [r for r in diff_rows if resolved.get(r["position"]) == c]
            sdd = centred_slope(sub)
            if sdd is None or sdd["n_positions"] < 3:
                continue
            paired.append({"resolved": c, "delta": sdd["slope"],
                           "se": sdd["se_clustered"],
                           "positions": sdd["n_positions"]})
            print(f"{c:>9}{sdd['slope']:>+10.4f}{sdd['se_clustered']:>9.4f}"
                  f"{sdd['n_positions']:>6}")
        pos_lv = sum(1 for q in paired if q["delta"] - 1.96 * q["se"] > 0)
        print(f"  levels where the engine is ahead by more than noise: "
              f"{pos_lv} of {len(paired)}")
        print("  The paper's claim is this table, not the one above it: a level")
        print("  that happens to be flat for both continuations says nothing")
        print("  about whether the continuation matters there.")

    out = {"source": str(src), "paired_by_level": paired, "levels": [
        {"resolved": c, "slope": s, "se": e, "positions": n}
        for c, s, e, n in pts],
        "trend_per_resolved": trend, "trend_se": trend_se,
        "extrapolated_at_2": pred}
    dest = ROOT / "results" / "slope_by_resolution.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
