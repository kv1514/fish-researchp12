"""Declarability at the lookahead's leaf: the shape tests.

WHAT THIS TERM HAS TO DO THAT NOTHING ELSE DOES
-----------------------------------------------
The possession chain counts CARDS. Two asks that each bank one card are worth
the same to it, and the project's error ledger says that is exactly the blind
spot: 0.1676 of our 0.1759 wrong declarations a game are ALLOCATION class --
our team held all six of a half-suit and we named the wrong split -- against
0.0083 ownership errors. The card that completes a half-suit our team can name
is worth more than the card that does not, and until now nothing in the search
could tell them apart.

`test_it_prefers_the_card_that_completes_a_declarable_half_suit` is that claim
in one position, and it is the test to read first: the cards-only bonus is
indifferent between the two asks by construction, and the declare-weighted one
must not be.

Everything here runs at w_declare = 0 in the shipped configuration, and the
last test asserts the champion is bit-identical there.
"""

from __future__ import annotations

import os
import random
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.lookahead import (ChainState, declarability, lookahead_bonus,
                             possession_value)

TEAM0 = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(0)]


class FakeObs:
    """The four attributes lookahead_bonus reads off an Observation."""

    def __init__(self, hand, counts, player, n_hs=9):
        self.hand = hand
        self.hand_counts = list(counts)
        self.player = player
        self.set_winner = [None] * n_hs

        class _R:
            allow_bluff_asks = False
        self.rules = _R()


class FakeCtx:
    def __init__(self, M, hand, counts, player=0, n_hs=9):
        self.M = M
        self.n_hs = n_hs
        self.obs = FakeObs(hand, counts, player, n_hs)


def _mask(cards):
    m = 0
    for c in cards:
        m |= 1 << c
    return m


def _uniform_M():
    return np.full((54, NUM_PLAYERS), 1.0 / NUM_PLAYERS)


def _pin(M, card, player):
    M[card] = 0.0
    M[card, player] = 1.0


# -- the quantity ------------------------------------------------------------

def test_declarability_is_ownership_only_when_the_split_is_known():
    """max-over-team equals sum-over-team exactly when mass sits on one seat.

    This is the whole distinction between this term and `claim`. A half-suit
    our team certainly owns but splits 50/50 between two teammates on every
    card is a POSITION WE LOSE FROM: ownership 1.0, declarability 1/64.
    """
    live = [True] + [False] * 8
    known = _uniform_M()
    for c in range(6):
        _pin(known, c, 2)
    split = _uniform_M()
    for c in range(6):
        split[c] = 0.0
        split[c, 0] = split[c, 2] = 0.5
    own_known = float(np.prod([known[c, TEAM0].sum() for c in range(6)]))
    own_split = float(np.prod([split[c, TEAM0].sum() for c in range(6)]))
    assert own_known == pytest.approx(1.0)
    assert own_split == pytest.approx(1.0), "both are certainly ours"
    assert declarability(known, TEAM0, live, 9) == pytest.approx(1.0)
    assert declarability(split, TEAM0, live, 9) == pytest.approx(1 / 64)


def test_one_certain_opponent_card_zeroes_the_half_suit():
    live = [True] + [False] * 8
    M = _uniform_M()
    for c in range(5):
        _pin(M, c, 0)
    _pin(M, 5, 1)
    assert declarability(M, TEAM0, live, 9) == 0.0


def test_a_resolved_half_suit_contributes_nothing():
    M = _uniform_M()
    for c in range(6):
        _pin(M, c, 0)
    assert declarability(M, TEAM0, [True] + [False] * 8, 9) == pytest.approx(1.0)
    assert declarability(M, TEAM0, [False] * 9, 9) == 0.0


# -- the discrimination that is the point ------------------------------------

def _two_ask_position():
    """Two asks, one card each, same probability, different declarations.

    Half-suit 0: I hold five of six for certain. The sixth is a coin flip
    between opponents 1 and 3.
    Half-suit 1: I hold one. A second is the same coin flip. Opponent 3
    certainly holds the other four, so this half-suit can never be declared by
    us at all.

    Asking opponent 1 for either missing card lands with probability 0.5 and
    banks exactly one card, and the cards-only chain scores them EXACTLY
    equally -- the assertion below is `==`, not a tolerance.

    WHY THE PROBABILITY HAS TO BE BELOW ONE, and this is worth reading because
    the first version of this test got it wrong. With both asks certain the
    chain takes both cards whichever order it starts in, so the two orderings
    end at the same declarability and the term ties them -- correctly. What
    securing a declarable half-suit FIRST buys is that it needs less to go
    right: at probability p the ordering is worth w * G * p * (1 - p), which is
    zero at p = 1 and maximal at a coin flip. A test that asserted a preference
    at p = 1 was asserting a bug.

    The hand counts are synthetic (opponent 3 holds most of the deck) so the
    two half-suits above are the only live business in the position.
    """
    M = np.zeros((54, NUM_PLAYERS))
    for c in range(5):
        _pin(M, c, 0)
    M[5, 1] = M[5, 3] = 0.5
    _pin(M, 6, 0)
    M[7, 1] = M[7, 3] = 0.5
    for c in range(8, 12):
        _pin(M, c, 3)
    for c in range(12, 54):
        _pin(M, c, 5)
    return (FakeCtx(M, _mask([0, 1, 2, 3, 4, 6]), [6, 2, 0, 46, 0, 0]),
            [Ask(1, 5), Ask(1, 7)])


def test_the_cards_only_chain_cannot_see_the_difference():
    """The blind spot, pinned first so the fix is not taken on trust."""
    ctx, asks = _two_ask_position()
    b = lookahead_bonus(ctx, asks, depth=3, beam=4)
    assert b[0] == b[1], (
        f"one card banked either way: the possession chain is indifferent by "
        f"construction, got {b[0]:.6f} vs {b[1]:.6f}")


def test_it_prefers_the_card_that_completes_a_declarable_half_suit():
    ctx, asks = _two_ask_position()
    cards_only = lookahead_bonus(ctx, asks, depth=3, beam=4)
    with_declare = lookahead_bonus(ctx, asks, depth=3, beam=4, w_declare=1.0)
    gain = with_declare - cards_only
    assert gain[0] > 0.4, (
        f"completing a nameable half-suit should be worth a large fraction of "
        f"a set, got {gain[0]:+.4f}")
    assert gain[1] < 0.05, (
        f"the other half-suit has four certain opponent cards in it and can "
        f"never be ours, so it must earn nothing, got {gain[1]:+.4f}")
    assert with_declare[0] - with_declare[1] > 0.4


def test_certain_asks_are_tied_because_ordering_cannot_matter_there():
    """The term does not invent a preference where none exists.

    Make both coin flips certain. Now the chain takes both cards in either
    order and ends in the same place, so a preference between them would be
    the term reading noise into a position that has none.
    """
    ctx, asks = _two_ask_position()
    _pin(ctx.M, 5, 1)
    _pin(ctx.M, 7, 1)
    b = lookahead_bonus(ctx, asks, depth=3, beam=4, w_declare=1.0)
    assert b[0] == pytest.approx(b[1], abs=1e-9), (
        f"both orderings reach the same cards and the same declarability: "
        f"{b[0]:.6f} vs {b[1]:.6f}")


# -- invariants --------------------------------------------------------------

def test_depth_one_is_still_identically_zero_at_any_declare_weight():
    """The one-ply version is refused, not merely unused.

    prereg/locate_term.md measured an additively weighted one-ply declaration
    feature over 3,000 pairs and closed the family. A knob that let this be run
    at depth 1 would invite that same run again.
    """
    ctx, asks = _two_ask_position()
    for w in (0.0, 0.5, 2.0):
        assert not lookahead_bonus(ctx, asks, depth=1, w_declare=w).any()
        assert not lookahead_bonus(ctx, asks, depth=0, w_declare=w).any()


def test_zero_weight_reproduces_the_cards_only_bonus_exactly():
    ctx, asks = _two_ask_position()
    a = lookahead_bonus(ctx, asks, depth=3, beam=4)
    b = lookahead_bonus(ctx, asks, depth=3, beam=4, w_declare=0.0)
    assert np.array_equal(a, b)


def test_declarability_never_falls_along_a_successful_chain():
    """The property the >= 0 initialisation in possession_value relies on.

    A taken card's row becomes a point mass on us, and the quota rebalance
    divides every row by a total below one -- which can only raise a teammate's
    entry. Asserted over random positions rather than argued, because if it
    ever failed the search would silently prefer chains it should avoid.
    """
    rng = random.Random(4_242)
    for _ in range(40):
        M = np.array([[rng.random() for _ in range(NUM_PLAYERS)]
                      for _ in range(54)])
        M /= M.sum(axis=1)[:, None]
        st = ChainState(M, _mask(range(0, 54, 7)), [9] * NUM_PLAYERS, 0,
                        [True] * 9, 9)
        prev = st.declarability()
        for _ in range(5):
            asks = st.legal_asks()
            if not asks:
                break
            t, c = asks[rng.randrange(len(asks))]
            st.apply_success(t, c)
            now = st.declarability()
            assert now >= prev - 1e-12, f"{prev:.6f} -> {now:.6f}"
            prev = now


def test_deeper_search_finds_more_declarability_than_shallower():
    """The compounding claim: this is what a feature could not do.

    A chain that needs two asks to make a half-suit nameable is invisible at
    depth 2 and visible at depth 3, and the whole reason to put the quantity in
    the search rather than in the ask basis is that it can see such chains.
    """
    M = _uniform_M()
    for c in range(4):
        _pin(M, c, 0)
    _pin(M, 4, 1)
    _pin(M, 5, 1)
    for c in range(6, 54):
        _pin(M, c, 3)
    _pin(M, 6, 0)
    ctx = FakeCtx(M, _mask([0, 1, 2, 3, 6]), [5, 9, 8, 24, 4, 4])
    asks = [Ask(1, 4)]
    g2 = lookahead_bonus(ctx, asks, depth=2, beam=4, w_declare=1.0)[0]
    g3 = lookahead_bonus(ctx, asks, depth=3, beam=4, w_declare=1.0)[0]
    assert g3 > g2 + 0.5, (
        f"the second card of the pair is only reachable at depth 3: "
        f"depth2 {g2:.4f}, depth3 {g3:.4f}")


def test_possession_value_stays_non_negative():
    rng = random.Random(99)
    M = np.array([[rng.random() for _ in range(NUM_PLAYERS)]
                  for _ in range(54)])
    M /= M.sum(axis=1)[:, None]
    st = ChainState(M, _mask(range(0, 54, 6)), [9] * NUM_PLAYERS, 0,
                    [True] * 9, 9)
    for w in (0.0, 0.5, 3.0):
        assert possession_value(st, 3, 4, False, w) >= 0.0


def test_a_chain_cannot_disambiguate_two_teammates():
    """THE STRUCTURAL LIMIT, and it is a property of the search space itself.

    ``apply_success`` collapses the taken card's row to a point mass on us and
    then runs one proportional-fitting sweep: scale the TARGET's column by a
    constant, divide each row by its total. Both operations preserve ratios
    among the non-target entries of a row, and the target is always an
    opponent. So for any two teammates t1, t2 and any card the chain does not
    itself take::

        M[c, t1] / M[c, t2]  is invariant under the entire tree

    at every depth and every beam width. A possession chain therefore resolves
    allocation uncertainty on exactly the cards it takes -- at most `depth` of
    them -- and on nothing else in the deal.

    That holds for ANY leaf evaluation, a perfect one included, which is why it
    is the honest bound on what `w_declare` could ever have been worth: 0.1676
    of our 0.1759 wrong declarations a game are allocation class, and the
    search cannot see most of that however it scores its leaves.
    """
    rng = random.Random(11)
    mates = [p for p in range(NUM_PLAYERS)
             if team_of(p) == team_of(0) and p != 0]
    worst = 0.0
    for _ in range(30):
        M = np.array([[rng.random() for _ in range(NUM_PLAYERS)]
                      for _ in range(54)])
        M /= M.sum(axis=1)[:, None]
        st = ChainState(M, _mask(range(0, 54, 5)), [9] * NUM_PLAYERS, 0,
                        [True] * 9, 9)
        before = st.M.copy()
        taken = []
        for _ in range(3):
            asks = st.legal_asks()
            if not asks:
                break
            t, c = asks[rng.randrange(len(asks))]
            st.apply_success(t, c)
            taken.append(c)
        assert taken, "the position must offer the chain something to take"
        for c in range(54):
            if c in taken:
                continue
            r0 = before[c, mates[0]] / max(before[c, mates[1]], 1e-300)
            r1 = st.M[c, mates[0]] / max(st.M[c, mates[1]], 1e-300)
            worst = max(worst, abs(r1 - r0) / max(r0, 1e-12))
    assert worst < 1e-12, (
        f"a chain moved a teammate/teammate ratio by {worst:.3e}; if this ever "
        f"becomes false the closure argument in prereg/declarability_leaf.md "
        f"no longer holds and the direction reopens")


def test_the_chain_does_resolve_the_card_it_takes():
    """The other half of the theorem, so it is a limit and not a no-op."""
    M = _uniform_M()
    st = ChainState(M, _mask([0, 1]), [9] * NUM_PLAYERS, 0, [True] * 9, 9)
    assert st.M[2].max() < 0.9
    st.apply_success(1, 2)
    assert st.M[2, 0] == pytest.approx(1.0)


# -- the ablation ------------------------------------------------------------

def test_the_champion_is_bit_identical_at_zero():
    from fish4.registry4 import V06_DEPLOYED, make_agent
    assert V06_DEPLOYED[1].get("lookahead_declare", 0.0) == 0.0
    rules = RuleConfig(wrong_distribution_outcome="opponent")

    def play(seed, extra):
        agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1], **extra)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 6_100 + seed * 13 + p)
        moves = []
        for _ in range(400):
            if st.is_terminal:
                break
            act = agents[st.turn].act(Observation.from_state(st, st.turn))
            moves.append((st.turn, repr(act)))
            st.apply(st.turn, act)
        return moves, list(st.set_winner)

    for seed in (6_001, 6_002):
        a = play(seed, {})
        b = play(seed, {"lookahead_declare": 0.0})
        assert a == b
        assert len(a[0]) > 20


def test_the_score_recorder_is_off_in_every_shipped_path():
    import fish4.agent4 as A
    assert A._SCORE_RECORDER is None
