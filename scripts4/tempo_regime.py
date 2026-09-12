"""How often is the engine in the regime where the turn it risks is free?

`fish4/askfeat.py` charges every candidate ask a tempo penalty of
`w_turn * (1 - p) * turn_risk[target]`, with w_turn = 0.6 and no dependence on
what the turn is actually worth. The paper's tempo section measured that, and
it is not a constant: bucketed by p_best -- the success probability of the ask
the seat would otherwise have made -- a turn prices at -0.043 +- 0.169 below
0.25, +0.004 +- 0.143 in [0.25, 0.50), and about +0.45 above 0.50. Its own
opening says none of the objective's tempo weights "was ever fitted against a
measured scale, because none existed. This section supplies one." It supplied
one and nothing went back to use it.

Whether that matters depends entirely on how much of the engine's play sits
below 0.50, which nobody has counted. This counts it, off the agent's own
trace, which `tests4/test_trace.py` asserts is RNG-free so instrumenting a run
cannot change it.

    py scripts4/tempo_regime.py [n_deals] [n_jobs]
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_100
AGENT0 = 9_000
#: the buckets the paper's tempo section used, with the price it measured
BANDS = [(0.00, 0.25, -0.043, 0.169),
         (0.25, 0.50, +0.004, 0.143),
         (0.50, 0.75, +0.508, 0.258),
         (0.75, 1.01, +0.415, 0.164)]
FREE_BELOW = 0.50


def _one(deal_seed: int) -> list:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1], trace=True)))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 7 + p)
    out = []
    for _ in range(600):
        if st.is_terminal:
            break
        m = st.turn
        act = agents[m].act(Observation.from_state(st, m))
        tr = getattr(agents[m], "last_trace", None)
        if tr and tr.get("kind") == "ask":
            ranked = tr.get("ranked") or []
            if ranked:
                # p of the ask the objective actually chose, which is the
                # quantity the tempo measurement bucketed by
                out.append(round(float(ranked[0].get("p_hit", 0.0)), 4))
        st.apply(m, act)
    return out


def report(ps: list) -> dict:
    n = len(ps)
    print(f"\n=== the regime the ask objective is in ({n:,} decisions) ===")
    print(f"  {'p_best band':<16}{'n':>8}{'share':>9}   what a turn is worth")
    rows = {}
    for lo, hi, price, se in BANDS:
        k = sum(1 for p in ps if lo <= p < hi)
        rows[f"[{lo:.2f},{hi:.2f})"] = {"n": k, "share": round(k / n, 4),
                                        "turn_price": price, "se": se}
        print(f"  [{lo:.2f}, {hi:.2f})     {k:>8}{k/n:>9.3f}   "
              f"{price:+.3f} +- {se:.3f}")
    free = sum(1 for p in ps if p < FREE_BELOW) / n
    print(f"\n  decisions where the turn at stake is measurably free: "
          f"{free:.4f}")
    print(f"  the objective charges the full 0.6*(1-p)*turn_risk at all of "
          f"them.")
    return {"rules": RULES_D, "n_decisions": n, "free_below": FREE_BELOW,
            "share_free": round(free, 4), "bands": rows}


def main(n_deals: int = 60, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [SEED0 + i for i in range(n_deals)]
    t0 = time.time()
    ps = []
    with Pool(n_jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            ps.extend(r)
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    if not ps:
        print("no ask decisions recorded")
        return 1
    out = report(ps)
    dest = ROOT / "results" / "tempo_regime.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          int(a[1]) if len(a) > 1 else 0))
