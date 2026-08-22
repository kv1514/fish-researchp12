"""A12: assorted checks.

(1) GameState.from_components round-trip over real game states (does it ever
    change the turn or crash?)
(2) Observation-side legality helpers agree with GameState for every seat.
(3) TunedAgent kwarg surface vs its parent.
(4) ExactEndgameMixin swallows every exception, including genuine bugs.
(5) BeliefState._pinned_count is written but never read.
(6) claims by a cardless on-move player: does any shipped agent ever emit one?
"""
import sys
import random
import inspect

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState, Claim, Pass
from fish.observation import Observation
from fish.agents import AGENT_REGISTRY
from fish.beliefs import BeliefState


def hdr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


RULES = RuleConfig()

hdr("1+2. from_components round-trip and Observation legality agreement")
turn_changed = crashes = disagree = 0
checked = 0
for g in range(10):
    state = GameState.deal(RULES, seed=77 + g)
    initial = [state.hands[p] for p in range(6)]
    agents = [AGENT_REGISTRY["memory"]() for _ in range(6)]
    rng = random.Random(g)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, rng.getrandbits(64))
    while not state.is_terminal:
        try:
            rt = GameState.from_components(RULES, list(state.hands),
                                           state.turn, list(state.set_winner))
            if rt.turn != state.turn:
                turn_changed += 1
        except Exception as e:
            crashes += 1
            if crashes <= 2:
                print("   from_components crash:", type(e).__name__, e)
        for seat in range(6):
            o = Observation.from_state(state, seat)
            if (sorted(o.legal_asks(), key=repr)
                    != sorted(state.legal_asks(seat), key=repr)
                    or sorted(o.legal_passes(), key=repr)
                    != sorted(state.legal_passes(seat), key=repr)
                    or o.claimable_half_suits() != state.claimable_half_suits(seat)
                    or o.must_claim() != state.must_claim(seat)):
                disagree += 1
            checked += 1
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    # terminal state round-trip
    try:
        GameState.from_components(RULES, list(state.hands), state.turn,
                                  list(state.set_winner))
    except Exception as e:
        crashes += 1
        if crashes <= 3:
            print("   TERMINAL from_components crash:", type(e).__name__, e)
print("  seat-checks:", checked, " legality disagreements:", disagree)
print("  from_components turn changes:", turn_changed, " crashes:", crashes)

hdr("3. TunedAgent kwargs")
print("  ProbabilisticAgent:",
      list(inspect.signature(AGENT_REGISTRY["probabilistic"]).parameters))
print("  TunedAgent        :",
      list(inspect.signature(AGENT_REGISTRY["tuned"]).parameters))
try:
    AGENT_REGISTRY["tuned"](tablebase_max_cards=6)
    print("  tuned(tablebase_max_cards=6) OK")
except TypeError as e:
    print("  tuned(tablebase_max_cards=6) -> TypeError:", e)

hdr("4. ExactEndgameMixin exception handling")
src = inspect.getsource(
    __import__("fish.agents.tablebase", fromlist=["x"]).ExactEndgameMixin)
for line in src.splitlines():
    if "except" in line:
        print("   ", line.strip())
print("  `except (SubgameTooLarge, Exception)` == `except Exception`:")
print("   any solver bug (e.g. the KeyError in A06) silently disables the")
print("   tablebase instead of surfacing.")

hdr("5. BeliefState._pinned_count")
import fish.beliefs as B
src = inspect.getsource(B)
uses = [l.strip() for l in src.splitlines() if "_pinned_count" in l]
print("  occurrences:")
for u in uses:
    print("   ", u)
print("  -> written in __init__/_pin/_exclude, never read: dead state, and")
print("     _exclude's increment is wrong anyway when the survivor was already")
print("     counted. Harmless because nothing consumes it.")

hdr("6. do shipped agents ever CLAIM while cardless?")
count = 0
for g in range(15):
    for name in ("random", "heuristic", "memory", "probabilistic"):
        state = GameState.deal(RULES, seed=900 + g)
        agents = [AGENT_REGISTRY[name]() for _ in range(6)]
        rng = random.Random(g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, rng.getrandbits(64))
        n = 0
        while not state.is_terminal and n < 600:
            p = state.turn
            act = agents[p].act(Observation.from_state(state, p))
            if isinstance(act, Claim) and state.hands[p] == 0:
                count += 1
            state.apply(p, act)
            n += 1
print("  cardless claims emitted by shipped agents:", count)
print("  (engine ALLOWS them: check_legal(Claim) never looks at the hand)")
