"""The tempo term's regime gate must be off, and must scale only what it says.

`askfeat.py` charges every candidate ask `w_turn * (1 - p) * turn_risk[t]`,
with no dependence on what the turn is worth. The paper measured a turn at
about zero below p_best = 0.50 and about +0.45 above it, and 57% of ask
decisions sit below that line. `turn_free_below` scales the tempo column down
when the ask the incumbent objective would have chosen is in the free regime.

Three properties. The default must be inert. Armed, it must change play --
without which the first proves nothing. And it must alter EXACTLY ONE weight:
the two-pass structure re-scores with a modified AskWeights, and a mistake
there would silently move every other term as well, which no duel would ever
attribute correctly.
"""

import os
import random
import sys
from dataclasses import replace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4 import agent4 as A4
from fish4.askfeat import AskWeights
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = {"wrong_distribution_outcome": "opponent"}
BASE = dict(V06_DEPLOYED[1])
#: the shipped w_turn, read off the agent rather than written down twice
BASE_TURN = make_agent(V06_DEPLOYED).weights.turn


def _play(params, seed):
    rules = RuleConfig(**RULES)
    agents = [make_agent(("fishbot4", params)) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    rng = random.Random(seed + 7)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, rng.getrandbits(64))
    moves = []
    for _ in range(400):
        if st.is_terminal:
            break
        p = st.turn
        act = agents[p].act(Observation.from_state(st, p))
        moves.append((p, repr(act)))
        st.apply(p, act)
    return moves, list(st.set_winner)


def test_the_default_changes_nothing():
    for seed in range(4):
        a, wa = _play(dict(BASE), 9_500 + seed)
        b, wb = _play(dict(BASE, turn_free_below=0.0, turn_free_scale=0.0),
                      9_500 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: turn_free_below=0 changed the game")
        assert len(a) > 20


def test_arming_it_changes_play():
    changed = 0
    for seed in range(4):
        a, _ = _play(dict(BASE), 9_500 + seed)
        c, _ = _play(dict(BASE, turn_free_below=0.50, turn_free_scale=0.0),
                     9_500 + seed)
        if a != c:
            changed += 1
    assert changed, "arming turn_free_below=0.50 changed no game in 4"


def test_it_rescales_the_tempo_weight_and_nothing_else():
    """The second pass must differ from the first in exactly one field.

    A `replace` that touched another weight would be invisible in play and
    catastrophic in interpretation: the duel would be attributed to tempo
    while measuring something else entirely.
    """
    seen = []
    real = A4.score_asks

    def spy(ctx, asks, wts):
        seen.append(wts)
        return real(ctx, asks, wts)

    A4.score_asks = spy
    try:
        _play(dict(BASE, turn_free_below=0.50, turn_free_scale=0.0), 9_500)
    finally:
        A4.score_asks = real

    # Pair WITHIN a decision, not across the boundary. Consecutive entries in
    # `seen` can be (second pass of decision N, first pass of decision N+1),
    # which is the rescale running backwards; the first version of this test
    # caught those and failed on the code being right.
    pairs = [(a, b) for a, b in zip(seen, seen[1:])
             if a.turn == BASE_TURN and b.turn == BASE_TURN * 0.0]
    assert pairs, ("the tempo column was never re-weighted, so the two-pass "
                   "branch never ran and this test proves nothing")
    for before, after in pairs:
        assert after == replace(before, turn=after.turn), (
            f"the second pass changed more than the tempo weight:\n"
            f"  before {before}\n  after  {after}")
        assert after.turn == before.turn * 0.0


def test_half_weight_is_half_weight():
    seen = []
    real = A4.score_asks

    def spy(ctx, asks, wts):
        seen.append(wts)
        return real(ctx, asks, wts)

    A4.score_asks = spy
    try:
        _play(dict(BASE, turn_free_below=0.50, turn_free_scale=0.5), 9_500)
    finally:
        A4.score_asks = real
    pairs = [(a, b) for a, b in zip(seen, seen[1:])
             if a.turn == BASE_TURN and abs(b.turn - BASE_TURN * 0.5) < 1e-12]
    assert pairs, "the branch never fired at scale 0.5"
    for before, after in pairs:
        assert abs(after.turn - before.turn * 0.5) < 1e-12
