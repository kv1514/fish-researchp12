"""The endgame-only ask weights must change nothing until they are asked to.

A knob that shifts the champion's play when it is set to its default is not a
knob, it is a regression, and every number in the paper was measured against
the champion. So the first test is that the default play is bit-identical --
not close, identical -- over whole games.

The second is that the knob fires when it should and only when it should: at
most ``endgame_m`` live half-suits, never above. A switch that never fires
would pass the first test perfectly.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35}


def _play(params, seed):
    rules = RuleConfig()
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
        a, wa = _play(dict(BASE), 3_000 + seed)
        b, wb = _play(dict(BASE, endgame_m=0, endgame_d_info=2.0,
                           endgame_d_certain=-0.5), 3_000 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: endgame_m=0 changed the game, so the knob is not "
            f"off by default")
        assert len(a) > 20, f"seed {seed} produced only {len(a)} moves"


def test_the_knob_fires_only_in_the_endgame():
    """Setting it must change SOME game, and only after the endgame starts."""
    changed = 0
    for seed in range(6):
        a, _ = _play(dict(BASE), 3_100 + seed)
        b, _ = _play(dict(BASE, endgame_m=2, endgame_d_certain=-0.5),
                     3_100 + seed)
        if a != b:
            changed += 1
            # The first divergence must come from a position with at most two
            # live half-suits. Replaying the shared prefix is how that is
            # checked without trusting the agent to report it.
            i = next(k for k in range(min(len(a), len(b))) if a[k] != b[k])
            rules = RuleConfig()
            st = GameState.deal(rules, seed=3_100 + seed)
            for p, mv in a[:i]:
                acts = {repr(x): x for x in _legal(st, p)}
                st.apply(p, acts[mv])
            live = sum(1 for x in st.set_winner if x is None)
            assert live <= 2, (
                f"seed {seed}: play first differs at {live} live half-suits, "
                f"which is above the endgame_m=2 the knob was given")
    assert changed >= 1, (
        "setting the endgame weights changed no game at all, so the switch "
        "never fires and the first test passes for the wrong reason")


def _legal(st, p):
    obs = Observation.from_state(st, p)
    if obs.must_pass():
        return list(obs.legal_passes())
    out = list(obs.legal_asks())
    out += list(_claims(st, p))
    return out


def _claims(st, p):
    from fish.cards import CARDS_PER_HALF_SUIT, team_of
    from fish.engine import Claim
    for h, w in enumerate(st.set_winner):
        if w is not None:
            continue
        base = h * CARDS_PER_HALF_SUIT
        holders = tuple(st.holder_of(base + i)
                        for i in range(CARDS_PER_HALF_SUIT))
        if all(x is not None for x in holders):
            yield Claim(h, holders)
