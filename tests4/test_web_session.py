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


# -- the analysis path, which no test covered until it broke in production ----
#
# WEB_SPEC gained "endgame_m": 0 with v0.6 and api/_engine.py splatted the
# whole spec into Analyser, which has never had that parameter. Every call
# raised TypeError, api/index.py turned it into {"error": "internal error"},
# and the Think button, the auto-analysis checkbox, the posterior panel and the
# declare dialog's suggested split were all dead on the live site. Nothing
# failed loudly, because nothing exercised the route.

def test_analysis_actually_returns_an_analysis():
    """The regression test proper: this raised TypeError in production."""
    s = new_session({"seat": 0})
    a = s.analysis()
    assert not a.get("terminal")
    assert a["moves"], "an analysis with no ranked moves explains nothing"
    assert a["seat"] == 0


def test_every_web_spec_key_is_either_understood_or_registered_inert():
    """The guard that makes the fix a fix rather than a patch.

    Silently dropping a spec key the Analyser cannot represent would leave the
    page confidently explaining a policy the site is not playing -- a worse
    failure than the 500, because it looks like it works.
    """
    from api._engine import WEB_SPEC, _ANALYSER_INERT, _analyser_spec
    import inspect

    from fish4.analyse import Analyser
    accepted = set(inspect.signature(Analyser.__init__).parameters)
    spec = _analyser_spec()
    for k, v in WEB_SPEC.items():
        if k in accepted:
            assert spec[k] == v, f"{k} must reach the Analyser unchanged"
        else:
            assert k in _ANALYSER_INERT, (
                f"{k} is dropped from the analysis with no justification")
            assert v == _ANALYSER_INERT[k]
            assert k not in spec


def test_a_non_inert_unknown_key_is_a_loud_error_not_a_wrong_panel():
    """endgame_m is queued to ship non-zero; when it does, this must shout."""
    import api._engine as eng
    from api._engine import _analyser_spec

    original = dict(eng.WEB_SPEC)
    try:
        eng.WEB_SPEC["endgame_m"] = 2          # the queued refit, hypothetically
        with pytest.raises(RuntimeError, match="different policy"):
            _analyser_spec()
        eng.WEB_SPEC.clear()
        eng.WEB_SPEC.update(original)
        eng.WEB_SPEC["some_future_knob"] = 1.0
        with pytest.raises(RuntimeError, match="not registered as inert"):
            _analyser_spec()
    finally:
        eng.WEB_SPEC.clear()
        eng.WEB_SPEC.update(original)
    assert _analyser_spec()                     # restored, and working again


def test_a_restored_session_remembers_where_the_cards_were():
    """The end-of-game review panel was empty on every refresh.

    ``revealed`` is what the "where the cards actually were as each set
    resolved" panel reads. ``advance`` and ``play`` recorded it, but the
    ``restore`` replay did not -- and since EVERY request restores from the
    token, the map only ever held what resolved inside the current request.
    A finished game showed 0 of its 54 cards on a refresh.
    """
    s = new_session({"seat": 0})
    tok, log = s.token(), list(s.wire_log)
    for _ in range(200):
        cur = Session.restore(tok, log)
        if cur.state.is_terminal:
            break
        if cur.state.turn == cur.seat:
            obs = cur.obs()
            acts = obs.legal_asks() or obs.legal_passes()
            if not acts:
                break
            cur.play(acts[0])
        else:
            cur.advance(3)
        tok, log = cur.token(), list(cur.wire_log)

    final = Session.restore(tok, log)
    resolved = sum(1 for w in final.state.set_winner if w is not None)
    assert resolved, "fixture never resolved a half-suit"
    assert len(final.revealed) == 6 * resolved, (
        f"{len(final.revealed)} cards recorded for {resolved} resolved "
        f"half-suits; the review panel reads this map")
    for holder in final.revealed.values():
        assert 0 <= holder < NUM_PLAYERS


def test_both_modes_reveal_the_same_shape_at_game_over():
    """`{}` is truthy in JS, so a dict here threw at every exhibition game over.

    The client does `if (s.reveal) s.reveal.forEach(...)`. Spectate used to
    send an empty dict, which passes the guard and fails the walk -- and the
    throw escaped the caller's catch, so watchGameOver() never ran, the series
    tally froze and the next deal never started.
    """
    shapes = {}
    for mode, body in (("spectate", {"mode": "spectate", "step": 1}),
                       ("play", {"seat": 0})):
        s = new_session(body)
        tok, log = s.token(), list(s.wire_log)
        for _ in range(250):
            cur = Session.restore(tok, log)
            if cur.state.is_terminal:
                break
            if mode == "play" and cur.state.turn == cur.seat:
                # suggest() is the engine's own move, so it is legal in every
                # state including the forced-declaration one where there is no
                # legal ask AND no legal pass. Picking legal_asks()[0] broke
                # there and made this test flaky rather than wrong -- worse.
                cur.play(cur.suggest())
            else:
                cur.advance(6)
            tok, log = cur.token(), list(cur.wire_log)
        assert cur.state.is_terminal, f"{mode} fixture never finished"
        rev = cur.snapshot()["reveal"]
        assert isinstance(rev, list), f"{mode} reveal is {type(rev).__name__}"
        assert len(rev) == NUM_PLAYERS
        shapes[mode] = sum(len(h) for h in rev)
    assert shapes["spectate"] == shapes["play"] == 54, shapes


def test_trace_keys_index_the_log_that_was_actually_sent():
    """Absolute action indices go out of range once the log is trimmed.

    The snapshot ships only the last LOG_TAIL entries. Traces are stored
    against absolute action indices, so past that point the two numberings
    drift apart and every explanation silently renders nothing -- the exact
    failure the trace feature exists to avoid. Measured before the rebase: at
    63 actions the keys were 60, 61, 62 against a 60-entry list.
    """
    from api._engine import LOG_TAIL

    s = new_session({"mode": "spectate", "step": 1})
    tok, log = s.token(), list(s.wire_log)
    checked_past_the_tail = False
    for _ in range(80):
        cur = Session.restore(tok, log)
        if cur.state.is_terminal:
            break
        cur.advance(3)
        snap = cur.snapshot()
        sent = len(snap["log"])
        for key in snap["why"]:
            assert 0 <= int(key) < sent, (
                f"trace key {key} against a {sent}-entry log "
                f"({len(cur.wire_log)} actions played)")
        if len(cur.wire_log) > LOG_TAIL + 2 and snap["why"]:
            checked_past_the_tail = True
        tok, log = cur.token(), list(cur.wire_log)
    assert checked_past_the_tail, (
        "fixture never got past the log tail, so the regression is untested")
