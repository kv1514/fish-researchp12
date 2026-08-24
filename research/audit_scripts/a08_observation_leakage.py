"""A08: observation boundary / leakage checks.

(1) Observation.from_state == Observation.reconstruct at EVERY ply for ALL
    six seats, across rule configurations the shipped tests do not cover
    (claims_any_time, allow_bluff_asks, wrong_distribution_outcome,
    non-zero starting_player, 48-card variant).
(2) Observation.initial_hand() equals the true initial hand at every ply
    (BeliefState pins the observer's cards from it, so an error here would
    be an unsoundness source).
(3) Observation carries no field derived from hidden state.
(4) agent seeds are independent of the deal.
"""
import sys
import random
import itertools

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState, AskEvent, ClaimEvent, PassEvent
from fish.observation import Observation
from fish.agents import AGENT_REGISTRY
from fish.cards import deck_size


def hdr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


CONFIGS = [
    dict(),
    dict(variant="48"),
    dict(claims_any_time=True),
    dict(allow_bluff_asks=True),
    dict(wrong_distribution_outcome="opponent"),
    dict(starting_player=3),
    dict(variant="48", starting_player=5, allow_bluff_asks=True),
    dict(claims_any_time=True, wrong_distribution_outcome="opponent",
         starting_player=2),
]

hdr("1+2. reconstruct equivalence and initial_hand correctness")
tot_ply = 0
mismatch = []
ih_bad = []
for cfg in CONFIGS:
    rules = RuleConfig(**cfg)
    n = deck_size(rules.variant)
    for g in range(6):
        for agent_name in ("heuristic", "memory", "probabilistic"):
            state = GameState.deal(rules, seed=1000 * g + 7)
            initial = [state.hands[p] for p in range(6)]
            agents = [AGENT_REGISTRY[agent_name]() for _ in range(6)]
            rng = random.Random(g)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, rng.getrandbits(64))
            ply = 0
            while not state.is_terminal and ply < 400:
                for seat in range(6):
                    o1 = Observation.from_state(state, seat)
                    o2 = Observation.reconstruct(rules, seat, initial[seat],
                                                 tuple(state.history))
                    if (o1.hand, o1.turn, o1.hand_counts, o1.set_winner) != \
                       (o2.hand, o2.turn, o2.hand_counts, o2.set_winner):
                        mismatch.append((cfg, agent_name, g, ply, seat,
                                         (o1.hand, o1.turn, o1.hand_counts,
                                          o1.set_winner),
                                         (o2.hand, o2.turn, o2.hand_counts,
                                          o2.set_winner)))
                    if o1.initial_hand() != initial[seat]:
                        ih_bad.append((cfg, agent_name, g, ply, seat,
                                       bin(o1.initial_hand()),
                                       bin(initial[seat])))
                    tot_ply += 1
                p = state.turn
                state.apply(p, agents[p].act(Observation.from_state(state, p)))
                ply += 1
print("  seat-plies checked:", tot_ply)
print("  reconstruct mismatches:", len(mismatch))
for m in mismatch[:5]:
    print("    ", m)
print("  initial_hand errors:", len(ih_bad))
for m in ih_bad[:5]:
    print("    ", m)

hdr("3. Observation fields")
o = Observation.from_state(GameState.deal(RuleConfig(), seed=1), 0)
import dataclasses
print("  fields:", [f.name for f in dataclasses.fields(o)])
print("  GameState slots:", GameState.__slots__)
print("  'hands' present in Observation:", hasattr(o, "hands"))
print("  'agent_seed' present in Observation:", hasattr(o, "agent_seed"))

hdr("4. agent seed independence from the deal")
import inspect
from fish import runner
src = inspect.getsource(runner.play_game)
print("  play_game seeds agents from:",
      [l.strip() for l in src.splitlines() if "agent_seed" in l or "getrandbits" in l])
from fish.eval import tournament
src2 = inspect.getsource(tournament.play_matchup)
print("  tournament seed stream:",
      [l.strip() for l in src2.splitlines()
       if "seed_rng" in l or "secrets" in l])
