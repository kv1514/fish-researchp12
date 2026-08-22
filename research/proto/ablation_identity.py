"""A zero weight must reproduce the baseline decision for decision.

v0.3's most instructive methodological failure was a confounded ablation: the
ablated agent silently changed a second term, so every cell compared two changes
at once and produced tight, confident, wrong intervals. This is the guard.
"""
import random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.rules import RuleConfig
from fish.engine import GameState
from fish.observation import Observation
from fish4.registry4 import make_agent

rules = RuleConfig()
TERMS = ["w_expose", "w_claim", "w_info", "w_certain", "w_concent",
         "w_reveal", "w_deplete"]
for term in TERMS:
    same = diff = 0
    for g in range(3):
        a1 = make_agent(("fishbot4", {}))
        a2 = make_agent(("fishbot4", {term: 0.0}))
        a3 = make_agent(("fishbot4", {term: 0.7}))
        st = GameState.deal(rules, seed=5000 + g)
        for a in (a1, a2, a3):
            a.begin_game(st.turn, rules, 1234)
        drivers = [make_agent(("tuned", {"w_turn": 0.6, "w_scarce": 0.2}))
                   for _ in range(6)]
        ar = random.Random(60 + g)
        for p, d in enumerate(drivers):
            d.begin_game(p, rules, ar.getrandbits(64))
        step = 0
        while not st.is_terminal and step < 120:
            p = st.turn
            obs = Observation.from_state(st, p)
            if step % 5 == 0 and step > 3:
                acts = []
                for agent in (a1, a2, a3):
                    ag = make_agent(("fishbot4", {} if agent is a1 else
                                     {term: 0.0} if agent is a2 else {term: 0.7}))
                    ag.begin_game(p, rules, 999)
                    acts.append(ag.act(obs))
                if acts[0] == acts[1]:
                    same += 1
                else:
                    print(f"  {term}: ZERO-WEIGHT DIVERGENCE at step {step}: "
                          f"{acts[0]} vs {acts[1]}")
                if acts[0] != acts[2]:
                    diff += 1
            st.apply(p, drivers[p].act(obs))
            step += 1
    print(f"{term:12s} zero-weight identical: {same}  "
          f"non-zero-weight changed a decision: {diff}")
