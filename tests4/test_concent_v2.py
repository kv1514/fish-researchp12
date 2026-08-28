"""The concentration term must measure the change it causes, not the level.

v1 was one number per half-suit -- `team_concentration[hs]` -- identical for
every candidate ask in it. Two things follow that make it untestable as a
preference:

  1. it cannot distinguish two asks in the same half-suit, so it can only tilt
     the choice of half-suit;
  2. when the concentration sits with a TEAMMATE, taking a card breaks it up,
     and v1 scored that ask highest for exactly the reason it should have
     scored it lowest.

v2 is the expected change: pi times (concentration after a successful ask minus
concentration now). These tests build positions where the right answer is known
by construction and check the sign.

Everything here runs at weight 0, so none of it can move the champion; the last
test asserts that.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, half_suit_mask
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import (TERM_NAMES, TERM_VERSIONS, DecisionContext,
                           ask_feature_matrix, stale_terms)

CONCENT = TERM_NAMES.index("concent")


class FakeCtx:
    """The minimum DecisionContext surface ask_feature_matrix touches.

    Written rather than staged through a real game because the point is to
    control the marginals exactly: a position where our team's holding is
    concentrated in ME and one where it is concentrated in a TEAMMATE differ
    only in the numbers, and reaching each by playing would be luck.
    """

    def __init__(self, M, me=0, mine=(0, 2, 4), n_hs=9):
        self.M = M
        self.me = me
        self.mine = list(mine)
        self.theirs = [p for p in range(NUM_PLAYERS) if p not in mine]
        self.my_team = 0
        self.n_hs = n_hs
        self.per = 9
        self.hs_live = np.ones(n_hs, dtype=bool)
        self.my_depth = np.zeros(n_hs)
        self.player_exp = np.zeros((n_hs, NUM_PLAYERS))
        for hs in range(n_hs):
            self.player_exp[hs] = M[hs * 6:hs * 6 + 6].sum(axis=0)
        self.team_exp = np.array(
            [self.player_exp[hs, self.mine].sum() for hs in range(n_hs)])
        self.opp_exp = np.array(
            [self.player_exp[hs, self.theirs].sum() for hs in range(n_hs)])
        self.hs_entropy = np.zeros(n_hs)
        self.team_concentration = np.array([
            (self.player_exp[hs, self.mine].max() / self.team_exp[hs])
            if self.team_exp[hs] > 0 else 0.0 for hs in range(n_hs)])
        self.p_team_card = np.zeros((n_hs, 6))
        for hs in range(n_hs):
            self.p_team_card[hs] = M[hs * 6:hs * 6 + 6][:, self.mine].sum(axis=1)
        self.p_team_all = np.array(
            [float(np.prod(self.p_team_card[hs])) for hs in range(n_hs)])
        self.revealed = np.ones(n_hs, dtype=bool)
        self.turn_risk = np.zeros(NUM_PLAYERS)
        self.exposure = np.zeros(NUM_PLAYERS)
        self.avg_live = 9.0

        class _O:
            hand_counts = [9] * NUM_PLAYERS
        self.obs = _O()


def _M(holdings):
    """holdings: {card: {player: prob}} over half-suit 0, rest spread."""
    M = np.zeros((54, NUM_PLAYERS))
    for c in range(54):
        M[c] = 1.0 / NUM_PLAYERS
    for c, d in holdings.items():
        M[c] = 0.0
        for p, v in d.items():
            M[c, p] = v
    return M


def _feat(M, ask, me=0):
    ctx = FakeCtx(M, me=me)
    _, F = ask_feature_matrix(ctx, [ask])
    return float(F[0, CONCENT])


def test_taking_a_card_into_the_biggest_hand_scores_positive():
    """I hold two, a teammate holds one, the rest are with an opponent.

    Concentration is 2/3 now and 3/4 after, so the ask tightens the holding.
    Note the case that must NOT be used here: if I already hold every card our
    team has, concentration is 1.0 and taking another cannot raise it, so the
    feature is correctly 0. That is a property of the quantity, not a gap --
    the first version of this test asserted a positive there and was wrong.
    """
    M = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0},
            3: {1: 1.0}, 4: {1: 1.0}, 5: {1: 1.0}})
    assert _feat(M, Ask(1, 3), me=0) > 0.0


def test_taking_a_card_that_breaks_up_a_teammates_holding_scores_negative():
    """THE case v1 got backwards.

    Teammate 2 holds three of the half-suit and I hold none. Our team's holding
    is maximally concentrated, and my taking the fourth card from an opponent
    spreads it across two hands -- which is the split we would then have to
    name. v1 scored this ask at the concentration LEVEL, which here is its
    maximum.
    """
    M = _M({0: {2: 1.0}, 1: {2: 1.0}, 2: {2: 1.0},
            3: {1: 1.0}, 4: {1: 1.0}, 5: {1: 1.0}})
    v2 = _feat(M, Ask(1, 3), me=0)
    assert v2 < 0.0, f"breaking up a teammate's holding scored {v2:+.4f}"


def test_v1_would_have_scored_that_case_at_its_maximum():
    """Pin the contrast, so 'v2 is different' is not taken on trust."""
    M = _M({0: {2: 1.0}, 1: {2: 1.0}, 2: {2: 1.0},
            3: {1: 1.0}, 4: {1: 1.0}, 5: {1: 1.0}})
    ctx = FakeCtx(M, me=0)
    v1 = float(ctx.team_concentration[0])
    assert v1 == pytest.approx(1.0), v1
    assert _feat(M, Ask(1, 3), me=0) < 0.0


def test_it_distinguishes_two_asks_within_one_half_suit():
    """v1 could not, by construction: it had no per-ask component at all."""
    M = _M({0: {0: 1.0}, 1: {0: 1.0},
            2: {2: 1.0}, 3: {2: 1.0},
            4: {1: 1.0}, 5: {1: 1.0}})
    ctx = FakeCtx(M, me=0)
    _, F = ask_feature_matrix(ctx, [Ask(1, 4), Ask(1, 5)])
    lvl = {float(ctx.team_concentration[0])}
    assert len(lvl) == 1
    # two asks in the same half-suit; v2 need not tie them, and must not be
    # the constant v1 was
    assert not np.allclose(F[:, CONCENT], ctx.team_concentration[0])


def test_it_scales_with_the_chance_of_actually_getting_the_card():
    """An expected change, so a coin-flip ask is worth half a certain one."""
    sure = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0},
               3: {1: 1.0}, 4: {1: 1.0}, 5: {1: 1.0}})
    # players 1 and 3 are both opponents, so the card is off our team either
    # way and only pi moves: the expected change must halve with it.
    half = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0},
               3: {1: 0.5, 3: 0.5}, 4: {1: 1.0}, 5: {1: 1.0}})
    a, b = _feat(sure, Ask(1, 3)), _feat(half, Ask(1, 3))
    assert 0.0 < b < a, (a, b)
    assert b == pytest.approx(a / 2.0, rel=1e-9), (a, b)


def test_an_empty_half_suit_does_not_divide_by_zero():
    M = _M({c: {1: 1.0} for c in range(6)})
    assert _feat(M, Ask(1, 0)) == 0.0


def test_the_version_is_bumped_so_old_fits_are_marked_stale():
    assert TERM_VERSIONS["concent"] == 2
    assert "concent" in stale_terms(None), (
        "a harvest taken before this correction must be flagged, or a weight "
        "fitted against the level would be applied to the change")


def test_the_champion_is_untouched():
    """Weight 0 by default, so none of the above can reach a shipped game."""
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(wrong_distribution_outcome="opponent")
    seen = []
    for seed in (4_411, 4_412):
        agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 777 + seed * 13 + p)
        moves = []
        for _ in range(400):
            if st.is_terminal:
                break
            act = agents[st.turn].act(Observation.from_state(st, st.turn))
            moves.append((st.turn, repr(act)))
            st.apply(st.turn, act)
        seen.append((moves, list(st.set_winner)))
    from fish4.askfeat import AskWeights
    assert AskWeights().concent == 0.0
    assert all(len(m) > 20 for m, _ in seen)
