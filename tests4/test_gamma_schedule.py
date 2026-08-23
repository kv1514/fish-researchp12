"""Weighting an ask by where in the game it happened.

The opponent choice model treats every ask as equally informative about depth.
It should not: the hypothesis is that a player asks in proportion to how many
cards of a half-suit they hold, which presumes they had a choice. Early they do;
late, legality binds and they ask where they can.

``gamma_schedule`` scales the per-ask weight by the fraction of half-suits
already resolved when the ask was made. At zero it is the incumbent, exactly, and
that has to be true decision for decision or the term cannot be attributed.
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

from fish.beliefs import BeliefState                       # noqa: E402
from fish.cards import NUM_PLAYERS                          # noqa: E402
from fish.engine import AskEvent, ClaimEvent                # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.oppmodel import schedule_factor                   # noqa: E402
from fish4.registry4 import make_agent                      # noqa: E402

from tests4.test_leakage4 import collect_positions          # noqa: E402

BASE = {"opponent_gamma": 0.35}


# ---------------------------------------------------------------------------
# The schedule arithmetic, tested directly
#
# Not through a hand-built Observation: a fabricated history is not a reachable
# state, the belief tracker correctly refuses it, and a test that has to defeat
# the engine's own consistency checks is testing the fixture rather than the
# code. The integration is covered on real harvested positions below.
# ---------------------------------------------------------------------------

def test_zero_schedule_is_one_everywhere():
    for resolved in range(10):
        assert schedule_factor(resolved, 9, 0.0) == 1.0


def test_an_opening_ask_counts_for_more_than_a_closing_one():
    """The whole hypothesis: early asks carry more signal about depth."""
    opening = schedule_factor(0, 9, 0.5)
    closing = schedule_factor(8, 9, 0.5)
    assert opening == pytest.approx(1.5)
    assert closing == pytest.approx(1 + 0.5 * (1 - 2 * 8 / 9))
    assert opening > closing


def test_the_factor_falls_monotonically_through_the_game():
    fs = [schedule_factor(r, 9, 0.5) for r in range(10)]
    assert all(a >= b for a, b in zip(fs, fs[1:]))


def test_the_midpoint_is_unweighted():
    """Halfway through, the schedule should neither favour nor discount."""
    assert schedule_factor(9, 18, 0.7) == pytest.approx(1.0)


def test_a_late_ask_is_never_weighted_negatively():
    """Past zero it is evidence of the opposite, which is a different model."""
    for s in (2.0, 5.0, 50.0):
        assert schedule_factor(8, 9, s) >= 0.0


def test_no_half_suits_does_not_divide_by_zero():
    assert schedule_factor(0, 0, 0.5) == pytest.approx(1.5)


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


def test_zero_schedule_reproduces_the_baseline_decision_for_decision():
    positions = collect_positions(3, 3, 18)
    assert positions
    for pos in positions:
        assert _act(BASE, *pos) == _act(dict(BASE, gamma_schedule=0.0), *pos)


def test_a_nonzero_schedule_changes_some_decision():
    differed = 0
    for pos in collect_positions(5, 2, 60):
        if _act(BASE, *pos) != _act(dict(BASE, gamma_schedule=0.6), *pos):
            differed += 1
    assert differed > 0, "the schedule never changed a decision"
