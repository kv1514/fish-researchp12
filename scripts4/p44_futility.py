"""P44's futility screen: do D1 and D2 change enough to be worth a duel?

Registered in `prereg/kraken_v12_declaration_latency.md` with its thresholds
fixed before the run: D1 must change at least 2% of ask decisions, D2 at least
0.25 declarations a game. `avoid_doomed_asks` fires on 1.5% of decisions and is
a measured null at that rate, so an arm firing there is not worth 6,000 pairs
to re-establish.

WHY A FIRING RATE AND NOT A MARGIN. Four of v1.1's seven directions were
stopped here, saving roughly 9,000 duplicate-deal pairs. A screen that reads a
margin is a duel with a smaller n and invites reading a sign off noise; a
screen that reads how often the code path is reached cannot.

WHAT IS COUNTED. Both arms play their own games -- this is not paired against
the champion, because "how often does this knob fire" is a property of the arm
alone. For D1 the numerator is decisions where `_filter_dead` actually removed
the top-scoring ask from consideration. For D2 it is voluntary declarations the
incumbent bar would have refused, which is exactly the disjunct the arm adds.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                         # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_500_000
AGENT0 = 95_000
MAX_ACTIONS = 600
BASE = {"opponent_gamma": 0.35}


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    ours = {p for p in range(6) if (p % 2 == 0) == kv_even}
    # Both knobs on at once for the FIRING count only. They act on disjoint
    # code paths -- one filters asks, the other adds a declaration -- so the
    # counts do not contaminate each other, and one pass costs half of two.
    arm = dict(BASE, dead_ask_threshold=0.5, claim_owned_threshold=0.77)
    agents = [make_agent(("fishbot4", arm)) if p in ours
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    out = {"asks": 0, "d1_fired": 0, "declares": 0, "d2_fired": 0, "games": 1}
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        if mover in ours:
            ag = agents[mover]
            if hasattr(act, "target") and hasattr(act, "card"):
                out["asks"] += 1
                # Re-derive the filter's verdict from the agent's own state at
                # this decision: the posterior it just built is still on it, so
                # this is the sample the decision used and not a fresh draw.
                asks = obs.legal_asks()
                from fish4.askfeat import DecisionContext
                ctx = DecisionContext(obs, ag.bel, ag.build_posterior(obs))
                order = list(range(len(asks)))
                if ag._filter_dead(order, asks, ctx) is not order:
                    out["d1_fired"] += 1
            elif hasattr(act, "half_suit"):
                out["declares"] += 1
                claims = _claims_for(ag, obs)
                best = claims.best_candidate()
                # The arm's own disjunct: p_exact below the incumbent bar, and
                # p_team at the ceiling. A declaration the champion would also
                # have made does not count.
                if (best is not None and best[0] < ag.claim_cfg.threshold
                        and best[1] >= ag.claim_cfg.owned_p_team):
                    out["d2_fired"] += 1
        st.apply(mover, act)
    return out


def _claims_for(ag, obs):
    from fish4.claim4 import ClaimEvaluator
    from fish4.askfeat import DecisionContext
    ctx = DecisionContext(obs, ag.bel, ag.build_posterior(obs))
    return ClaimEvaluator(ag._claim_ctx(ctx), ag.claim_cfg)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results" / "p44_futility.json"))
    a = ap.parse_args(argv)
    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games, counting how often each knob fires",
          flush=True)
    tot = {"asks": 0, "d1_fired": 0, "declares": 0, "d2_fired": 0, "games": 0}
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, g in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            for k in tot:
                tot[k] += g[k]
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} games, "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)
    d1 = tot["d1_fired"] / max(1, tot["asks"])
    d2 = tot["d2_fired"] / max(1, tot["games"])
    print(f"\n=== P44 futility screen ===")
    print(f"{tot['games']:,} games, {tot['asks']:,} of our ask decisions\n")
    print(f"  D1  dead_ask_threshold=0.5 changed the ask   "
          f"{tot['d1_fired']:,}/{tot['asks']:,} = {d1:.2%}   "
          f"bar 2.00%   {'PASS' if d1 >= 0.02 else 'STOP'}")
    print(f"  D2  claim_owned_threshold=0.77 declared      "
          f"{tot['d2_fired']:,} in {tot['games']:,} games = {d2:.3f}/game   "
          f"bar 0.250/game   {'PASS' if d2 >= 0.25 else 'STOP'}")
    print(f"\n  (for scale: avoid_doomed_asks fires on 1.5% of decisions and "
          "is a measured null there)")
    out = {"games": tot["games"], "asks": tot["asks"],
           "d1_fire_rate": d1, "d1_bar": 0.02, "d1_pass": d1 >= 0.02,
           "d2_per_game": d2, "d2_bar": 0.25, "d2_pass": d2 >= 0.25,
           "counts": tot, "seconds": round(time.time() - t0, 1),
           "prereg": "prereg/kraken_v12_declaration_latency.md"}
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
