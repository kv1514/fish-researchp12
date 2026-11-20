"""The pre-registered verdict on the learned ask weights.

Does what ``jobs/PREREGISTRATION_learned_weights.md`` says and nothing else.

  PRIMARY. Fixed-effect pool of the two blocks. Demonstrated BETTER if and only
  if the 95% interval lies entirely above zero; demonstrated WORSE if entirely
  below.

  AND AN INTERVAL CONTAINING ZERO IS NOT A NULL HERE. The pre-registration
  states, in advance, that 2000 pairs gives an MDE of 0.238 against a minimum
  interesting effect of 0.15 -- so this design cannot separate a small positive
  from zero, and says so before the data rather than after. What it CAN resolve
  is a repeat of the previous catastrophe: v0.4's learned weights lost by
  -2.183, which at this size would be nine standard errors. So a zero-crossing
  interval is reported as UNRESOLVED AT THIS SIZE, never as a null, and this
  script refuses to print the other sentence.

  HOMOGENEITY. Cochran's Q across the two, diagnostic only.

  REPORTED ALONGSIDE, NOT DECISIVE. v0.4's -2.183, labelled as the different
  experiment it was -- different target, different baseline, different fit --
  and the fitted vector beside the incumbent so a reader can see which terms
  moved.

  THE TERM THAT WAS NOT FITTED. `claim`'s formula changed after the harvest, so
  its column was zeroed rather than trusted. A reported weight of exactly 0.0
  for it is not a measurement, and this script says so rather than letting the
  zero pass as a finding.

  WHAT A POSITIVE DOES NOT DO. It does not move a default. The pre-registration
  commits it to a replication on fresh seeds first, because this line has
  already produced one confidently-argued result that did not survive a control.

    py scripts4/learned_weights_verdict.py
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

BLOCKS = [f"LEARNED WEIGHTS v2 vs champion block {i}" for i in range(2)]

#: v0.4's own attempt: the best of three variants over 120 pairs, against
#: fishbot4() defaults rather than the champion, on the weak continuation.
#: Reported for context and explicitly NOT used to size anything.
V04_ATTEMPT = -2.183
V04_PAIRS = 120

#: Fixed in the pre-registration before any pair was played.
MIE = 0.15
PLANNED_SD = 3.8
PLANNED_MDE = 0.238

#: Where the fitted vector is written, so the verdict can print it beside the
#: incumbent rather than describing it.
FIT_FILE = "ask_objective_fit_v2.json"


def _weights_table() -> list[str]:
    from fish4.askfeat import TERM_NAMES, AskWeights

    path = ROOT / "results" / FIT_FILE
    if not path.exists():
        return [f"  (no {FIT_FILE}; run the fit stage to report the vector)"]
    d = json.loads(path.read_text())
    fit = d.get("fit", d)
    # The vector lives under fit.learned_weights; the per-term diagnostics
    # (permutation p, cluster se) live under fit.linear.coefficients. An
    # earlier version of this looked for fit.coefficients, found nothing, and
    # printed an EMPTY TABLE under a heading -- which is worse than not
    # printing it, because the pre-registration commits to showing this vector
    # and a blank table reads as "there was nothing to show".
    learned = fit.get("learned_weights") or {}
    if not learned:
        return [f"  *** {FIT_FILE} has no fit.learned_weights; the table the "
                f"pre-registration\n      commits to cannot be printed, and "
                f"this says so rather than printing nothing."]
    lin = fit.get("linear") or {}
    coefs = lin.get("coefficients") or {}
    not_fitted = set(lin.get("terms_not_fitted")
                     or fit.get("terms_not_fitted") or [])
    inc = AskWeights()
    out = [f"  {'term':<10}{'incumbent':>11}{'learned':>11}{'perm p':>9}   note"]
    for name in TERM_NAMES:
        val = learned.get(name)
        if val is None:
            continue
        c = coefs.get(name)
        pv = c.get("perm_p") if isinstance(c, dict) else None
        pstr = f"{pv:>9.3f}" if isinstance(pv, (int, float)) else " " * 9
        note = "NOT FITTED (stale column, zeroed)" if name in not_fitted else ""
        out.append(f"  {name:<10}{getattr(inc, name):>+11.3f}{val:>+11.3f}"
                   f"{pstr}   {note}")
    if not_fitted:
        out.append(f"\n  {sorted(not_fitted)}: 0.0 by construction, not by "
                   f"measurement -- its stored\n  column predates a change to "
                   f"its formula.")
    out.append("\n  The individual signs are NOT findings. `certain` "
               "correlates 0.738 with\n  P(success), which carries weight 1.0 "
               "by convention, and a different fit on a\n  different "
               "population gives it the OPPOSITE sign. That collinearity is "
               "the\n  same one this paper documents for P(success)'s own "
               "coefficient.")
    return out


def main() -> int:
    cs = cells(BLOCKS)
    print("do learned ask weights beat hand-tuned ones?")
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

    p = pool(cs)
    est, se = p["fe"], p["fe_se"]
    lo, hi = est - Z * se, est + Z * se
    better, worse = lo > 0, hi < 0
    print("\nPRIMARY -- fixed-effect pool of the two blocks")
    print(f"  {est:+.4f}  95% [{lo:+.4f}, {hi:+.4f}]   "
          f"{'ENTIRELY ABOVE ZERO' if better else 'ENTIRELY BELOW ZERO' if worse else 'CONTAINS ZERO'}")

    print("\nhomogeneity across the two (diagnostic only)")
    print(f"  Cochran Q  {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2        {100 * p['i2']:.1f}%")

    print("\nTHE SIZING, as fixed in advance and as it came out")
    print(f"  planned per-pair sd     {PLANNED_SD:.3f}  -> MDE "
          f"{PLANNED_MDE:.3f}")
    print(f"  realised per-pair sd    {sd:.3f}  -> MDE {mde:.3f}")
    print(f"  minimum interesting     {MIE:.3f}")
    print(f"  divergence share        {100 * share:.1f}%  (an ask-weight change "
          f"alters decisions constantly, which is why the A/A sd is the right "
          f"one here)")

    print("\nFOR CONTEXT ONLY -- v0.4's own attempt")
    print(f"  {V04_ATTEMPT:+.3f} over {V04_PAIRS} pairs, best of three variants, "
          f"against fishbot4()\n  defaults rather than the champion, on the weak "
          f"rollout continuation. Different\n  target, different baseline, "
          f"different fit. It sized nothing here.")
    if n_tot and sd > 0:
        print(f"  At this size that result would sit "
              f"{abs(V04_ATTEMPT) / (sd / math.sqrt(n_tot)):.0f} standard errors "
              f"from zero, which is what\n  this design was built to be able to "
              f"see.")

    print("\nTHE FITTED VECTOR, beside the incumbent")
    for line in _weights_table():
        print(line)

    print("\n" + "=" * 70)
    if better:
        print("VERDICT: the learned weights BEAT the champion.")
        print("The pre-registration commits this to a REPLICATION on fresh "
              "seeds before it\nmoves any default. This line has already "
              "produced one confidently-argued\nresult that did not survive a "
              "control, and that is exactly the prior under\nwhich a single "
              "positive is most likely to be noise.")
    elif worse:
        print("VERDICT: the learned weights LOSE to the champion.")
        print(f"The line fails a second time, now against a target that "
              f"carries signal and a\nbaseline that is the shipped champion. "
              f"That is a stronger negative than v0.4's:\nthe diagnosis blamed "
              f"the continuation, the continuation was fixed, and the\nweights "
              f"still lose.")
    else:
        print("VERDICT: UNRESOLVED AT THIS SIZE.")
        print(f"The interval contains zero. The pre-registration fixed, before "
              f"any pair was\nplayed, that this is a FAILURE TO RESOLVE and "
              f"NOT a null: the MDE here is\n{mde:.3f} against a minimum "
              f"interesting effect of {MIE:.3f}, so an effect of the size\n"
              f"this study calls real could be present and this design would "
              f"miss it.")
        print(f"\nWhat it DOES resolve is the outcome that mattered most. A "
              f"repeat of v0.4's\n{V04_ATTEMPT:+.3f} is excluded: the lower "
              f"bound here is {lo:+.3f}. The catastrophe did not\nrecur, and "
              f"that is the finding.")
        print("\nA larger run needs its own pre-registration, not an extension "
              "of this one.")
    print("=" * 70)

    out = {"blocks": cs, "pooled": p, "n_pairs": n_tot,
           "estimate": est, "se": se, "ci": [lo, hi],
           "demonstrated_better": bool(better),
           "demonstrated_worse": bool(worse),
           "unresolved": bool(not better and not worse),
           "realised_sd": sd, "mde_80": mde, "divergence_share": share,
           "planned_sd": PLANNED_SD, "planned_mde": PLANNED_MDE,
           "min_interesting": MIE,
           "v04_attempt": {"est": V04_ATTEMPT, "n_pairs": V04_PAIRS}}
    dest = ROOT / "results" / "learned_weights_verdict.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
