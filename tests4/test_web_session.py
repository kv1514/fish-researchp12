"""The public site ships one engine, one deck, and starts the human on the move.

Three things the site used to let a visitor choose, and why each stopped being
a choice:

  THE DECK. 54 or 48 cards, offered as peers. Every number in the paper, every
  pre-registered run and every calibration table is measured on 54; the 48-card
  arm exists in fish.rules for the rule-variant robustness study and carries no
  tuning, no verdict and no claim. Offering it as an equal option implied a
  parity nobody had measured.

  THE ENGINE. gamma 0 ("reads only the rules") against gamma 0.35 ("reads your
  asks") -- a strength selector whose weak arm is worth about -1.9 sets per
  deal-pair. A button whose only function is to make your opponent worse.

  WHO STARTS. The deal used starting_player=0 regardless of where the human
  sat, so a player in seat 3 dealt in and watched three engine possessions
  before touching anything, then had to reconstruct the tracking from a log.

The third change has a failure mode the other two do not, and it is the reason
this file exists. ``Session.restore`` rebuilds RuleConfig from the token. If it
does not carry the same starting_player, restore builds a game with a DIFFERENT
seat on turn at ply 0, and every replayed action is then applied to the wrong
player -- loudly for most logs, and quietly for one whose first action happens
to be legal for both seats.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                              # noqa: E402
from api._engine import CHAMPION_GAMMA, Session, new_session    # noqa: E402


def test_the_human_is_on_the_move_at_the_deal():
    """Whatever seat they pick -- not just seat 0, which was already true."""
    for seat in range(NUM_PLAYERS):
        s = new_session({"seat": seat})
        assert s.rules.starting_player == seat
        assert s.state.turn == seat
        assert s.snapshot()["your_turn"] is True, (
            f"seat {seat} deals in without the move")


def test_the_client_cannot_choose_the_deck_or_the_engine():
    """Passing the old fields changes nothing, rather than being honoured."""
    s = new_session({"seat": 0, "variant": "48", "gamma": 0.0,
                     "any_time": True})
    assert s.rules.variant == "54", "the 48-card deck is still reachable"
    assert s.gamma == CHAMPION_GAMMA, "engine strength is still selectable"
    # claims_any_time is a rule variant too, and the same argument applies.
    assert s.rules.claims_any_time is False


def test_restore_rebuilds_the_same_game_from_a_non_zero_seat():
    """The token has no starting_player field; it is derived from the seat.

    This is the check that would have caught a defaulted starting_player: at
    seat 0 the old and new code agree, so a test that only ever seats the
    player at 0 passes either way.
    """
    for seat in range(NUM_PLAYERS):
        s = new_session({"seat": seat})
        r = Session.restore(s.token(), s.wire_log)
        assert r.rules.starting_player == seat
        assert r.state.turn == s.state.turn
        assert r.state.hands == s.state.hands, (
            f"seat {seat}: restore dealt a different game")


def test_a_replayed_log_lands_on_the_same_position():
    """The real invariant: play, seal, restore, and the position agrees.

    Exercised from a seat that is NOT 0, because that is where a defaulted
    starting_player diverges.
    """
    s = new_session({"seat": 4})
    # The human is on the move, so ask the engine what it would do and do it.
    s.play(s.suggest(), max_moves=6)
    tok, log = s.token(), list(s.wire_log)
    assert log, "no actions were recorded"

    r = Session.restore(tok, log)
    assert r.state.turn == s.state.turn
    assert r.state.hands == s.state.hands
    assert r.state.set_winner == s.state.set_winner
    assert r.snapshot()["score"] == s.snapshot()["score"]


def test_a_token_whose_seat_was_tampered_with_does_not_replay():
    """Seat and starting_player are now the same field, so moving one moves
    both -- which means a forged seat changes the deal and the log stops
    matching. The signature already prevents this; this records that the
    derivation did not open a second path around it."""
    s = new_session({"seat": 2})
    s.play(s.suggest(), max_moves=4)
    tok = s.token()
    # Flip a character in the payload. unseal must reject it outright.
    bad = tok[:8] + ("A" if tok[8] != "A" else "B") + tok[9:]
    with pytest.raises(ValueError):
        Session.restore(bad, s.wire_log)
