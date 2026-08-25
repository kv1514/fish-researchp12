"""How much does the champion randomise at m = 1? The caveat on the exact BR.

``results/ii_endgame.json`` best-responds to a DETERMINISTIC realisation of the
champion -- seeded from a hash of the observation -- because the champion
samples, and a distribution over policies is not a strategy one can
best-respond to. That choice is what makes the solver exact, and it is also
what limits the reading:

    best-responding to a realisation you can PREDICT is easier than
    best-responding to the mixture it was drawn from.

So the measured gain likely overstates the exploitability of the champion as it
actually plays. The size of that overstatement depends on how much the champion
mixes, which is measurable directly: query the same information set under many
seeds and count distinct actions. If it always plays the same move, the
realisation IS the policy and the caveat is empty.

    py scripts4/champion_mixing.py [n_games] [n_seeds]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import consistent_deals
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def main(n_games: int = 40, k: int = 12) -> int:
    rules = RuleConfig()
    dist = []
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=76_000_000 + g)
        ar = random.Random(76_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 1:
                agents[p].bel.update(obs)
                deals = consistent_deals(obs, agents[p].bel, live[0])
                if 1 < len(deals) <= 24:
                    acts = set()
                    for s in range(k):
                        a2 = make_agent(SPEC)
                        a2.begin_game(p, rules, 1000 + s)
                        try:
                            acts.add(repr(a2.act(obs)))
                        except Exception:
                            pass
                    dist.append(len(acts))
            st.apply(p, agents[p].act(obs))
        print(f"  {g+1}/{n_games} games, {len(dist)} info sets", flush=True)

    n = len(dist)
    if not n:
        print("No hidden m=1 information sets reached.")
        return 1
    same = sum(1 for d in dist if d == 1)
    print(f"\n{n} hidden m=1 information sets, {k} seeds each\n")
    print(f"  same action on every seed: {same}/{n} = {same/n*100:.0f}%")
    print(f"  varies:                    {n-same}/{n} = {(n-same)/n*100:.0f}%")
    print(f"  mean distinct actions over {k} seeds: {sum(dist)/n:.2f}")
    print()
    if same == n:
        print("The champion is effectively a pure strategy here, so the exact")
        print("best response is against the policy itself and the caveat is "
              "empty.")
    else:
        print("The champion mixes at most of these information sets, so the")
        print("exact gain in results/ii_endgame.json is the exploitability of")
        print("ONE REALISATION and likely overstates the exploitability of the")
        print("randomised policy it was drawn from. How much is not settled by")
        print("this measurement -- it bounds the caveat's relevance, not its")
        print("size -- and settling it needs a best response against the mixed")
        print("policy, which is a different and larger computation.")

    out = ROOT / "results" / "champion_mixing.json"
    out.write_text(json.dumps({"n_games": n_games, "n_seeds": k,
                               "n_info_sets": n, "n_pure": same,
                               "mean_distinct": sum(dist) / n,
                               "distinct": dist}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40, int(a[1]) if len(a) > 1 else 12))
