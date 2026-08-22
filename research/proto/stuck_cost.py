"""How much does 'we own this half-suit but cannot place it' actually cost?

For every half-suit that is at some point PROVABLY owned by a team (from a
member's own beliefs) but not placeable by that member, record how it finally
resolved. If those half-suits resolve normally, the deadlock is a curiosity.
If they null or get gifted away, it is a target.
"""
import random, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.perpetual import half_suit_owner_team
from fish4.registry4 import make_agent

rules = RuleConfig()
outcome = Counter(); never = Counter(); tot_hs = 0
stuck_dur = []
for g in range(40):
    bots = [make_agent(("fishbot4", {"opponent_gamma": 0.35})) for _ in range(6)]
    st = GameState.deal(rules, seed=910_000 + g)
    ar = random.Random(920_000 + g)
    for p, b in enumerate(bots): b.begin_game(p, rules, ar.getrandbits(64))
    bels = [BeliefState(rules, observer=p) for p in range(6)]
    stuck = {}          # hs -> (team, plies stuck)
    n = 0
    while not st.is_terminal and n < 400:
        for q in range(6):
            bels[q].update(Observation.from_state(st, q))
        for hs, w in enumerate(st.set_winner):
            if w is not None: continue
            for q in range(6):
                if half_suit_owner_team(bels[q], hs) != team_of(q): continue
                amb = any(bels[q].current_holder_mask(c) & (bels[q].current_holder_mask(c)-1)
                          for c in half_suit_cards(hs))
                if amb:
                    k = (hs, team_of(q))
                    stuck[k] = stuck.get(k, 0) + 1
                break
        p = st.turn
        st.apply(p, bots[p].act(Observation.from_state(st, p)))
        n += 1
    for hs, w in enumerate(st.set_winner):
        tot_hs += 1
        for team in (0, 1):
            if (hs, team) in stuck:
                stuck_dur.append(stuck[(hs, team)])
                if w is None: outcome["unresolved"] += 1
                elif w == -1: outcome["NULLED"] += 1
                elif w == team: outcome["won by the owning team"] += 1
                else: outcome["GIFTED to the opponents"] += 1
            else:
                if w == -1: never["NULLED"] += 1
                elif w in (0,1): never["scored"] += 1
n_stuck = sum(outcome.values())
print(f"half-suits observed: {tot_hs}")
print(f"of these, ever provably-owned-but-unplaceable: {n_stuck} "
      f"({100*n_stuck/tot_hs:.1f}%)")
print(f"  mean plies spent stuck: {sum(stuck_dur)/max(1,len(stuck_dur)):.1f}"
      f"  max {max(stuck_dur) if stuck_dur else 0}")
print("\noutcome of a STUCK half-suit:")
for k, v in outcome.most_common():
    print(f"   {k:28s} {v:4d}  ({100*v/max(1,n_stuck):.1f}%)")
n_never = sum(never.values())
print("\noutcome of a half-suit that was never stuck:")
for k, v in never.most_common():
    print(f"   {k:28s} {v:4d}  ({100*v/max(1,n_never):.1f}%)")
