"""The pre-registered verdict on the shipped configuration.

Does what ``jobs/PREREGISTRATION_combined.md`` says and nothing else.

  PRIMARY. Fixed-effect pool of the two blocks; the estimate and its 95%
  interval, against the CHAINED prediction fixed before any pair was played.

  HOMOGENEITY. Cochran's Q across the two, diagnostic only.

  THE CONTRAST THAT MATTERS. Direct minus chained, standard errors combined in
  quadrature. The chain is refuted if that difference excludes zero.

  THE THREE OUTCOMES, fixed in advance so none can be chosen afterwards:
  agrees (the direct interval overlaps the chained one, and the indirect caveat
  can leave the paper); lower (negative interaction, the chain overstates);
  higher (positive interaction, which earns a replication rather than a
  paragraph).

  WHAT THIS RUN CANNOT DO, also stated in advance: at 2000 pairs against the
  chain's 12000 it cannot make the estimate more precise. It can only make it
  honest. A wider interval here is the design working, not a disappointment.

  AND WHAT IT DOES NOT DECIDE. V04_COMBINED and the website's spec do not
  change on this result. It measures what ships; it does not choose it.

    py scripts4/combined_verdict.py
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

BLOCKS = [f"COMBINED 480+lookahead vs champion block {i}" for i in range(2)]

#: The chained prediction, read from the file that computes it so the two
#: cannot drift apart. The pre-registration fixes this as the thing under test.
CHAIN_FILE = "combined_estimate.json"

#: Per-pair sd the design assumed: the A/A 3.796 rather than the divergence
#: model, deliberately conservative because this arm differs from the champion
#: by TWO knobs and the model was fitted on arms differing by one.
PLANNED_SD = 3.796
PLANNED_MDE = 0.238


def main() -> int:
    cs = cells(BLOCKS)
    print("is the shipped configuration worth what the chain says?")
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
            print(f"\n{label} has no per-pair differentials, so the realised "
                  f"sd cannot be\ncomputed. Refusing to guess it.",
                  file=sys.stderr)
            return 2
        diffs.extend(float(x) for x in d)

    n_tot = len(diffs)
    sd = statistics.stdev(diffs)
    mde = (Z + 0.8416212) * sd / math.sqrt(n_tot)
    share = sum(1 for x in diffs if x != 0.0) / n_tot

    ch = json.loads((ROOT / "results" / CHAIN_FILE).read_text())["chained"]
    c_est, c_se = float(ch["est"]), float(ch["se"])
    c_lo, c_hi = float(ch["lo"]), float(ch["hi"])

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

    print("\nTHE SIZING, checked against what the run actually had")
    print(f"  planned per-pair sd     {PLANNED_SD:.3f}  -> MDE "
          f"{PLANNED_MDE:.3f}")
    print(f"  realised per-pair sd    {sd:.3f}  -> MDE {mde:.3f}")
    print(f"  divergence share        {100 * share:.1f}%")
    if sd < PLANNED_SD * 0.95:
        print(f"  The A/A figure was conservative, as the pre-registration "
              f"said it would be:\n  the realised sd is "
              f"{100 * (1 - sd / PLANNED_SD):.0f}% lower, so this run resolves "
              f"more than it promised.")

    print("\nTHE CONTRAST THAT MATTERS -- direct against chained")
    print(f"  chained, 12000 pairs   {c_est:+.3f} [{c_lo:+.3f}, {c_hi:+.3f}]")
    print(f"  direct,  {n_tot} pairs   {est:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    d = est - c_est
    d_se = math.hypot(se, c_se)
    print(f"  difference             {d:+.3f} +/- {d_se:.3f}  "
          f"({d / d_se:+.1f} SE)")
    refuted = abs(d) - Z * d_se > 0
    overlaps = not (hi < c_lo or lo > c_hi)

    print("\n" + "=" * 70)
    if refuted:
        if d < 0:
            print("VERDICT: the chain OVERSTATES the combination.")
            print(f"The two changes interact negatively. The pre-registration "
                  f"commits the DIRECT\nestimate {est:+.3f} as the headline "
                  f"and the chain as refuted -- not averaged with\nit, and not "
                  f"quietly dropped.")
        else:
            print("VERDICT: the chain UNDERSTATES the combination.")
            print(f"The two changes interact positively, which is the more "
                  f"surprising direction.\nThe pre-registration commits this "
                  f"to a REPLICATION rather than to a paragraph.")
    elif overlaps:
        print("VERDICT: the chain AGREES with the direct measurement.")
        print(f"The direct interval [{lo:+.3f}, {hi:+.3f}] overlaps the "
              f"chained [{c_lo:+.3f}, {c_hi:+.3f}], and the\ndifference "
              f"{d:+.3f} +/- {d_se:.3f} does not resolve. The assumption the "
              f"chain rests on --\nthat each change's effect does not depend "
              f"on the deal population the other was\nmeasured over -- was "
              f"plausible and unmeasured; it is now measured and holds.\nThe "
              f"indirect caveat can leave the paper.")
    else:
        print("VERDICT: NOT RESOLVED EITHER WAY.")
        print(f"The intervals do not overlap but the difference "
              f"{d:+.3f} +/- {d_se:.3f} does not exclude\nzero, which is what "
              f"non-overlapping intervals of unequal width look like when\n"
              f"nothing is established. Reported as unresolved.")
    print(f"\nAt {n_tot} pairs against the chain's 12000, this run was never "
          f"going to make the\nestimate more precise -- the pre-registration "
          f"says so. Its job was to make it\nhonest, and this is the first "
          f"time the configuration the website actually serves\nhas played the "
          f"reference in a single duel.")
    print("=" * 70)

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot,
           "estimate": est, "se": se, "ci": [lo, hi],
           "excludes_zero": bool(excludes),
           "realised_sd": sd, "mde_80": mde, "divergence_share": share,
           "planned_sd": PLANNED_SD, "planned_mde": PLANNED_MDE,
           "chained": {"est": c_est, "se": c_se, "lo": c_lo, "hi": c_hi},
           "contrast_vs_chain": {"delta": d, "se": d_se,
                                 "chain_refuted": bool(refuted),
                                 "intervals_overlap": bool(overlaps)}}
    dest = ROOT / "results" / "combined_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
