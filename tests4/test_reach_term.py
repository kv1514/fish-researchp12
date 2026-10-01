"""`reach`: the entry point an ask spends.

WHAT IT IS FOR
--------------
results/forced_locus.json, 15,929 decisions with game stage controlled for: a
seat five of its own decisions from a `gate` or `forced` declaration has 6.9
FEWER live asks than a seat at the same cards-left, and 4.0 fewer at eight.
Those two paths carry 62 of 63 wrong declarations. And such a seat holds 0.6 to
0.9 MORE cards than the control -- it is not short of cards, it is short of
places to reach.

The term charges an ask for the probability that landing it closes the
half-suit as an entry point:

    reach = -pi * prod over the other five cards of (1 - P(an opponent holds it))

`test_it_charges_most_for_completing_a_half_suit_we_already_own` is the one to
read first: it is the whole claim, and it is also the term's biggest risk,
because that ask is the one that banks a set.

Everything here runs at weight 0 in the shipped configuration and the last test
asserts the champion is bit-identical there.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import (TERM_NAMES, TERM_VERSIONS, ask_feature_matrix,
                           stale_terms)
from tests4.test_concent_v2 import FakeCtx

REACH = TERM_NAMES.index("reach")


def _M(holdings):
    M = np.zeros((54, NUM_PLAYERS))
    for c in range(54):
        M[c] = 1.0 / NUM_PLAYERS
    for c, d in holdings.items():
        M[c] = 0.0
        for p, v in d.items():
            M[c, p] = v
    return M


def _feat(M, ask, hand=0):
    ctx = FakeCtx(M, me=0)
    ctx.obs.hand = hand
    _, F = ask_feature_matrix(ctx, [ask])
    return float(F[0, REACH])


def _mask(cards):
    m = 0
    for c in cards:
        m |= 1 << c
    return m


def test_it_charges_most_for_completing_a_half_suit_we_already_own():
    """THE CLAIM, and the term's biggest risk in one position.

    Our team holds five of the half-suit and opponent 1 holds the sixth.
    Taking it completes the set -- and closes the half-suit as somewhere we can
    ever ask again. The term charges the full price here, and that is exactly
    the ask that banks a set, so the weight is a real trade and only a duel
    prices it.
    """
    M = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0}, 3: {2: 1.0}, 4: {4: 1.0},
            5: {1: 1.0}})
    v = _feat(M, Ask(1, 5), hand=_mask([0, 1]))
    assert v == pytest.approx(-1.0), v


def test_it_charges_almost_nothing_when_opponents_still_hold_plenty():
    """The same card taken out of a half-suit that stays wide open."""
    M = _M({0: {0: 1.0}, 1: {1: 1.0}, 2: {3: 1.0}, 3: {5: 1.0}, 4: {1: 1.0},
            5: {1: 1.0}})
    v = _feat(M, Ask(1, 5), hand=_mask([0]))
    assert -0.01 < v <= 0.0, v


def test_it_is_a_cost_and_never_a_reward():
    """Signed negative, so a positive weight penalises. A term that could pay
    for spending an entry point would be the opposite of the finding."""
    rng = np.random.default_rng(7)
    for _ in range(30):
        M = rng.random((54, NUM_PLAYERS))
        M /= M.sum(axis=1)[:, None]
        ctx = FakeCtx(M, me=0)
        ctx.obs.hand = _mask(range(0, 54, 7))
        asks = [Ask(1, c) for c in range(6, 12)]
        _, F = ask_feature_matrix(ctx, asks)
        assert (F[:, REACH] <= 1e-12).all()


def test_it_scales_with_the_chance_the_ask_lands():
    sure = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0}, 3: {2: 1.0},
               4: {4: 1.0}, 5: {1: 1.0}})
    half = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0}, 3: {2: 1.0},
               4: {4: 1.0}, 5: {1: 0.5, 3: 0.5}})
    a = _feat(sure, Ask(1, 5), hand=_mask([0, 1]))
    b = _feat(half, Ask(1, 5), hand=_mask([0, 1]))
    assert a < b < 0.0, (a, b)
    assert b == pytest.approx(a / 2.0, rel=1e-9), (a, b)


def test_the_asked_card_is_excluded_from_the_product():
    """We hold it either way once the ask lands, so it cannot keep the
    half-suit open for us. Including it would zero the term precisely on a
    certain steal -- the bug `claim`, `concent` and `locate` all had at v1."""
    M = _M({0: {0: 1.0}, 1: {0: 1.0}, 2: {2: 1.0}, 3: {2: 1.0}, 4: {4: 1.0},
            5: {1: 1.0}})
    assert _feat(M, Ask(1, 5), hand=_mask([0, 1])) == pytest.approx(-1.0)


def test_the_version_is_bumped_so_the_divided_shape_is_marked_stale():
    assert TERM_VERSIONS["reach"] == 2
    assert "reach" in stale_terms(None)


def test_the_champion_is_bit_identical_at_zero():
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.askfeat import AskWeights
    assert AskWeights().reach == 0.0
    assert V06_DEPLOYED[1].get("w_reach", 0.0) == 0.0
    rules = RuleConfig(wrong_distribution_outcome="opponent")

    def play(seed, extra):
        agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1], **extra)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 7_700 + seed * 13 + p)
        moves = []
        for _ in range(400):
            if st.is_terminal:
                break
            act = agents[st.turn].act(Observation.from_state(st, st.turn))
            moves.append((st.turn, repr(act)))
            st.apply(st.turn, act)
        return moves, list(st.set_winner)

    for seed in (7_001, 7_002):
        a = play(seed, {})
        assert a == play(seed, {"w_reach": 0.0})
        assert len(a[0]) > 20
