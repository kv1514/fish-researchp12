"""Why does the m = 2 best response score BELOW the champion in 5/157?

A negative gain is impossible on paper. The deviator may copy the champion at
every information set, so its optimum is at least the champion's value. Five
positions in ``results/ii_endgame_m2.json`` say otherwise, which means the
solver and ``champion_value`` are not measuring the same object.

The obvious suspect -- the depth cap -- is already out: a sweep over
MAX_PLIES 24 / 60 / 150 changed nothing, though it also never reproduced a
negative, so it settled less than it looks. This reproduces the actual
positions instead and asks the one question that splits the hypotheses:

    IS THE CHAMPION'S OWN ROOT ACTION IN THE DEVIATOR'S ACTION SET?

  * absent    -> the optimisation cannot copy the champion, so the bound does
                 not apply and the fault is in ``_deviator``'s action set.
  * present, and its value already >= champion_value
              -> the root is fine and the two disagree DEEPER, in how the
                 subtree is scored.
  * present, and its value < champion_value
              -> the same action is scored two different ways, which is a
                 difference between the recursion and the playout, not a
                 search failure at all.

    py scripts4/ii_negative_repro.py [game ...]
"""

from __future__ import annotations

import copy
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, SolveTimeout, _champion_action,
                            consistent_deals_multi)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24
LAYER = 2


def probe(g: int, deadline: float = 120.0):
    """Replay game ``g`` exactly as scripts4/ii_endgame.py does."""
    rules = RuleConfig()
    agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=99_000 + g)
    ar = random.Random(99_500 + g)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    out = []
    for _ in range(600):
        if st.is_terminal:
            break
        p = st.turn
        obs = Observation.from_state(st, p)
        live = [h for h, w in enumerate(obs.set_winner) if w is None]
        if len(live) == LAYER:
            agents[p].bel.update(obs)
            deals = consistent_deals_multi(obs, agents[p].bel, live)
            if deals and len(deals) <= MAX_SUPPORT:
                sv = ExactII(rules, list(live), p, SPEC)
                sv.deadline = time.monotonic() + deadline
                states = []
                for hands in deals:
                    t = GameState.from_components(
                        rules, list(hands), st.turn, list(st.set_winner))
                    t.history = list(st.history)
                    states.append(t)
                w = [1.0 / len(states)] * len(states)
                try:
                    v = sv.solve(states, w)
                except SolveTimeout:
                    st.apply(p, agents[p].act(obs))
                    continue
                except Exception:
                    st.apply(p, agents[p].act(obs))
                    continue
                cv = sv.champion_value(states, w)
                out.append((sv, states, w, v, cv, p))
        st.apply(p, agents[p].act(obs))
    return out


def main(games) -> int:
    rules = RuleConfig()
    verdicts = []
    for g in games:
        for sv, states, w, v, cv, seat in probe(g):
            if v - cv >= -1e-9:
                continue
            print(f"\n=== game {g}  seat {seat}  support {len(states)}  "
                  f"nodes {sv.nodes}")
            print(f"    best response {v:+.4f}   champion {cv:+.4f}   "
                  f"gain {v - cv:+.4f}")

            # The champion's root move. Every state in the set shares the
            # deviator's observation, so this is one action, not many -- and
            # the diagnostic asserts that rather than trusting it.
            champ = {repr(_champion_action(SPEC, rules, seat, s))
                     for s in states}
            print(f"    champion's root action(s): {sorted(champ)}")
            ca = sorted(champ)[0]
            present = ca in sv.action_values
            print(f"    in the deviator's action set: {present}")
            if present:
                print(f"    value the search assigns it: "
                      f"{sv.action_values[ca]:+.4f}")
            print(f"    actions considered: {len(sv.action_values)}")
            for k, val in sorted(sv.action_values.items(),
                                 key=lambda kv: -kv[1])[:6]:
                print(f"      {val:+.4f}  {k}")
            if not present:
                verdicts.append("action-set")
            elif sv.action_values[ca] + 1e-9 >= cv:
                verdicts.append("root-ok-deeper")
            else:
                verdicts.append("same-action-two-values")

    print("\n" + "=" * 66)
    if not verdicts:
        print("no negative-gain position reproduced in these games")
        return 1
    for name, why in (
            ("action-set", "the champion's move is NOT among the deviator's "
                           "options"),
            ("root-ok-deeper", "the root is sound; the subtree is scored "
                               "differently"),
            ("same-action-two-values", "one action, two values: recursion vs "
                                       "playout")):
        n = verdicts.count(name)
        if n:
            print(f"  {n:2d}  {why}")
    return 0


if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:]] or [20]
    raise SystemExit(main(a))
