"""The oracle's side filter: two bounds, not two halves.

`OracleBot(side=...)` restricts which cards the cheat is told about, so the
value of knowing where TEAMMATES' cards are can be priced apart from the value
of knowing where OPPONENTS' are. The project's error ledger is why: 0.1676 of
our 0.1759 wrong declarations a game are allocation class -- our own team held
all six and we named the wrong split -- against 0.0083 ownership errors.

These tests check the filter selects the side it says and nothing else, and
that the default is bit-identical to the historical behaviour so no stored
ceiling figure silently changes meaning.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.oracle import OracleBot

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _owners(st):
    out = [None] * 54
    for p in range(NUM_PLAYERS):
        h = st.hands[p]
        for c in range(54):
            if h >> c & 1:
                out[c] = p
    return out


def _armed(seat, side, seed=4242, reveal=1.0):
    """Arm the cheat and let it choose its revealed set, without moving.

    `act` is deliberately not used. It calls through to the full policy, which
    at a seat that is not on turn has no legal action and raises -- and the
    revealed set is chosen before any of that, in exactly these two lines. So
    the test drives the mechanism under test rather than a whole decision.
    """
    st = GameState.deal(RULES, seed=seed)
    bot = OracleBot(reveal=reveal, side=side)
    bot.begin_game(seat, RULES, 900 + seat)
    bot.see_deal(_owners(st))
    bot.bel.update(Observation.from_state(st, seat))
    bot._collapse()
    return bot, _owners(st)


def test_bad_side_is_rejected_at_construction():
    with pytest.raises(ValueError):
        OracleBot(side="teammates")
    for s in ("all", "team", "opp"):
        OracleBot(side=s)


def test_team_reveals_only_teammates_cards():
    bot, owners = _armed(0, "team")
    assert bot._revealed, "nothing was revealed"
    assert all(team_of(owners[c]) == team_of(0) for c in bot._revealed), (
        "a card belonging to an opponent was revealed under side='team'")


def test_opp_reveals_only_opponents_cards():
    bot, owners = _armed(0, "opp")
    assert bot._revealed, "nothing was revealed"
    assert all(team_of(owners[c]) != team_of(0) for c in bot._revealed), (
        "a teammate's card was revealed under side='opp'")


def test_the_two_sides_are_disjoint_and_together_are_all():
    t, owners = _armed(0, "team")
    o, _ = _armed(0, "opp")
    a, _ = _armed(0, "all")
    assert not (t._revealed & o._revealed)
    assert t._revealed | o._revealed == a._revealed, (
        "team and opp together are not the whole hidden set, so one of the "
        "filters is dropping cards rather than partitioning them")


def test_the_default_is_the_historical_behaviour():
    """side='all' must reproduce what every stored ceiling figure was taken at."""
    a, _ = _armed(0, "all")
    plain = OracleBot(reveal=1.0)
    st = GameState.deal(RULES, seed=4242)
    plain.begin_game(0, RULES, 900)
    plain.see_deal(_owners(st))
    plain.bel.update(Observation.from_state(st, 0))
    plain._collapse()
    assert a._revealed == plain._revealed


def test_a_seat_is_never_told_its_own_cards():
    """`reveal` is a fraction of what is genuinely hidden, and one's own hand
    is not hidden -- it is already pinned, so it must never enter the pool."""
    for side in ("all", "team", "opp"):
        bot, owners = _armed(3, side)
        assert all(owners[c] != 3 for c in bot._revealed), side
