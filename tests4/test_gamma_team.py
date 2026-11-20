"""gamma_team must be inert by default, live when set, and never collapse.

The bug this file exists for: `oppmodel.build` returned `(None, None)` whenever
`gamma == 0.0`, without consulting `gamma_team`. So the configuration "believe
nothing about opponents, something about teammates" silently produced the
UNIFORM posterior, and a whole row of the sweep grid in scripts4/gamma_split.py
reported bit-identical numbers for every gamma_team. That reads as a measured
null. It is a dead code path.

It is the second time this exact shape has bitten: the `> 0` guard on gamma used
to turn a negative gamma into gamma = 0, collapsing one experiment arm into
another and reporting the collapse as a result.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                     # noqa: E402
from fish.cards import NUM_PLAYERS                       # noqa: E402
from fish.engine import GameState                        # noqa: E402
from fish.observation import Observation                 # noqa: E402
from fish.rules import RuleConfig                        # noqa: E402
from fish4.oppmodel import build                         # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent     # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _mid_game(seed=520_000, steps=24):
    """A position with enough asks in the log for the model to have slots."""
    agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 530_000 + p)
    bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
    for _ in range(steps):
        m = st.turn
        for q in range(NUM_PLAYERS):
            bels[q].update(Observation.from_state(st, q))
        st.apply(m, agents[m].act(Observation.from_state(st, m)))
    m = st.turn
    return Observation.from_state(st, m), bels[m], m


def _moves(kw, seed):
    agents = [make_agent(("kraken", dict(V06_DEPLOYED[1], **kw)))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 7000 + seed * 13 + p)
    out = []
    for _ in range(600):
        if st.is_terminal:
            break
        m = st.turn
        act = agents[m].act(Observation.from_state(st, m))
        out.append(repr(act))
        st.apply(m, act)
    return out


@pytest.mark.parametrize("seed", [3, 11])
def test_default_is_bit_identical(seed):
    """An unset knob must not perturb a single move."""
    base = _moves({}, seed)
    assert base == _moves({"gamma_team": None}, seed)


@pytest.mark.parametrize("seed", [3, 11])
def test_equal_gammas_are_bit_identical(seed):
    """gamma_team == gamma is the incumbent by construction, so prove it."""
    g = V06_DEPLOYED[1]["opponent_gamma"]
    assert _moves({}, seed) == _moves({"gamma_team": g}, seed)


def test_a_different_value_actually_changes_play():
    """A knob that cannot change anything is not a knob."""
    assert _moves({}, 3) != _moves({"gamma_team": 0.9}, 3)


def _weights_by_side(opp, card_slot, me):
    """(teammate weights, opponent weights). card_slot maps (player, card) to
    the slot index, which is the only public route from a seat to its slots."""
    team, other = set(), set()
    for (player, _card), i in card_slot.items():
        (team if (player % 2) == (me % 2) else other).add(i)
    return ([opp.weight[i] for i in sorted(team)],
            [opp.weight[i] for i in sorted(other)])


def test_teammate_slots_get_the_team_gamma():
    """The weight really is keyed on the side of the table, not on the seat."""
    obs, bel, me = _mid_game()
    opp, card_slot = build(bel, obs, 0.35, gamma_team=1.5)
    assert opp is not None
    team, other = _weights_by_side(opp, card_slot, me)
    assert team and other, "position exercised only one side"
    assert min(team) >= 1.5, (
        f"a teammate slot carries {min(team)}, which is the opponent gamma "
        f"rather than gamma_team")
    assert max(other) < 1.5


def test_gamma_team_is_live_when_gamma_is_zero():
    """THE REGRESSION. build() must not bail at gamma == 0 with a live
    gamma_team, or 'believe nothing about opponents, something about
    teammates' silently returns the uniform posterior."""
    obs, bel, me = _mid_game()
    opp, _cs = build(bel, obs, 0.0, gamma_team=1.5)
    assert opp is not None, (
        "build() returned None at gamma=0 with gamma_team=1.5 -- the "
        "teammate-only configuration has collapsed to the uniform posterior")
    team, other = _weights_by_side(opp, _cs, me)
    assert team and max(team) > 0.0, "teammate slots carry no weight"
    assert other and max(other) == 0.0, (
        "opponent slots carry weight at gamma=0; they must be exactly off")


def test_both_off_still_returns_none():
    """The genuine off switch must stay off."""
    obs, bel, _ = _mid_game()
    assert build(bel, obs, 0.0, gamma_team=None)[0] is None
    assert build(bel, obs, 0.0, gamma_team=0.0)[0] is None
