"""Are nulled half-suits a lever, or a symptom? A spurious correlation, caught.

Every large duel in this project nulls about **0.274 half-suits per game** --
3.0% of the nine -- and the rate is strikingly stable across arms. A null scores
for nobody, so each one costs a full set of DIFFERENTIAL to whichever team would
otherwise have taken that half-suit. At the exchange rate measured in
``results/inference_curve.json`` (0.45 sets per card) that is a lot of value
sitting in one place, and "reduce nulls" is the obvious next feature.

It is the wrong next feature, and this script is why.

WHAT LOOKED LIKE A LEVER
------------------------
Duel records carry ``x_nulls`` and ``y_nulls``, attributing each null to the
side whose claim caused it. Across 66 duels of at least 500 pairs, the nulls a
challenger causes MINUS the nulls the champion causes correlates with the
challenger's margin at **r = -0.365**, 95% CI [-0.558, -0.135]. Cause more
nulls, lose more. A slope of about -20 sets per extra null per game.

WHY IT IS NOT ONE
-----------------
Drop the blowouts and the sign inverts:

    all 66 arms                        r = -0.365  [-0.558, -0.135]
    excluding |margin| > 1.0   n=61    r = +0.466  [+0.243, +0.643]
    excluding |margin| > 0.6   n=59    r = +0.009  [-0.248, +0.264]
    excluding |margin| > 0.3   n=49    r = -0.072  [-0.346, +0.214]

Removing five arms flips the correlation from strongly negative to strongly
positive; removing two more kills it entirely. Among arms of comparable
strength -- the only comparison that could support a causal reading -- there is
no relationship at all.

The confound is visible in the extremes. ``value pure`` (-7.191) and
``value_keep`` (-2.88) both null far more than the champion AND lose badly, but
they lose because they play badly, and playing badly causes both. The clincher
is ``LEARNED WEIGHTS``, which causes 0.074 FEWER nulls per game than the
champion and still loses by -0.745. Fewer nulls, worse play.

So the null rate is a symptom of policy quality, not a handle on it, and
"reduce nulls" would have optimised a correlate. The paper already supplies the
mechanism for why most of them are structural: 73% of nulls arise in STUCK
half-suits, where the null rate is 23.4% against 0.92% elsewhere -- a property
of the position, not of the claim that ended it.

    py scripts4/null_lever.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"

#: A causal reading needs arms that are otherwise comparable. These cutoffs on
#: |margin| are the sensitivity analysis, not a search for a cutoff that works.
CUTOFFS = (None, 1.0, 0.6, 0.3)


def load():
    out = []
    for line in DUELS.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("n_pairs", 0) < 500:
            continue
        x, y = r.get("x_nulls"), r.get("y_nulls")
        if x is None or y is None or r.get("diff_mean") is None:
            continue
        out.append(((x - y) / (2 * r["n_pairs"]), r["diff_mean"], r["label"]))
    return out


def corr(sub):
    n = len(sub)
    if n < 4:
        return None
    mx = sum(a for a, _, _ in sub) / n
    my = sum(b for _, b, _ in sub) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a, _, _ in sub) / (n - 1))
    sy = math.sqrt(sum((b - my) ** 2 for _, b, _ in sub) / (n - 1))
    if sx * sy == 0:
        return None
    r = sum((a - mx) * (b - my) for a, b, _ in sub) / (n - 1) / (sx * sy)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    return {"n": n, "r": r, "ci95": [math.tanh(z - 1.96 * se),
                                     math.tanh(z + 1.96 * se)]}


def main() -> int:
    d = load()
    tot_n = 0
    tot_g = 0
    for line in DUELS.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("n_pairs", 0) >= 500 and r.get("nulls") is not None:
            tot_n += r["nulls"]
            tot_g += 2 * r["n_pairs"]
    print(f"nulls per game: {tot_n/tot_g:.3f}  "
          f"({tot_n} in {tot_g} games, {tot_n/tot_g/9*100:.1f}% of half-suits)\n")

    print("correlation of (nulls caused by challenger minus champion, per game)")
    print("with the challenger's margin:\n")
    out = []
    for c in CUTOFFS:
        sub = d if c is None else [t for t in d if abs(t[1]) < c]
        s = corr(sub)
        if not s:
            continue
        tag = "all arms" if c is None else f"excluding |margin| > {c}"
        print(f"  {tag:<30} n={s['n']:>3}  r={s['r']:+.3f}  "
              f"95% CI [{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]")
        out.append({"cutoff": c, **s})

    signs = {s["r"] > 0 for s in out}
    print()
    if len(signs) > 1:
        print("The sign is NOT stable across cutoffs. That is the signature of a")
        print("correlation carried by a few extreme arms, not of a lever: a")
        print("policy that plays badly both loses and nulls more, and among arms")
        print("of comparable strength the relationship disappears.")
        print("\nReducing nulls would optimise a symptom.")
    else:
        print("Sign stable across cutoffs; the relationship survives dropping")
        print("the extremes and is worth pursuing.")

    (ROOT / "results" / "null_lever.json").write_text(json.dumps(
        {"nulls_per_game": tot_n / tot_g, "n_games": tot_g,
         "by_cutoff": out, "sign_stable": len(signs) == 1}, indent=1))
    print(f"\nwrote results/null_lever.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
