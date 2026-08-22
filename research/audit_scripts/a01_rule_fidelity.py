"""A01: rule-fidelity probes against SPEC.md sections 4.1-4.5 and 7."""
import sys, traceback
sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState, Ask, Claim, Pass, IllegalAction, NULL_TEAM
from fish.cards import half_suit_mask

R = RuleConfig()

def hdr(t):
    print("\n" + "=" * 70); print(t); print("=" * 70)

# ---------------------------------------------------------------- 1
hdr("1. May a player CLAIM a half-suit in which they hold no cards?")
hands = [0] * 6
# hs0 entirely with players 0 and 2 (team 0); player 4 (team 0) holds nothing of it
for c in range(0, 3):
    hands[0] |= 1 << c
for c in range(3, 6):
    hands[2] |= 1 << c
# give everyone else some other cards so the state is legal-ish
for i, c in enumerate(range(6, 12)):
    hands[[1, 3, 5, 1, 3, 5][i]] |= 1 << c
st = GameState(R, list(hands), turn=4)
for hs in range(2, 9):
    st.set_winner[hs] = NULL_TEAM
print("player 4 hand:", bin(st.hands[4]), "claimable:", st.claimable_half_suits(4))
try:
    ev = st.apply(4, Claim(0, (0, 0, 0, 2, 2, 2)))
    print("  ACCEPTED. event:", ev)
except IllegalAction as e:
    print("  rejected:", e)

# ---------------------------------------------------------------- 2
hdr("2. May a CARDLESS on-move player CLAIM instead of PASS? (SPEC 4.3 'Required')")
hands = [0] * 6
for c in range(0, 6):
    hands[2] |= 1 << c          # teammate of 0 holds all of hs0
hands[1] |= 1 << 6
hands[3] |= 1 << 7
st = GameState(R, list(hands), turn=0)
for hs in range(2, 9):
    st.set_winner[hs] = NULL_TEAM
print("turn after normalize:", st.turn, "hand_counts:", st.hand_counts())
print("legal_passes(0):", st.legal_passes(0))
try:
    st.check_legal(0, Claim(0, (2,) * 6))
    print("  Claim by cardless on-move player is LEGAL per check_legal")
except IllegalAction as e:
    print("  rejected:", e)

# ---------------------------------------------------------------- 3
hdr("3. from_components on a TERMINAL state (all resolved, all hands empty)")
try:
    st = GameState.from_components(R, [0] * 6, 0, [0] * 9)
    print("  ok, terminal:", st.is_terminal)
except Exception as e:
    print("  RAISED", type(e).__name__, ":", e)
    traceback.print_exc(limit=3)

# ---------------------------------------------------------------- 4
hdr("4. __init__ _normalize_turn runs BEFORE set_winner is known")
# state: hs0 live with cards only at seat 1; seats 0,2,4 cardless; turn=0
hands = [0] * 6
hands[1] = half_suit_mask(0)
st = GameState.from_components(R, hands, 0, [None] + [NULL_TEAM] * 8)
print("  turn:", st.turn, "(SPEC 4.4: next opponent clockwise with cards = 1)")

# ---------------------------------------------------------------- 5
hdr("5. Endgame: one team cardless -> other team must claim out")
hands = [0] * 6
hands[0] = 0b000111          # 3 cards of hs0
hands[2] = 0b111000          # other 3 of hs0
st = GameState(R, list(hands), turn=0)
for hs in range(1, 9):
    st.set_winner[hs] = NULL_TEAM
print("  legal_asks(0):", st.legal_asks(0))
print("  must_claim(0):", st.must_claim(0))
ev = st.apply(0, Claim(0, (0, 0, 0, 2, 2, 2)))
print("  claim ->", ev, "terminal:", st.is_terminal, "scores:", st.scores())

# ---------------------------------------------------------------- 6
hdr("6. Wrong-distribution nulling and opponent-holds detection")
for decl, label in [((0, 0, 0, 2, 2, 2), "exact"),
                    ((0, 0, 2, 0, 2, 2), "team but wrong split"),
                    ((0, 0, 0, 0, 2, 2), "wrong split 2")]:
    hands = [0] * 6
    hands[0] = 0b000111
    hands[2] = 0b111000
    st = GameState(R, list(hands), turn=0)
    for hs in range(1, 9):
        st.set_winner[hs] = NULL_TEAM
    ev = st.apply(0, Claim(0, decl))
    print(f"  {label:24s} declared={decl} revealed={ev.revealed} winner={ev.winner}")

# opponent holds one
hands = [0] * 6
hands[0] = 0b000111
hands[2] = 0b011000
hands[1] = 0b100000
st = GameState(R, list(hands), turn=0)
for hs in range(1, 9):
    st.set_winner[hs] = NULL_TEAM
ev = st.apply(0, Claim(0, (0, 0, 0, 2, 2, 2)))
print("  opponent holds one       winner =", ev.winner, "(expect 1)")

# ---------------------------------------------------------------- 7
hdr("7. Claim assignment type coercion / length / duplicates")
hands = [0] * 6
hands[0] = 0b111111
st = GameState(R, list(hands), turn=0)
for hs in range(1, 9):
    st.set_winner[hs] = NULL_TEAM
ev = st.apply(0, Claim(0, [0, 0, 0, 0, 0, 0]))   # list, not tuple
print("  list assignment ->", ev.winner, "(expect 0)")
