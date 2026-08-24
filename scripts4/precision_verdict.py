"""The pre-registered verdict on buying posterior precision.

Does what ``jobs/PREREGISTRATION_precision.md`` says and nothing else. Same
shape as ``scripts4/settle_verdict.py``, and for the same reason: the analysis
was fixed before the blocks existed, so it cannot be a choice about the numbers.

  PRIMARY, and the only thing that decides. Fixed-effect pool of the six
  blocks. Every block is unselected, so none may be dropped for its result.
  Demonstrated if and only if the 95% interval excludes zero.

  HOMOGENEITY. Cochran's Q across the six, diagnostic only.

  CONTEXT, not decisive. The two screening cells, explicitly labelled as
  screens. The pre-registration was written before either had a number and was
  sized against a threshold, so neither contributes to the design or the
  verdict.

  THE DEFAULT IS A SEPARATE DECISION. The pre-registration commits to this in
  advance: ``n_draws`` trades playing strength against inference latency, and
  the public table has a request budget. This script therefore prints the
  measured cost next to the measured effect and stops there. It does not change
  a default and there is no code path here that could.

    py scripts4/precision_verdict.py [rung]     # rung 1 (default) or 2
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

#: The two rungs, each with the design its own pre-registration fixed BEFORE it
#: ran. jobs/PREREGISTRATION_precision2.md says this script is reused unchanged
#: for the second rung; it could not be, because the labels were hard-coded --
#: a promise made in a document that the code could not keep. Both rungs are
#: parameterised here instead, and neither one's constants may be edited after
#: its data exists.
RUNGS = {
    "1": {
        "title": "is posterior precision worth buying? (160 -> 480 draws)",
        "blocks": [f"PRECISION n_draws 480 vs 160 block {i}" for i in range(6)],
        "screens": ["SCREEN precision half n_draws 80 vs 160",
                    "SCREEN precision triple n_draws 480 vs 160"],
        "min_interesting": 0.15,
        "per_pair_sd": 3.796,          # the A/A figure this rung was sized on
        "prereg_mde": 0.137,
        "prereg": "jobs/PREREGISTRATION_precision.md",
        "previous": None,
    },
    "2": {
        "title": "does precision keep paying past 480 draws? (480 -> 1440)",
        "blocks": [f"PRECISION2 n_draws 1440 vs 480 block {i}" for i in range(6)],
        "screens": [],
        "min_interesting": 0.15,
        # NOT the A/A figure: the measured mean of the six 480-vs-160 blocks,
        # which is the same contrast one rung down. Re-checked after the
        # standard-error recovery in pool_cells was corrected from a normal
        # critical to the t the harness actually uses -- that moved the mean by
        # -0.0004 and left the MDE at 0.1374 either way, so the pre-registered
        # constant stands and needs no amendment.
        "per_pair_sd": 3.799,
        "prereg_mde": 0.137,
        "prereg": "jobs/PREREGISTRATION_precision2.md",
        # Reported, not decisive: equal steps support a response linear in
        # log(draws); a smaller one is diminishing returns.
        "previous": ("the first rung, 160 -> 480", 0.340),
    },
}

LATENCY = ROOT / "results" / "precision_cost.json"


def _line(c):
    return (f"  block {c['label'][-1]}  n={c['n']:>5}  {c['est']:>+7.3f} "
            f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    which = argv[0] if argv else "1"
    if which not in RUNGS:
        print(f"unknown rung {which!r}; choose from {sorted(RUNGS)}")
        return 2
    cfg = RUNGS[which]
    BLOCKS = cfg["blocks"]
    SCREENS = cfg["screens"]
    MIN_INTERESTING = cfg["min_interesting"]
    PER_PAIR_SD = cfg["per_pair_sd"]
    PREREG_MDE = cfg["prereg_mde"]

    cs = cells(BLOCKS)
    print(cfg["title"])
    print(f"design fixed in {cfg['prereg']}")
    print(f"\nblocks recorded: {len(cs)}/6")
    for c in cs:
        print(_line(c))
    if len(cs) < 6:
        print("\nNot all six blocks are in, so there is no verdict to print. "
              "Looking at a\npartial pool of a pre-registered run and then "
              "deciding whether to continue\nis exactly what pre-registering "
              "was for. Re-run when they land.")
        return 1

    n_tot = sum(c["n"] for c in cs)
    half = Z * PER_PAIR_SD / math.sqrt(n_tot)
    mde = (Z + 0.8416212) * PER_PAIR_SD / math.sqrt(n_tot)
    print(f"\ntotal pairs {n_tot}")
    print(f"  MDE at 80% power        {mde:.3f}  "
          f"(pre-registered as {PREREG_MDE:.3f})")
    print(f"  95% interval half-width {half:.3f}")
    print(f"  minimum interesting effect, fixed in advance  "
          f"{MIN_INTERESTING:+.3f}")

    p = pool(cs)
    est, se = p["fe"], p["fe_se"]
    lo, hi = est - Z * se, est + Z * se
    demonstrated = lo > 0 or hi < 0
    print("\nPRIMARY -- fixed-effect pool of the six blocks")
    print(f"  {est:+.4f}  95% [{lo:+.4f}, {hi:+.4f}]   "
          f"{'EXCLUDES ZERO' if demonstrated else 'INCLUDES ZERO'}")

    print("\nhomogeneity across the six (diagnostic only)")
    print(f"  Cochran Q  {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2        {100 * p['i2']:.1f}%")
    print(f"  tau        {p['tau']:.4f} sets per pair")

    sc = cells(SCREENS)
    if sc:
        print("\nSCREENS -- context only, contributed nothing to the design")
        for c in sc:
            print(f"  {c['label']:<44} n={c['n']:>4} {c['est']:>+7.3f} "
                  f"[{c['lo']:+.3f}, {c['hi']:+.3f}]")
        trip = [c for c in sc if "triple" in c["label"]]
        if trip and demonstrated:
            d = est - trip[0]["est"]
            print(f"\n  The 400-pair screen of this same cell read "
                  f"{trip[0]['est']:+.3f}; the pre-registered\n"
                  f"  run reads {est:+.3f}, {d:+.3f} higher. The screen did "
                  f"not inflate this one --\n  which is what an unselected "
                  f"screen looks like, and is only worth saying\n  because the "
                  f"selected ones in this project inflated every time.")

    prev = cfg.get("previous")
    if prev and demonstrated:
        name, val = prev
        d = est - val
        print(f"\nAGAINST {name.upper()} -- reported, not decisive")
        print(f"  that rung {val:+.3f}, this rung {est:+.3f}, "
              f"difference {d:+.3f}")
        if hi < val:
            print("  This rung's whole interval sits below, so the response is")
            print("  flattening: equal ratios of draws are not worth equal "
                  "amounts.")
        elif lo > val:
            print("  This rung is worth MORE than the last, which no model of")
            print("  diminishing returns predicts and is worth looking at.")
        else:
            print("  The intervals overlap, so a response linear in "
                  "log(draws) is")
            print("  consistent with both. Two points cannot say more than "
                  "that.")

    print("\n" + "=" * 70)
    if demonstrated:
        print("VERDICT: the effect is DEMONSTRATED by the pre-registered test.")
        if lo > MIN_INTERESTING:
            print(f"The whole interval clears the {MIN_INTERESTING:+.2f} "
                  f"threshold set in advance, so the")
            print("effect is not merely real, it is large enough to have been "
                  "worth finding.")
        else:
            print(f"The interval excludes zero but reaches below the "
                  f"{MIN_INTERESTING:+.2f} threshold set in")
            print("advance, so the effect is real and may still be too small "
                  "to be worth its price.")
    else:
        print("VERDICT: NOT DEMONSTRATED.")
        print("Reported that way whatever the screens said, with no further "
              "run added to\nchase significance.")
    print("=" * 70)

    print("\nTHE DEFAULT")
    if LATENCY.exists():
        cost = json.loads(LATENCY.read_text())
        b = cost["per_decision_ms"]
        print(f"  inference per decision   {b['160']:.1f} ms at 160 draws, "
              f"{b['480']:.1f} ms at 480")
        print(f"  ratio                    {b['480'] / b['160']:.2f}x")
        print(f"  measured on {cost['n_decisions']} decisions "
              f"({cost['host']})")
    else:
        print("  Cost not measured yet -- run scripts4/precision_cost.py.")
    print("  Whether to move the default is a separate decision from whether "
          "the effect\n  is real, and the pre-registration says so. This "
          "script does not make it.")

    out = {"rung": which, "blocks": cs, "pooled": p, "n_pairs": n_tot,
           "mde_80": mde, "half_width": half,
           "min_interesting": MIN_INTERESTING,
           "demonstrated": bool(demonstrated),
           "screens": sc}
    dest = (ROOT / "results" / "precision_verdict.json" if which == "1"
            else ROOT / "results" / f"precision{which}_verdict.json")
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
