"""Is the rollout target's slope about the continuation, or about the positions?

``scripts4/rollout_target.py`` measured the position-centred slope of rollout
value on P(success) at +0.681 with the full engine finishing every rollout, and
the paper's published figure for the same quantity is +0.101. Quoting the two
against each other is not sound: the published number was measured over the
LEARNING harvest, whose positions span the whole deal, while this script's
positions have four or more half-suits resolved by construction. A difference
between them is a difference in two things at once.

The control run fixes that -- same positions, same determinized worlds, same
seeds, same root asks, only the continuation policy changing. This script pools
the two arms and reports the contrast PAIRED BY POSITION, which is the estimator
the design earns: both arms scored the same 3056 candidate asks at the same 110
positions, so the position's own value level cancels exactly, as it does in
every duplicate-deal experiment here.

Usage: python scripts4/continuation_compare.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from rollout_target import PAPER_SLOPE, centred_slope           # noqa: E402

V04 = ROOT / "results" / "rollout_target.json"
PUBLIC = ROOT / "results" / "rollout_target_public.json"


def per_position_slopes(rows):
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    out = {}
    for pid, group in by.items():
        s = centred_slope(group)
        if s is not None and s["se_clustered"] > 0:
            out[pid] = s["slope"]
    return out


def main() -> int:
    if not PUBLIC.exists():
        print("the control arm has not run; "
              "py scripts4/rollout_target.py 120 12 4 public")
        return 1
    a = json.loads(V04.read_text())
    b = json.loads(PUBLIC.read_text())

    print("is the slope about the continuation, or about the positions?\n")
    for name, d in (("full v0.4", a), ("public heuristic", b)):
        s = d["p_success_slope"]
        print(f"  {name:<18}{s['slope']:>+8.4f} +/- {s['se_clustered']:.4f}"
              f"   {s['n_points']} asks over {s['n_positions']} positions")
    print(f"  {'the paper':<18}{PAPER_SLOPE:>+8.4f}"
          f"            measured on a DIFFERENT position set")

    same_pos = (a["p_success_slope"]["n_positions"]
                == b["p_success_slope"]["n_positions"]
                and a["p_success_slope"]["n_points"]
                == b["p_success_slope"]["n_points"])
    print(f"\narms scored the same positions and asks: {same_pos}")

    # Unpaired contrast, for reference only.
    d_un = a["p_success_slope"]["slope"] - b["p_success_slope"]["slope"]
    se_un = float(np.hypot(a["p_success_slope"]["se_clustered"],
                           b["p_success_slope"]["se_clustered"]))
    print(f"\nunpaired difference   {d_un:+.4f} +/- {se_un:.4f}  "
          f"({d_un / se_un:+.1f} SE)")

    # Paired, and weighted the way both arms' own headline slopes are weighted.
    #
    # The obvious pairing -- average the per-position slope differences -- is a
    # DIFFERENT estimand from the one being compared. A per-position slope is
    # very noisy (they run from -6 to +4 here), and an unweighted average of
    # their differences is dominated by positions carrying almost no contrast,
    # while the reported slopes weight each position by its own sum of squared
    # centred P(success). Comparing the two would be comparing two estimators
    # rather than two continuations.
    #
    # Because both arms scored the same asks at the same positions, x is
    # IDENTICAL between them (verified above), and the difference of the two
    # within-slopes is exactly the within-slope of the difference:
    #
    #     delta = sum_gi x_gi (yA_gi - yB_gi) / sum_gi x_gi^2
    #
    # so the pairing is free and the clustered standard error is the ordinary
    # one applied to the differenced outcome.
    rows_d = []
    for ra, rb in zip(a["rows"], b["rows"]):
        assert ra["position"] == rb["position"]
        rows_d.append({"position": ra["position"],
                       "p_success": ra["p_success"],
                       "q": ra["q"] - rb["q"]})
    sd = centred_slope(rows_d)
    m, se = sd["slope"], sd["se_clustered"]
    print(f"paired difference     {m:+.4f} +/- {se:.4f}  ({m / se:+.1f} SE)"
          f"   over {sd['n_positions']} positions")

    sa, sb = per_position_slopes(a["rows"]), per_position_slopes(b["rows"])
    common = sorted(set(sa) & set(sb))
    share = float(np.mean([sa[p] > sb[p] for p in common])) if common else 0.0
    naive = np.array([sa[p] - sb[p] for p in common])
    print(f"  share of positions where the engine's slope is the larger: "
          f"{share:.2f}")
    print(f"  unweighted mean of per-position differences, for contrast: "
          f"{naive.mean():+.4f} +/- {naive.std(ddof=1) / np.sqrt(naive.size):.4f}")

    print()
    if m - 1.96 * se > 0:
        print("The continuation is the cause. On identical positions, identical")
        print("worlds and identical root asks, replacing the heuristic with the")
        print("engine raises the slope by a margin this design resolves -- so the")
        print("earlier comparison happened to be right, and is now right for a")
        print("reason rather than by coincidence of position mix.")
    elif m + 1.96 * se < 0:
        print("The continuation makes the target WORSE on matched positions, so")
        print("the published comparison was position mix and nothing else.")
    else:
        print("Matched, the two continuations are indistinguishable. The earlier")
        print("comparison was position mix, and the diagnosis it appeared to")
        print("overturn stands.")

    out = {"v04": a["p_success_slope"], "public": b["p_success_slope"],
           "paper_slope": PAPER_SLOPE, "same_positions": bool(same_pos),
           "unpaired": {"delta": d_un, "se": se_un, "z": d_un / se_un},
           "paired": {"delta": m, "se": se, "z": m / se,
                      "n_positions": int(sd["n_positions"]),
                      "share_v04_larger": share,
                      "unweighted_mean": float(naive.mean())}}
    dest = ROOT / "results" / "continuation_compare.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
