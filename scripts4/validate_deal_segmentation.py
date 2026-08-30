"""Does 'a drop in history length starts a new deal' recover the true deal index?

Checked against the harvest itself, which knows g. If the rule is right on the
full harvest it is right on any subset of consecutive rows drawn from it.
"""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ok = True
for spec in ("objective", "champion"):
    os.environ["ASK_REGRET_HARVEST_SPEC"] = spec
    for m in [k for k in list(sys.modules) if k.startswith("scripts4.ask_regret")]:
        del sys.modules[m]
    import scripts4.ask_regret as AR
    g = []
    pos = AR.harvest(130, 5, 260, games_out=g)
    hist = [len(p[4]) for p in pos]
    seg, cur, prev = [], 0, -1
    for h in hist:
        if h <= prev:
            cur += 1
        seg.append(cur); prev = h
    true_boundaries = [i for i in range(1, len(g)) if g[i] != g[i-1]]
    seg_boundaries = [i for i in range(1, len(seg)) if seg[i] != seg[i-1]]
    same = true_boundaries == seg_boundaries
    ok &= same
    print(f"{spec:10s} {len(pos)} positions, {len(set(g))} deals; "
          f"boundaries recovered exactly: {same}")
    if not same:
        print(f"   true {true_boundaries}\n   seg  {seg_boundaries}")
print("\nRULE VALID" if ok else "\nRULE INVALID -- do not use it")
