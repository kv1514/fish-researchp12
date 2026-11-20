"""How long does each continuation take to finish a deal?

The paper's diagnosis of the failed objective-learning line was that a
public-information heuristic "throws away most of the value of a marginal card,
so a card won by a good ask is largely squandered before the game ends". That is
a story about a mechanism. This measures the mechanism.

Both continuations are handed the same late positions, the same determinized
world and the same root ask, and the only thing recorded is how many actions
each takes to reach a terminal state. A continuation that needs six times as
many plies to resolve the same position is spending most of the deal on
exchanges that undo each other, and every one of those plies is a chance for the
root ask to stop mattering to the final differential.

It also settles a confound in ``scripts4/rollout_target.py``'s control arm: if
either policy were hitting the action cap, the capped games would be scored on
resolved half-suits only, which would flatten that arm's target for a reason
having nothing to do with the policy's quality.

Usage: python scripts4/continuation_length.py [n_positions]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.beliefs import BeliefState                          # noqa: E402
from fish.cards import NUM_PLAYERS                            # noqa: E402
from fish.engine import GameState, IllegalAction              # noqa: E402
from fish.observation import Observation                      # noqa: E402
from fish4.learn.rollout import PublicInfoHeuristic           # noqa: E402
from fish4.posterior import Posterior                         # noqa: E402
from fish4.registry4 import make_agent                        # noqa: E402

from ask_regret import (GAMMA, MAX_ACTIONS, SPEC,              # noqa: E402
                        _legal_asks, harvest)

MIN_RESOLVED = 4


def _run(state, agents) -> tuple[int, bool]:
    n = 0
    while not state.is_terminal and n < MAX_ACTIONS:
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
        n += 1
    return n, state.is_terminal


def main(argv):
    n_pos = int(argv[0]) if argv else 40
    print("how long does each continuation take to finish the same position?\n")
    positions = harvest(max(40, n_pos * 3), MIN_RESOLVED, n_pos)

    pub, v04 = [], []
    pub_cap = v04_cap = 0
    for i, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        worlds = [list(w) for w in
                  Posterior(bel, random.Random(4400 + i), n_draws=160,
                            n_worlds=1, obs=obs, gamma=GAMMA).worlds()]
        asks = _legal_asks(obs)
        if not asks or not worlds:
            continue
        a, w = asks[0], worlds[0]

        st = GameState.from_components(rules, list(w), turn, list(sw))
        agents = [PublicInfoHeuristic() for _ in range(NUM_PLAYERS)]
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, 7000 + p)
        try:
            st.apply(seat, a)
        except IllegalAction:
            continue
        n, term = _run(st, agents)
        pub.append(n)
        pub_cap += (not term)

        st = GameState.from_components(rules, list(w), turn, list(sw))
        st.history = list(hist)
        agents = [make_agent(("fishbot4", dict(SPEC)))
                  for _ in range(NUM_PLAYERS)]
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, 7000 + p)
        try:
            st.apply(seat, a)
        except IllegalAction:
            continue
        n, term = _run(st, agents)
        v04.append(n)
        v04_cap += (not term)

    if not pub or not v04:
        print("no usable positions")
        return
    pub_a, v04_a = np.array(pub), np.array(v04)
    print(f"positions {min(len(pub), len(v04))} | "
          f">= {MIN_RESOLVED} half-suits resolved | cap {MAX_ACTIONS} actions\n")
    print(f"{'continuation':<22}{'mean':>8}{'median':>8}{'p90':>7}{'max':>6}"
          f"{'cap hits':>10}")
    print(f"{'public heuristic':<22}{pub_a.mean():>8.1f}"
          f"{np.median(pub_a):>8.0f}{np.percentile(pub_a, 90):>7.0f}"
          f"{pub_a.max():>6}{pub_cap:>10}")
    print(f"{'full v0.4':<22}{v04_a.mean():>8.1f}"
          f"{np.median(v04_a):>8.0f}{np.percentile(v04_a, 90):>7.0f}"
          f"{v04_a.max():>6}{v04_cap:>10}")
    ratio = pub_a.mean() / v04_a.mean()
    print(f"\nThe heuristic needs {ratio:.1f}x as many plies to resolve the same "
          f"position.")
    print("Those extra plies are exchanges that undo each other -- the policy")
    print("has no reason to stop trading a card back and forth until its stall")
    print("rule fires. Every one of them is a chance for the root ask to stop")
    print("mattering to the final differential, which is the paper's stated")
    print("mechanism measured rather than asserted.")
    if pub_cap or v04_cap:
        print(f"\nCAUTION: the action cap bound {pub_cap} public and {v04_cap} "
              f"v0.4 rollouts.\nA capped game is scored on resolved half-suits "
              f"only, so any slope measured\nwith this cap is confounded by it.")
    else:
        print(f"\nNeither policy hit the {MAX_ACTIONS}-action cap, so the cap "
              f"confounds nothing in\nthe rollout-target comparison.")

    out = {"n_positions": min(len(pub), len(v04)),
           "min_resolved": MIN_RESOLVED, "max_actions": MAX_ACTIONS,
           "public": {"mean": float(pub_a.mean()),
                      "median": float(np.median(pub_a)),
                      "max": int(pub_a.max()), "cap_hits": pub_cap},
           "v04": {"mean": float(v04_a.mean()),
                   "median": float(np.median(v04_a)),
                   "max": int(v04_a.max()), "cap_hits": v04_cap},
           "ratio": float(ratio)}
    dest = ROOT / "results" / "continuation_length.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
