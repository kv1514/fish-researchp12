"""Read the bound journal and ask what the two bounds are actually worth.

``scripts4/ii_bound_unsolved.py`` collects, this reads. Splitting them keeps
the collector's fingerprint stable: every change here would otherwise discard
the rows already paid for, and an analysis that costs hours to re-ask is an
analysis nobody re-asks.

THREE QUESTIONS, IN THE ORDER THEY SURVIVE
------------------------------------------
1. *Does the upper bound bind at all?* On wide positions the per-deal
   perfect-information solves fall back to the trivial "both half-suits"
   figure, and a bound of +2 on a quantity that cannot exceed +2 is not a
   bound. Counted, per support band, before anything is concluded from it.

2. *How loose is the lower bound where the truth is known?* Every position the
   collector also solved exactly gives an exact gain and a one-ply gain. Their
   gap is what the one-ply policy fails to capture. If that gap GROWS with
   support, then reading the one-ply figure across the support range is exactly
   as unsafe as extrapolating the slope it was meant to replace -- and saying
   so is the point of measuring it.

3. *What does the one-ply gain do across the range?* It is computable on every
   position, solved or not, which the exact gain is not. That makes it the only
   matched instrument that spans the cap. Its trend is reported with question 2
   attached to it, never on its own.

    py scripts4/ii_bound_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "results" / "ii_bound_journal.jsonl"
BANDS = [(1, 2), (3, 8), (9, 24), (25, 60), (61, 150), (151, 10 ** 9)]


def _stat(v):
    n = len(v)
    if not n:
        return None
    m = sum(v) / n
    var = sum((x - m) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
    return m, (var / n) ** 0.5, n


def _slope(xs, ys):
    """Least squares slope and its t, on the pairs given."""
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    if n <= 2:
        return None
    se = (resid / (n - 2) / sxx) ** 0.5 if resid > 0 else 0.0
    return b, (b / se if se > 0 else float("inf")), n


def main() -> int:
    if not JOURNAL.exists():
        print("no journal; run scripts4/ii_bound_unsolved.py first")
        return 1
    rows = [json.loads(x) for x in JOURNAL.read_text().splitlines() if x.strip()]
    fps = sorted(set(r["solver"] for r in rows))
    if len(fps) > 1:
        # Rows from two fingerprints are two different measurements. Mixing
        # them would average a bound computed under one budget with a bound
        # computed under another and report the result as one number.
        keep = max(fps, key=lambda f: sum(1 for r in rows if r["solver"] == f))
        print(f"journal holds {len(fps)} fingerprints; using {keep} only")
        rows = [r for r in rows if r["solver"] == keep]
    games = sorted(set(r["game"] for r in rows))
    print(f"{len(rows)} positions over {len(games)} games "
          f"({games[0]}-{games[-1]})\n")

    # -- 1. does the upper bound bind? ---------------------------------------
    print("1. Where the upper bound still says something")
    print("   band          n   mean U-C   deals fallen back   binding")
    for lo, hi in BANDS:
        sel = [r for r in rows if lo <= r["support"] <= hi]
        if not sel:
            continue
        u = _stat([r["gain_upper"] for r in sel])
        fb = sum(r["pi_fallbacks"] for r in sel)
        tot = sum(r["support"] for r in sel)
        # "Binding" means the bound is below the trivial one it would have got
        # for free. _upper() is exactly what a fully fallen-back position
        # returns, so a position with every deal fallen back is not bounded by
        # the perfect-information solve at all -- it is bounded by arithmetic.
        bind = sum(1 for r in sel if r["pi_fallbacks"] < r["support"])
        band = f"{lo}-{'inf' if hi > 10 ** 8 else hi}"
        print(f"   {band:<10} {u[2]:>4}   {u[0]:+7.4f}   "
              f"{fb:>6}/{tot:<6} ({100.0*fb/max(1,tot):5.1f}%)   "
              f"{bind}/{len(sel)}")
    allfb = sum(1 for r in rows if r["pi_fallbacks"] >= r["support"])
    print(f"   {allfb}/{len(rows)} positions had EVERY deal fall back, so "
          f"their upper bound is\n   the trivial one and carries no "
          f"information about the champion.\n")

    # -- 2. how loose is the lower bound where truth is known? ---------------
    both = [r for r in rows if r.get("gain_exact") is not None]
    print(f"2. Looseness of the one-ply bound, on the {len(both)} positions "
          f"solved exactly")
    if len(both) < 3:
        print("   too few to say anything. Nothing is concluded from it.\n")
    else:
        gaps = [r["gain_exact"] - r["gain_lower"] for r in both]
        g = _stat(gaps)
        inside = sum(1 for r in both
                     if r["gain_lower"] - 1e-6 <= r["gain_exact"]
                     <= r["gain_upper"] + 1e-6)
        print(f"   control: {inside}/{len(both)} exact values inside their "
              f"own bounds")
        print(f"   exact minus one-ply: mean {g[0]:+.4f} "
              f"(95% CI [{g[0]-1.96*g[1]:+.4f}, {g[0]+1.96*g[1]:+.4f}])")
        tight = sum(1 for x in gaps if abs(x) < 1e-9)
        print(f"   the one-ply policy is already optimal on {tight}/"
              f"{len(both)} of them")
        sl = _slope([r["support"] for r in both], gaps)
        if sl:
            print(f"   gap against support: slope {sl[0]:+.5f} per deal, "
                  f"t = {sl[1]:+.2f}")
            if sl[1] > 2:
                print("   The gap GROWS with support. The one-ply figure is "
                      "therefore not a\n   fixed-offset proxy for the exact "
                      "gain, and reading its trend across\n   the support "
                      "range inherits the same problem as the slope it was\n"
                      "   meant to replace.")
            elif sl[1] < -2:
                print("   The gap SHRINKS with support, so the one-ply figure "
                      "gets tighter\n   exactly where the exact solver stops "
                      "working.")
            else:
                print("   No detectable trend in the gap, on this sample. "
                      "That is weak evidence\n   of a fixed offset, not "
                      "evidence of one.")
        print()

    # -- 3. what does the one-ply gain do across the range? ------------------
    print("3. The one-ply gain across the whole range (computable everywhere)")
    print("   band          n   mean L-C")
    for lo, hi in BANDS:
        sel = [r for r in rows if lo <= r["support"] <= hi]
        if not sel:
            continue
        l = _stat([r["gain_lower"] for r in sel])
        band = f"{lo}-{'inf' if hi > 10 ** 8 else hi}"
        print(f"   {band:<10} {l[2]:>4}   {l[0]:+7.4f}")
    sl = _slope([r["support"] for r in rows],
                [r["gain_lower"] for r in rows])
    if sl:
        print(f"   slope against support: {sl[0]:+.6f} per deal, "
              f"t = {sl[1]:+.2f} over {sl[2]} positions")
    narrow = [r["gain_lower"] for r in rows if r["support"] <= 24]
    wide = [r["gain_lower"] for r in rows if r["support"] > 24]
    sn, sw = _stat(narrow), _stat(wide)
    if sn and sw:
        se = (sn[1] ** 2 + sw[1] ** 2) ** 0.5
        t = (sw[0] - sn[0]) / se if se > 0 else 0.0
        print(f"   at or below the study's cap: {sn[0]:+.4f} (n={sn[2]}); "
              f"above it: {sw[0]:+.4f} (n={sw[2]}); Welch t = {t:+.2f}")

    out = ROOT / "results" / "ii_bound_analysis.json"
    out.write_text(json.dumps({
        "n": len(rows), "games": games,
        "positions_with_trivial_upper": allfb,
        "n_exact": len(both),
        # The count the paper bolds. Stored so the manifest can watch it: a
        # bolded number with nothing behind it is what tests4 rejects, and it
        # is right to -- "88 of 100" is the whole claim that the exploitation
        # is one move.
        "oneply_already_optimal": sum(
            1 for r in both
            if abs(r["gain_exact"] - r["gain_lower"]) < 1e-9),
        "mean_gap_exact_minus_oneply": (_stat(
            [r["gain_exact"] - r["gain_lower"] for r in both])[0]
            if len(both) >= 3 else None),
        "oneply_narrow_mean": sn[0] if sn else None,
        "oneply_wide_mean": sw[0] if sw else None,
        "oneply_slope": sl[0] if sl else None,
        "oneply_slope_t": sl[1] if sl else None,
    }, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
