"""How far up the layers can the exact imperfect-information solver reach?

``fish4/exact_ii`` enumerates every deal consistent with the public record and
optimises over the deviator's information sets. Its cost has two independent
drivers, and only one of them is obvious:

  * **the support** -- how many deals the record still allows. Enumerable or
    not, measurable directly, and measured here.
  * **the tree** -- how deep play runs before the layer resolves. At m = 1 six
    cards are in play; at m = 2 it is twelve, and the game runs roughly twice
    as long with more branching at every node.

The support is the cheap thing to check first, so this checks it before any
effort goes into extending the solver. It does NOT establish that a layer is
solvable: a small support with a deep tree is still out of reach, and claiming
m = 2 is tractable on this evidence alone would be exactly the kind of
extrapolation this project keeps catching.

    py scripts4/ii_support_sizes.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
#: Beyond this the raw product of per-card options is not worth enumerating;
#: reported as un-enumerable rather than silently skipped.
PRODUCT_CAP = 400_000
COUNT_CAP = 5000


def support(obs, bel, live) -> int:
    cards = [c for h in live for c in half_suit_cards(h)]
    unseen = [c for c in cards if not (obs.hand >> c) & 1]
    opts = []
    for c in unseen:
        m = bel.current_holder_mask(c)
        allowed = [q for q in range(NUM_PLAYERS)
                   if q != obs.player and (m >> q) & 1]
        if not allowed:
            return 0
        opts.append(allowed)
    prod = 1
    for o in opts:
        prod *= len(o)
    if prod > PRODUCT_CAP:
        return -1
    counts = list(obs.hand_counts)
    me = obs.player
    n = 0
    for combo in (product(*opts) if opts else [()]):
        need = [0] * NUM_PLAYERS
        for q in combo:
            need[q] += 1
        if all(need[q] == counts[q] for q in range(NUM_PLAYERS) if q != me):
            n += 1
            if n > COUNT_CAP:
                return COUNT_CAP + 1
    return n


def main(n_games: int = 25) -> int:
    rules = RuleConfig()
    sizes = {1: [], 2: [], 3: []}
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=78_000 + g)
        ar = random.Random(78_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) in sizes:
                agents[p].bel.update(obs)
                sizes[len(live)].append(support(obs, agents[p].bel, live))
            st.apply(p, agents[p].act(obs))
        print(f"  {g+1}/{n_games} games", flush=True)

    out = {}
    print(f"\n{'m':>3}{'decisions':>11}{'median':>9}{'mean':>8}"
          f"{'<=24':>8}{'<=200':>8}{'huge':>7}")
    for m in sorted(sizes):
        raw = sizes[m]
        if not raw:
            continue
        v = sorted(x for x in raw if x >= 0)
        huge = sum(1 for x in raw if x < 0)
        if not v:
            continue
        row = {"decisions": len(raw), "median": v[len(v) // 2],
               "mean": sum(v) / len(v),
               "share_le_24": sum(1 for x in v if x <= 24) / len(v),
               "share_le_200": sum(1 for x in v if x <= 200) / len(v),
               "un_enumerable": huge}
        out[m] = row
        print(f"{m:>3}{len(raw):>11}{row['median']:>9}{row['mean']:>8.0f}"
              f"{row['share_le_24']*100:>7.0f}%{row['share_le_200']*100:>7.0f}%"
              f"{huge:>7}")

    print("\nThe support is enumerable for most of m = 2, which is necessary "
          "for an exact\nsolve and not sufficient. The other cost is tree "
          "depth: m = 2 has twelve cards\nin play against six, so play runs "
          "about twice as long with more branching at\nevery node, and that "
          "is not measured here. Extending the solver has to be\ntested "
          "against a real m = 2 position before the layer is called reachable.")

    o = ROOT / "results" / "ii_support_sizes.json"
    o.write_text(json.dumps({"n_games": n_games, "by_live": out,
                             "product_cap": PRODUCT_CAP,
                             "count_cap": COUNT_CAP}, indent=1))
    print(f"\nwrote {o.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 25))
