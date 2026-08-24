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
#: The third arm. The two above differ in TWO things, not one: the engine
#: finishes the game and is handed the real public log, while the heuristic
#: finishes the game and starts blind to every card the table has watched
#: change hands. Reading the whole contrast as "the continuation policy" is the
#: two-factor error this experiment exists to avoid, one level further in. This
#: arm is the heuristic WITH the log, so information is held fixed and only the
#: policy moves.
PUBLIC_SEEDED = ROOT / "results" / "rollout_target_public-seeded.json"


def per_position_slopes(rows):
    """Each position's own within-slope, with NO filter on its standard error.

    The filter that used to sit here -- keep a position only if its clustered
    standard error is positive -- looked like ordinary defensive coding and was
    a bug. Within one cluster the CR0 numerator is (x . e)^2, and x . e is the
    OLS normal equation, so it is EXACTLY ZERO in exact arithmetic. The filter
    therefore kept only the positions where floating-point roundoff happened to
    leave a nonzero residual dot product: 97 of 110 here, chosen by nothing.

    It mattered, and in the flattering direction. Dropping those 13 removed the
    largest outlier -- one position with four scored asks and a slope difference
    of -21.7 -- and turned an unweighted mean of +0.020 into +0.194, which made
    the weighted and unweighted estimators look far closer than they are.
    """
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    out = {}
    for pid, group in by.items():
        s = centred_slope(group)
        if s is not None:
            out[pid] = s["slope"]
    return out


def paired_slope(a_rows, b_rows):
    """Within-slope of (A - B), which IS the difference of the two within-slopes.

    Both arms scored the same asks at the same positions, so x is bit-identical
    between them and the pairing is exact rather than approximate.
    """
    rows_d = []
    for ra, rb in zip(a_rows, b_rows):
        assert ra["position"] == rb["position"]
        rows_d.append({"position": ra["position"],
                       "p_success": ra["p_success"],
                       "q": ra["q"] - rb["q"]})
    return centred_slope(rows_d)


def main() -> int:
    if not PUBLIC.exists():
        print("the control arm has not run; "
              "py scripts4/rollout_target.py 120 12 4 public")
        return 1
    a = json.loads(V04.read_text())
    b = json.loads(PUBLIC.read_text())

    print("is the slope about the continuation, or about the positions?\n")
    c = (json.loads(PUBLIC_SEEDED.read_text())
         if PUBLIC_SEEDED.exists() else None)
    arms = [("full v0.4", a), ("public heuristic", b)]
    if c is not None:
        arms.append(("public + real log", c))
    for name, d in arms:
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
    sd = paired_slope(a["rows"], b["rows"])
    m, se = sd["slope"], sd["se_clustered"]
    print(f"paired difference     {m:+.4f} +/- {se:.4f}  ({m / se:+.1f} SE)"
          f"   over {sd['n_positions']} positions")

    sa, sb = per_position_slopes(a["rows"]), per_position_slopes(b["rows"])
    common = sorted(set(sa) & set(sb))
    share = float(np.mean([sa[p] > sb[p] for p in common])) if common else 0.0
    naive = np.array([sa[p] - sb[p] for p in common])
    print(f"  positions with a per-position slope on both arms: {len(common)}")
    print(f"  share where the engine's slope is the larger: {share:.2f}")
    print(f"  median per-position difference: {np.median(naive):+.4f}")
    print(f"  unweighted MEAN, for contrast: {naive.mean():+.4f} "
          f"+/- {naive.std(ddof=1) / np.sqrt(naive.size):.4f}")
    print("  The mean is the wrong summary and is printed to show how wrong: a")
    print("  single position with four scored asks contributes a slope")
    print(f"  difference of {naive.min():+.1f}, because a slope fitted to four")
    print("  points is not an estimate of anything. The median and the share")
    print("  are the robust statements; the weighted estimate above is the one")
    print("  the design earns.")

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

    decomp = None
    if c is not None:
        pol = paired_slope(a["rows"], c["rows"])        # policy alone
        info = paired_slope(c["rows"], b["rows"])       # information alone
        print("\nDECOMPOSITION -- what the two arms above were changing at once")
        print(f"  policy alone   (v04 vs public+log)   "
              f"{pol['slope']:+.4f} +/- {pol['se_clustered']:.4f}  "
              f"({pol['slope'] / pol['se_clustered']:+.1f} SE)")
        print(f"  the log alone  (public+log vs public){info['slope']:+.4f} "
              f"+/- {info['se_clustered']:.4f}  "
              f"({info['slope'] / info['se_clustered']:+.1f} SE)")
        print(f"  the two sum to {pol['slope'] + info['slope']:+.4f} against "
              f"the combined {m:+.4f} (exact: both are\n  within-slopes of "
              f"differences on the same x, so they add)")
        share = abs(info["slope"]) / abs(m) if m else 0.0
        print()
        if abs(info["slope"]) > 1.96 * info["se_clustered"]:
            print(f"  Handing the weak policy the same public log moves the "
                  f"target on its own,\n  by {share:.0%} of the combined "
                  f"contrast. That much of the +0.641 is information\n  "
                  f"rather than continuation, and the paper must say so.")
        else:
            print(f"  Handing the weak policy the same public log does not move "
                  f"the target\n  ({info['slope']:+.4f} +/- "
                  f"{info['se_clustered']:.4f}). The information asymmetry was "
                  f"real and is not\n  what the contrast measures: it is the "
                  f"policy, as published.")
        decomp = {"policy_only": {"delta": pol["slope"],
                                  "se": pol["se_clustered"]},
                  "log_only": {"delta": info["slope"],
                               "se": info["se_clustered"]},
                  "log_share_of_combined": share}

    out = {"v04": a["p_success_slope"], "public": b["p_success_slope"],
           "public_seeded": (c["p_success_slope"] if c else None),
           "decomposition": decomp,
           "paper_slope": PAPER_SLOPE, "same_positions": bool(same_pos),
           "unpaired": {"delta": d_un, "se": se_un, "z": d_un / se_un},
           "paired": {"delta": m, "se": se, "z": m / se,
                      "n_positions": int(sd["n_positions"]),
                      "share_v04_larger": share,
                      "n_positions_both_arms": len(common),
                      "median_per_position": float(np.median(naive)),
                      "unweighted_mean": float(naive.mean()),
                      "worst_per_position": float(naive.min())}}
    dest = ROOT / "results" / "continuation_compare.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
