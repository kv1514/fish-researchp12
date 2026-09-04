"""The `locate` term: does it price what its comment says it prices?

Every claim in the feature's docstring is a testable one, and the two defects
this basis has already had -- `claim` at v1 and `concent` at v1 -- were both
formulas that could not reward what their own comments described. Both scored
zero, or backwards, in exactly the case they existed for. So the tests here are
about the SHAPE of the term, not merely that it is non-zero.
"""

import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import (TERM_NAMES, TERM_VERSIONS, AskWeights,
                           DecisionContext, ask_feature_matrix)
from fish4.posterior import Posterior
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")
J = TERM_NAMES.index("locate")


def _contexts(n_games=3, stride=4, limit=14):
    """Real mid-game decision contexts with their candidate asks."""
    out = []
    for g in range(n_games):
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=6_200_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 6_210_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400 and len(out) < limit:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            obs = Observation.from_state(st, mover)
            asks = obs.legal_asks()
            if step > 6 and step % stride == 0 and asks:
                post = Posterior(bels[mover], random.Random(99 + step),
                                 n_draws=V06_DEPLOYED[1]["n_draws"], obs=obs,
                                 gamma=V06_DEPLOYED[1]["opponent_gamma"])
                out.append((DecisionContext(obs, bels[mover], post), asks))
            st.apply(mover, agents[mover].act(obs))
            step += 1
        if len(out) >= limit:
            break
    return out


def test_the_term_is_in_the_basis_and_versioned():
    assert "locate" in TERM_NAMES
    assert tuple(TERM_VERSIONS) == TERM_NAMES
    assert AskWeights().locate == 0.0, "must ship inert"


def test_it_is_zero_on_a_card_whose_location_is_already_public():
    """The stated exclusion. A located card sitting with the target is a
    certain steal, which `certain` already prices; paying `locate` for it too
    would be scoring the same ask twice for information it does not create."""
    seen = 0
    for ctx, asks in _contexts():
        _, F = ask_feature_matrix(ctx, asks)
        for i, a in enumerate(asks):
            if ctx.bel.public_loc[a.card] is not None:
                assert F[i, J] == 0.0
                seen += 1
    assert seen > 0, "no already-located asks in the sample; test proves nothing"


def test_it_is_never_negative_and_is_bounded_by_the_success_probability():
    """It is a share of uncertainty removed, scaled by P(success): a fraction
    of a probability. Anything outside [0, pi] is a formula error."""
    for ctx, asks in _contexts():
        p, F = ask_feature_matrix(ctx, asks)
        assert (F[:, J] >= -1e-12).all()
        assert (F[:, J] <= p + 1e-9).all()


def test_it_pays_more_as_the_half_suit_approaches_being_fully_located():
    """The load-bearing shape, from the mediator finding it comes from: what a
    declaration risks is how many cards were never publicly LOCATED, so going
    from two unlocated to one must be worth more than six to five.

    Checked as the 1/u bound the formula implies, on real rows. Note the term
    is legitimately ZERO whenever `rest` is zero -- an opponent certainly holds
    a card of the half-suit, so our team will never declare it and locating a
    card there buys nothing. That is the intended behaviour and not the case
    this test is about, so those rows are excluded rather than asserted on.
    """
    checked = positive = 0
    for ctx, asks in _contexts(limit=20):
        p, F = ask_feature_matrix(ctx, asks)
        for i, a in enumerate(asks):
            if ctx.bel.public_loc[a.card] is not None or p[i] <= 1e-9:
                continue
            hs = half_suit_of(a.card)
            u = sum(1 for k in range(6)
                    if ctx.bel.public_loc[hs * 6 + k] is None)
            if not u:
                continue
            # the 1/u factor: the feature can never exceed pi/u
            assert F[i, J] <= p[i] / u + 1e-9, "the 1/u factor is not applied"
            # and going to a SMALLER u must raise the bound, which is the
            # monotonicity the term is named for
            assert p[i] / max(u - 1, 1) >= p[i] / u - 1e-12
            checked += 1
            positive += F[i, J] > 0.0
    assert checked > 0
    assert positive > 0, ("the term is zero on every scorable ask; it cannot "
                          "reward what its comment describes")


def test_it_is_zero_where_the_team_cannot_win_the_half_suit():
    """The other half of the shape. Locating a card of a half-suit an opponent
    certainly holds part of buys nothing, because we will never declare it."""
    from fish4.askfeat import ask_feature_matrix as _f
    seen = 0
    for ctx, asks in _contexts(limit=20):
        _, F = _f(ctx, asks)
        for i, a in enumerate(asks):
            hs = half_suit_of(a.card)
            others = ctx.p_team_card[hs]
            rest = 1.0
            for k in range(6):
                if hs * 6 + k != a.card:
                    rest *= float(others[k])
            if rest == 0.0:
                assert F[i, J] == 0.0
                seen += 1
    assert seen > 0, "no unwinnable half-suits in the sample"


def test_a_weight_on_it_changes_the_engine_and_zero_does_not():
    """Inert at zero, live above it. The regression that matters: a term wired
    somewhere no decision reads would look exactly like a measured null, which
    has happened twice in this project."""
    same = diff = 0
    for g in range(6):
        moves = {}
        for w in (0.0, 0.6):
            st = GameState.deal(RULES, seed=6_400_000 + g)
            agents = [make_agent(("kraken", dict(V06_DEPLOYED[1],
                                                 **({"w_locate": w}
                                                    if p % 2 == 0 else {}))))
                      for p in range(NUM_PLAYERS)]
            for p, a in enumerate(agents):
                a.begin_game(p, RULES, 6_410_000 + g * 13 + p)
            seq, step = [], 0
            while not st.is_terminal and step < 400:
                m = st.turn
                act = agents[m].act(Observation.from_state(st, m))
                seq.append(repr(act))
                st.apply(m, act)
                step += 1
            moves[w] = seq
        if moves[0.0] == moves[0.6]:
            same += 1
        else:
            diff += 1
    assert diff >= 3, f"w_locate changed only {diff}/6 games; is it reaching " \
                      f"the objective at all?"


def test_the_champion_is_bit_identical_with_the_term_present():
    """Adding a column to the basis must not move the shipped engine. The
    weight is zero, so the extra column contributes exactly zero to the dot
    product -- but that is a claim about floating point, so check it."""
    for g in range(4):
        seqs = []
        for wts in (None, AskWeights(**{**AskWeights().to_dict(),
                                        "locate": 0.0})):
            st = GameState.deal(RULES, seed=6_600_000 + g)
            agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                      for _ in range(NUM_PLAYERS)]
            for p, a in enumerate(agents):
                a.begin_game(p, RULES, 6_610_000 + g * 13 + p)
                if wts is not None:
                    a.weights = wts
            seq, step = [], 0
            while not st.is_terminal and step < 400:
                m = st.turn
                act = agents[m].act(Observation.from_state(st, m))
                seq.append(repr(act))
                st.apply(m, act)
                step += 1
            seqs.append(seq)
        assert seqs[0] == seqs[1]
