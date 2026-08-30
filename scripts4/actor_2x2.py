"""The #82 2x2, with every interval clustered by DEAL.

    py scripts4/actor_2x2.py

Reads the four actor_compare runs already on disk and writes
``results/actor_compare_2x2.json``. The archived runs predate the
``deal`` field, so the deal index is recovered by replaying the harvest
-- which reproduces them exactly, checked on every position's legal-ask
count. Freshly-run cells carry ``deal`` on the row and need no replay.

`harvest` returns positions in game order and stops when it has enough, so
"129 positions" is 129 positions from FIVE deals. Every interval in this family
was computed as if positions were independent. They are not.
"""
import json, math, os, statistics, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CELLS = [("objective","objective","results/actor_compare.json"),
         ("objective","champion", "results/actor_compare_cross2.json"),
         ("champion", "objective","results/actor_compare_cross.json"),
         ("champion", "champion", "results/actor_compare_champion.json")]

def gmap(spec):
    os.environ["ASK_REGRET_HARVEST_SPEC"] = spec
    for m in [k for k in list(sys.modules) if k.startswith("scripts4.ask_regret")]:
        del sys.modules[m]
    import scripts4.ask_regret as AR
    g = []; AR.harvest(130, 5, 260, games_out=g); return g

G = {s: gmap(s) for s in ("objective", "champion")}

def cl(by):
    n = sum(len(v) for v in by.values()); k = len(by)
    mu = sum(sum(v) for v in by.values()) / n
    if k < 2: return mu, float("nan"), n, k
    acc = sum((sum(v) - mu*len(v))**2 for v in by.values())
    return mu, 1.96*math.sqrt(acc*k/(k-1.0))/n, n, k

def iid(x):
    return 1.96*statistics.stdev(x)/math.sqrt(len(x))

data = {}
print(f"{'harvest':<11}{'cont.':<11}{'pos':>5}{'deals':>7}   "
      f"{'chp-obj paired':<34}{'champion-actor level'}")
for h, r, f in CELLS:
    d = json.load(open(f)); g = G[h]
    by_p, by_l = {}, {}
    for row in d["rows"]:
        gi = g[row["position"]]
        by_p.setdefault(gi, []).append(row["champion"] - row["objective only"])
        by_l.setdefault(gi, []).append(row["champion"])
    mp, hp, n, k = cl(by_p); ml, hl, _, _ = cl(by_l)
    fp = [v for x in by_p.values() for v in x]
    data[(h, r)] = {"by_level": by_l, "by_paired": by_p, "n": n, "deals": k,
                    "level": ml, "level_hw": hl}
    print(f"{h:<11}{r:<11}{n:>5}{k:>7}   "
          f"{mp:+.4f} [{mp-hp:+.4f},{mp+hp:+.4f}] (iid +/-{iid(fp):.4f})   "
          f"{ml:+.4f} [{ml-hl:+.4f},{ml+hl:+.4f}]")

print("\nCONTINUATION effect, paired on identical positions, clustered by deal")
tot = {}
for harv in ("objective", "champion"):
    a = {r["position"]: r["champion"] for r in json.load(open(
            dict(((h, r), f) for h, r, f in CELLS)[(harv, "objective")]))["rows"]}
    b = {r["position"]: r["champion"] for r in json.load(open(
            dict(((h, r), f) for h, r, f in CELLS)[(harv, "champion")]))["rows"]}
    g = G[harv]; by = {}
    for p in sorted(set(a) & set(b)):
        by.setdefault(g[p], []).append(b[p] - a[p])
        tot.setdefault((harv, g[p]), []).append(b[p] - a[p])
    m, hw, n, k = cl(by)
    print(f"  {harv:10s} harvest  n={n:4d} deals={k}  {m:+.4f} [{m-hw:+.4f}, {m+hw:+.4f}]")
m, hw, n, k = cl(tot)
print(f"  {'pooled':10s}          n={n:4d} deals={k}  {m:+.4f} [{m-hw:+.4f}, {m+hw:+.4f}]"
      + ("   EXCLUDES 0" if (m-hw)*(m+hw) > 0 else "   straddles 0"))

print("\nPOSITIONS effect (champion turf - objective turf), unpaired by construction")
for cont in ("objective", "champion"):
    A, B = data[("objective", cont)], data[("champion", cont)]
    diff = B["level"] - A["level"]
    hw = math.sqrt((A["level_hw"])**2 + (B["level_hw"])**2)
    print(f"  {cont:10s} continuation  {diff:+.4f} [{diff-hw:+.4f}, {diff+hw:+.4f}]")
ses = [data[c]["level_hw"]/1.96 for c in data]
mh = ((data[("champion","champion")]["level"]+data[("champion","objective")]["level"])/2
      - (data[("objective","objective")]["level"]+data[("objective","champion")]["level"])/2)
hw = 1.96*math.sqrt(sum(s*s for s in ses))/2
print(f"  {'pooled main effect':24s}{mh:+.4f} [{mh-hw:+.4f}, {mh+hw:+.4f}]"
      + ("   EXCLUDES 0" if (mh-hw)*(mh+hw) > 0 else "   straddles 0"))

import json as _json
out = {"cells": [], "continuation_effect": {}, "positions_effect": {}}
for (h, r), v in data.items():
    out["cells"].append({"harvest": h, "continuation": r, "n": v["n"],
                         "deals": v["deals"], "champion_level": v["level"],
                         "champion_level_half_width": v["level_hw"]})
mm, hh, nn, kk = cl(tot)
out["continuation_effect"] = {"mean": mm, "half_width": hh, "n": nn, "deals": kk,
                              "paired": True, "clustered_by": "deal"}
out["positions_effect"] = {"mean": mh, "half_width": hw, "paired": False,
                           "clustered_by": "deal"}
(ROOT / "results" / "actor_compare_2x2.json").write_text(
    _json.dumps(out, indent=1))
print("\nwrote results/actor_compare_2x2.json")
