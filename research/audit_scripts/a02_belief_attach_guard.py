"""A02: is the 'attach at game start' guard in BeliefState.update real?"""
import sys, random
sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState, NULL_TEAM
from fish.observation import Observation
from fish.beliefs import BeliefState, BeliefContradiction
from fish.agents.memory import MemoryAgent
from fish.exact import information_is_resolved
from fish.cards import half_suit_mask

rules = RuleConfig()

print("== 1. the guard expression itself ==")
print("guard: `if not obs.history and dealt != self.n: raise`")
print("SPEC invariant 2 says sum(hand sizes) + 6*resolved == deck size ALWAYS.")
print("So `dealt != self.n` can never be true for any legal state -> dead guard.\n")

# demonstrate over many random truncations
bad = 0
for seed in range(30):
    state = GameState.deal(rules, seed=seed)
    agents = [MemoryAgent() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(60):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    if state.is_terminal:
        continue
    obs_full = Observation.from_state(state, state.turn)
    dealt = sum(obs_full.hand_counts) + 6 * sum(1 for w in obs_full.set_winner
                                                if w is not None)
    if dealt != 54:
        bad += 1
print(f"random truncations where `dealt != 54` (i.e. guard would fire): {bad}/30\n")

print("== 2. observer=None (spectator) mid-game attach: silent, no exception ==")
state = GameState.deal(rules, seed=5)
agents = [MemoryAgent() for _ in range(6)]
rng = random.Random(5)
for p, ag in enumerate(agents):
    ag.begin_game(p, rules, rng.getrandbits(64))
for _ in range(60):
    if state.is_terminal:
        break
    p = state.turn
    state.apply(p, agents[p].act(Observation.from_state(state, p)))
stripped = GameState.from_components(rules, list(state.hands), state.turn,
                                     list(state.set_winner))
obs = Observation.from_state(stripped, stripped.turn)
print("  resolved half-suits:", [i for i, w in enumerate(obs.set_winner)
                                 if w is not None])
bel = BeliefState(rules, observer=None)
try:
    bel.update(obs)
    print("  update() SUCCEEDED with a truncated transcript (no raise)")
except BeliefContradiction as e:
    print("  raised:", e)
# resolved cards should be dead, but are they?
res_hs = next(i for i, w in enumerate(obs.set_winner) if w is not None)
c = res_hs * 6
print(f"  current_holder_mask(card {c} of RESOLVED half-suit {res_hs}) = "
      f"{bel.current_holder_mask(c):06b}  (should be 000000)")
print("  known_current_hands:", [bin(h) for h in bel.known_current_hands()][:2], "...")

print("\n== 3. consequence: information_is_resolved() on ANY constructed endgame ==")
hands = [0] * 6
hands[0] = 0b000111
hands[2] = 0b111000
st = GameState(rules, list(hands), turn=0)
for hs in range(1, 9):
    st.set_winner[hs] = NULL_TEAM
print("  a 6-live-card endgame with all locations trivially public")
print("  information_is_resolved ->", information_is_resolved(st), "(want True)")

print("\n== 4. observer!=None mid-game attach when observer holds exactly `per` cards ==")
# craft: seat s still has 9 cards, some half-suits resolved
found = False
for seed in range(200):
    state = GameState.deal(rules, seed=seed)
    ags = [MemoryAgent() for _ in range(6)]
    r = random.Random(seed)
    for p, ag in enumerate(ags):
        ag.begin_game(p, rules, r.getrandbits(64))
    for _ in range(200):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, ags[p].act(Observation.from_state(state, p)))
        res = sum(1 for w in state.set_winner if w is not None)
        if res >= 1 and state.hand_count(state.turn) == 9 - 0:
            pass
        cnts = state.hand_counts()
        if res >= 1 and any(c == 9 for c in cnts):
            seat = cnts.index(9)
            stripped = GameState.from_components(rules, list(state.hands),
                                                 state.turn,
                                                 list(state.set_winner))
            o = Observation.from_state(stripped, seat)
            b = BeliefState(rules, observer=seat)
            try:
                b.update(o)
                print(f"  seed={seed}: seat {seat} holds 9 cards, "
                      f"{res} half-suit(s) resolved -> update() SUCCEEDED silently")
                cc = next(i for i, w in enumerate(o.set_winner)
                          if w is not None) * 6
                print(f"    belief says resolved card {cc} may be held by "
                      f"{b.current_holder_mask(cc):06b} (truth: nobody)")
                # and it will happily 'sample' resolved cards into hands
                w = b.sample_current_hands(random.Random(1))
                tot = sum(h.bit_count() for h in w)
                print(f"    sample_current_hands gives {tot} cards; "
                      f"true live cards = {sum(state.hand_counts())}")
                found = True
            except BeliefContradiction as e:
                pass
            break
    if found:
        break
if not found:
    print("  (no example found in 200 seeds)")
