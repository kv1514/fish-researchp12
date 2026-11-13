"""Crediting the turn on a successful ask: the ablation, and an exact monotone.

``score_asks_by_value`` prices an ask as the expected change in half-suit value
and nothing else. That omits the larger half of what a hit buys -- you are
still on the move, so you ask again -- and the omission is asymmetric, because
the turn DID appear on the failure side as ``turn_weight * (1 - p) *
turn_risk``. A cost on failure with no credit for success is largest exactly
where ``p`` is smallest, which is a subsidy for long shots.

That is measured, not argued: over 3236 real decisions
(``results/value_objective_diag.json``) the objective picks asks whose success
probability is 0.0946 +/- 0.0043 below the champion's picks, and DELETING the
turn term makes its picks better. The played consequence is -7.355 sets per
duplicate deal-pair.

``keep_value`` supplies the missing credit. Two properties carry it, and both
are exact rather than statistical:

* **It reduces to its baseline.** ``keep_value=0.0`` must reproduce the old
  scores bit for bit. Every new term in this project is required to pass this;
  v0.3's most instructive failure was an ablation that silently moved a second
  thing.
* **It is monotone in the right direction, provably.** Choosing
  ``argmax_i (f_i + k * p_i)``, the selected ``p`` is non-decreasing in ``k``.
  For ``k1 < k2`` with picks ``i1``, ``i2``, optimality at each gives
  ``f_i1 + k1*p_i1 >= f_i2 + k1*p_i2`` and ``f_i2 + k2*p_i2 >= f_i1 + k2*p_i1``;
  adding them leaves ``(k2 - k1)(p_i2 - p_i1) >= 0``. So this holds on EVERY
  position, and a violation is a bug in the term rather than noise -- which is
  why it is worth testing at all, and why it needs no sample size.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.observation import Observation
from fish4.askfeat import DecisionContext
from fish4.hsvalue import HalfSuitValue, ask_delta_values, score_asks_by_value
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

from tests4.test_leakage4 import collect_positions

MODEL = ROOT / "checkpoints" / "hsvalue_v1.json"
TURN = 0.15
GRID = (0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.8, 1.2, 2.0, 5.0)


def _ctx(rules, hands, set_winner, turn, history, seat):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(set_winner), history=history)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(13), n_draws=64, obs=obs, gamma=0.35)
    return obs, DecisionContext(obs, bel, post)


def _positions(n_games=3, stride=3, cap=12):
    model = HalfSuitValue.load(MODEL)
    for rules, hands, sw, turn, hist, seat in collect_positions(
            n_games, stride, cap):
        obs, ctx = _ctx(rules, hands, sw, turn, hist, seat)
        asks = obs.legal_asks()
        if len(asks) >= 2:
            yield ctx, asks, model


def test_zero_keep_reproduces_the_objective_exactly():
    """The ablation discipline: the default must change nothing at all."""
    seen = 0
    for ctx, asks, model in _positions():
        base = score_asks_by_value(ctx, asks, model, turn_weight=TURN)
        zero = score_asks_by_value(ctx, asks, model, turn_weight=TURN,
                                   keep_value=0.0)
        assert np.array_equal(base, zero), "keep_value=0.0 moved the scores"
        seen += 1
    assert seen > 0, "collected no positions, so this asserted nothing"


def test_the_credit_is_exactly_keep_times_p_success():
    """The term's whole content, stated as an identity rather than a direction."""
    seen = 0
    for ctx, asks, model in _positions():
        _, _, ps = ask_delta_values(ctx, asks, model)
        base = score_asks_by_value(ctx, asks, model, turn_weight=TURN)
        for k in (0.2, 0.8):
            got = score_asks_by_value(ctx, asks, model, turn_weight=TURN,
                                      keep_value=k)
            assert np.allclose(got, base + k * ps, atol=1e-12)
        seen += 1
    assert seen > 0


def test_the_chosen_ask_never_gets_less_likely_as_the_credit_rises():
    """Exact monotone, so one violation anywhere is a bug and not noise."""
    seen = 0
    for ctx, asks, model in _positions():
        _, _, ps = ask_delta_values(ctx, asks, model)
        picked = []
        for k in GRID:
            s = score_asks_by_value(ctx, asks, model, turn_weight=TURN,
                                    keep_value=k)
            picked.append(float(ps[int(np.argmax(s))]))
        for (k0, p0), (k1, p1) in zip(zip(GRID, picked),
                                      list(zip(GRID, picked))[1:]):
            assert p1 >= p0 - 1e-12, (
                f"raising keep_value {k0} -> {k1} lowered the chosen ask's "
                f"P(success) {p0:.6f} -> {p1:.6f}")
        seen += 1
    assert seen > 0


def test_a_large_credit_takes_the_likeliest_ask():
    """The limit the term is built to approach, checked at a finite value."""
    seen = 0
    for ctx, asks, model in _positions():
        _, _, ps = ask_delta_values(ctx, asks, model)
        s = score_asks_by_value(ctx, asks, model, turn_weight=TURN,
                                keep_value=50.0)
        assert float(ps[int(np.argmax(s))]) == pytest.approx(float(ps.max()))
        seen += 1
    assert seen > 0


def test_the_champion_is_untouched():
    """The reference spec must not acquire a term by default."""
    a = make_agent(("fishbot4", {"opponent_gamma": 0.35}))
    assert a.value_keep == 0.0


def test_a_credit_that_would_be_ignored_is_refused():
    """A parameter that silently does nothing is a misattributed ablation.

    In the blend path the heuristic objective already carries P(success) at
    weight 1.0, so applying the credit there would price the same tempo twice.
    Rather than quietly dropping it, the agent refuses the combination -- the
    failure mode being guarded against is a duel cell whose label says
    ``value_keep=0.4`` and whose policy never read it.
    """
    with pytest.raises(ValueError, match="value_keep"):
        make_agent(("fishbot4", {"w_value": 0.5, "value_keep": 0.4}))
    with pytest.raises(ValueError, match="value_keep"):
        make_agent(("fishbot4", {"value_keep": 0.4}))
    # and the supported combination constructs
    assert make_agent(("fishbot4", {"objective": "value",
                                    "value_keep": 0.4})).value_keep == 0.4
