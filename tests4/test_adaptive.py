"""Adaptive style: the duel penalty and the score-aware tie-breakers.

Both obey the same discipline every term in this project obeys - a zero weight
must reproduce the baseline decision for decision, and a non-zero weight must
demonstrably change one - because a term that cannot be turned off is a term
whose effect cannot be attributed, and a term that never changes anything is a
term nobody has tested.
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

from fish.cards import NUM_PLAYERS, team_of                    # noqa: E402
from fish.engine import AskEvent                                # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from fish4.adaptive import (adjust_weights, duel_depth,          # noqa: E402
                            recent_losses, retake_flags,
                            score_pressure)
from fish4.askfeat import AskWeights                             # noqa: E402
from fish4.registry4 import make_agent                           # noqa: E402

from tests4.test_leakage4 import collect_positions               # noqa: E402

BASE = {"opponent_gamma": 0.35}


def _obs(history, set_winner=None, seat=0, hand=0b111):
    return Observation(
        player=seat, rules=RuleConfig(), hand=hand, turn=seat,
        hand_counts=(9,) * NUM_PLAYERS,
        set_winner=tuple(set_winner if set_winner is not None else [None] * 9),
        history=tuple(history))


# ---------------------------------------------------------------------------
# The duel
# ---------------------------------------------------------------------------

def test_a_card_taken_from_us_is_a_recent_loss():
    o = _obs([AskEvent(asker=1, target=0, card=7, success=True)])
    assert recent_losses(o) == {(1, 7)}


def test_a_failed_ask_against_us_is_not_a_loss():
    o = _obs([AskEvent(asker=1, target=0, card=7, success=False)])
    assert recent_losses(o) == set()


def test_a_card_taken_from_someone_else_is_not_our_loss():
    o = _obs([AskEvent(asker=1, target=2, card=7, success=True)])
    assert recent_losses(o) == set()


def test_the_window_forgets():
    old = [AskEvent(asker=1, target=0, card=7, success=True)]
    filler = [AskEvent(asker=3, target=4, card=k, success=False)
              for k in range(10)]
    o = _obs(old + filler)
    assert recent_losses(o, window=8) == set()
    assert recent_losses(o, window=0) == {(1, 7)}


def test_only_the_ask_that_takes_it_back_is_flagged():
    from fish.engine import Ask
    o = _obs([AskEvent(asker=1, target=0, card=7, success=True)])
    asks = [Ask(1, 7), Ask(1, 8), Ask(3, 7)]
    assert list(retake_flags(o, asks)) == [1.0, 0.0, 0.0]


def test_duel_depth_counts_the_trade_in_both_directions():
    """A duel is a card going back and forth, not one player taking twice."""
    o = _obs([AskEvent(asker=1, target=0, card=7, success=True),
              AskEvent(asker=0, target=1, card=7, success=True),
              AskEvent(asker=1, target=0, card=7, success=True)])
    assert duel_depth(o) == 3
    quiet = _obs([AskEvent(asker=1, target=2, card=7, success=True)])
    assert duel_depth(quiet) == 0


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------

def test_score_pressure_is_zero_before_anything_is_decided():
    assert score_pressure(_obs([])) == 0.0


def test_score_pressure_is_positive_when_behind():
    # seat 0 is team 0; three sets to team 1, one to us
    o = _obs([], set_winner=[1, 1, 1, 0, None, None, None, None, None])
    assert score_pressure(o) == pytest.approx(0.5)


def test_score_pressure_is_negative_when_ahead():
    o = _obs([], set_winner=[0, 0, 0, 1, None, None, None, None, None])
    assert score_pressure(o) == pytest.approx(-0.5)


def test_a_nulled_set_counts_for_neither_side():
    """Which is what the rules say, so the pressure must not move."""
    from fish.engine import NULL_TEAM
    a = _obs([], set_winner=[0, 1, None, None, None, None, None, None, None])
    b = _obs([], set_winner=[0, 1, NULL_TEAM, None, None, None, None, None, None])
    assert score_pressure(a) == score_pressure(b) == 0.0


def test_adjust_weights_is_the_identity_at_zero():
    w = AskWeights(suit=0.06, turn=0.6, scarce=0.2)
    o = _obs([], set_winner=[1, 1, 1, 0, None, None, None, None, None])
    assert adjust_weights(w, o, 0.0) is w


def test_adjust_weights_scales_the_tie_breakers_not_the_objective():
    """P(success) always carries weight 1 and is not in AskWeights at all.

    That is the point: the paper's sharpest finding is that P(success) is the
    objective and the rest are tie-breaks, so adaptation moves the tie-breaks.
    """
    w = AskWeights(suit=0.06, turn=0.6, scarce=0.2)
    behind = _obs([], set_winner=[1, 1, 1, 0, None, None, None, None, None])
    got = adjust_weights(w, behind, 0.5)
    assert got.turn == pytest.approx(0.6 * 1.25)
    assert got.scarce == pytest.approx(0.2 * 1.25)
    assert "p_success" not in w.__dataclass_fields__


def test_a_term_is_never_inverted_by_a_large_weight():
    """Past a sign flip it is a different idea, not a scaled one."""
    w = AskWeights(suit=0.06, turn=0.6, scarce=0.2)
    ahead = _obs([], set_winner=[0, 0, 0, 0, None, None, None, None, None])
    got = adjust_weights(w, ahead, 5.0)          # k = 1 + 5*(-1) = -4 -> 0
    assert got.turn == 0.0 and got.scarce == 0.0


# ---------------------------------------------------------------------------
# The ablation discipline, on real positions
# ---------------------------------------------------------------------------

def _act(spec, rules, hands, sw, turn, hist, seat):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    a = make_agent(("fishbot4", spec))
    a.begin_game(seat, rules, 4242)
    return a.act(obs)


@pytest.mark.parametrize("off", [{"w_retake": 0.0}, {"w_behind": 0.0}])
def test_a_zero_weight_reproduces_the_baseline(off):
    positions = collect_positions(3, 3, 18)
    assert positions
    for pos in positions:
        assert _act(BASE, *pos) == _act(dict(BASE, **off), *pos)


@pytest.mark.parametrize("on", [{"w_retake": 0.5}, {"w_behind": 1.0}])
def test_a_nonzero_weight_changes_some_decision(on):
    differed = 0
    for pos in collect_positions(5, 2, 60):
        if _act(BASE, *pos) != _act(dict(BASE, **on), *pos):
            differed += 1
    assert differed > 0, f"{on} never changed a decision"
