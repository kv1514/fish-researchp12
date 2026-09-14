"""A game on the public path always ends, and ending it changes nothing else.

THE DEFECT THIS CLOSES. Two teams that both play well can cycle: a half-suit
passes back and forth, every ask succeeding, neither side ever holding all six,
nobody able to declare. `RESEARCH_FRONTIER.md` has a captured one whose last
200 actions are a single 8-action cycle repeated 25 times. On the web that game
never ended -- a visitor sat watching six bots trade two half-suits until they
gave up, and at 1,200 actions the session died on "action log too long" rather
than finishing.

WHAT THE FIX IS NOT. It is not a change to how anything plays. The rest of this
project has capped every measured game since v0.3 (`fish4/match.py::play_capped`)
and scores a capped game on the half-suits actually resolved, unresolved ones
counting for nobody -- the semantics `fish4/exact_ii.py` gives an unbroken
cycle. The web was the only surface without that rule. `scripts4/web_cap_check.py`
checks the equivalence the expensive way, by replaying both arms and comparing
action logs; these tests pin the properties that make the rule coherent.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("FISH_SECRET", "cap-test-secret-0123456789abcdef")

import pytest                                                 # noqa: E402

from fish.cards import NUM_PLAYERS                             # noqa: E402
from fish.rules import RuleConfig                              # noqa: E402
from api import _engine                                        # noqa: E402
from api._engine import (CHAMPION_GAMMA, MAX_LOG, Session,     # noqa: E402
                         SEED_ADVANCES_WITH_PLY, WEB_MAX_ACTIONS,
                         WEB_MAX_IDLE)

#: The runs the caps were chosen from: both modes, the DEPLOYED protocol (one
#: Session per move), and both seeding arms. The frozen arm is the defect the
#: ply arm fixed, kept runnable so the before/after does not live only in git
#: history -- and kept here because the caps have to clear the longest game
#: either arm produces, not just the well-behaved one.
EVIDENCE = ["web_termination_r1_ply_1000.json",
            "web_termination_r1_frozen_1000.json"]


def _rules():
    return RuleConfig(variant="54", starting_player=0,
                      wrong_distribution_outcome="opponent")


def _game(nonce="cap-fixture-0"):
    return Session(0, nonce, _rules(), CHAMPION_GAMMA)


def test_the_seeding_that_ships_is_the_one_that_advances():
    """The switch exists so the DEFECT stays reproducible, not so it stays
    reachable. Anything but True here is the livelock back on the public
    site."""
    assert SEED_ADVANCES_WITH_PLY is True, (
        "api/_engine.py ships SEED_ADVANCES_WITH_PLY False. That re-seeds all "
        "six agents from the deal on every request, which makes the engine's "
        "move a pure function of the position and lets a recurring position "
        "recur forever. See Session.seed_at.")


def test_a_stopped_game_still_ends_cleanly():
    """Past MAX_LOG the session does not end, it dies: `Session.restore`
    refuses the log and the player loses the game rather than finishing it.
    A cap at or above that ceiling would be no fix at all."""
    assert WEB_MAX_ACTIONS < MAX_LOG, (
        f"the cap is {WEB_MAX_ACTIONS} and the client's log ceiling is "
        f"{MAX_LOG}; a game that reaches the cap would already have died.")


@pytest.mark.parametrize("rel", EVIDENCE)
def test_the_cap_clears_every_game_that_ever_finished(rel):
    """The cap is a measurement, so it is checked against the measurement.

    If a future engine plays longer games, this fails rather than the cap
    quietly starting to truncate real ones.
    """
    path = ROOT / "results" / rel
    assert path.exists(), (
        f"results/{rel} is the evidence the cap was chosen from and is not "
        f"there; re-run scripts4/web_termination.py.")
    d = json.loads(path.read_text())
    longest = d["max_terminating_actions"]
    assert longest is not None and longest > 0
    assert WEB_MAX_ACTIONS > longest, (
        f"the cap is {WEB_MAX_ACTIONS} and {rel} saw a game terminate in "
        f"{longest} actions. The cap must clear every game that finishes on "
        f"the cards, or it stops real games.")
    quiet = d["max_terminating_idle"]
    assert quiet is not None and quiet > 0
    assert WEB_MAX_IDLE > quiet, (
        f"the no-progress rule is {WEB_MAX_IDLE} and {rel} saw a game that "
        f"finished go {quiet} actions without resolving a half-suit. A rule "
        f"tighter than that stops games that were about to end.")
    assert d["n_hung"] >= 0 and d["ceiling"] <= MAX_LOG


def test_the_no_progress_rule_fires_before_the_action_cap():
    """The rule that actually rescues a player, and the one that makes the
    ending timely: at the table's default pace, WEB_MAX_ACTIONS alone is about
    two hours of watching a cycle."""
    old_a, old_i = _engine.WEB_MAX_ACTIONS, _engine.WEB_MAX_IDLE
    _engine.WEB_MAX_ACTIONS, _engine.WEB_MAX_IDLE = MAX_LOG, 15
    try:
        s = _game()
        while not s.over:
            if s.state.turn == s.seat:
                s.play(s.suggest(), max_moves=0)
            else:
                s.advance(1)
        assert s.stopped is True
        assert len(s.wire_log) < MAX_LOG, (
            "the action cap ended it, so this proves nothing about idling")
        assert s.idle >= 15
    finally:
        _engine.WEB_MAX_ACTIONS, _engine.WEB_MAX_IDLE = old_a, old_i


def test_idle_counts_from_the_log_not_from_an_instance_counter():
    """Every request rebuilds the Session, so a counter kept on the object
    would reset to zero on each one and the rule would never fire on the only
    path it exists for."""
    s = _game()
    for _ in range(8):
        if s.over:
            break
        if s.state.turn == s.seat:
            s.play(s.suggest(), max_moves=0)
        else:
            s.advance(1)
    before = s.idle
    again = Session.restore(s.token(), list(s.wire_log))
    assert again.idle == before, (
        f"idle is {again.idle} after a restore and was {before} before it")


def test_the_caps_changed_no_game_that_finished():
    """The equivalence claim, read off the run that made it.

    Not "the capped arm scores about the same" -- that needs thousands of games
    and an interval and would still hide a small real effect. The arbiter rules
    are invisible to every agent, so the claim is exact: on every game that
    finishes below them, both arms play the IDENTICAL sequence of actions.
    One counterexample refutes it.
    """
    path = ROOT / "results" / "web_cap_check_r1_150.json"
    assert path.exists(), (
        "results/web_cap_check_r1_150.json is missing; re-run "
        "scripts4/web_cap_check.py 150 1.")
    d = json.loads(path.read_text())
    assert d["cap"] == WEB_MAX_ACTIONS and d["idle_cap"] == WEB_MAX_IDLE, (
        f"that run checked cap={d['cap']}, idle={d['idle_cap']}; the shipped "
        f"rules are {WEB_MAX_ACTIONS} and {WEB_MAX_IDLE}. The check says "
        f"nothing about rules it did not run under.")
    assert d["seeding"] == "ply", "checked under the seeding that is not shipped"
    assert d["n_diverged"] == 0, f"{d['n_diverged']} games played differently"
    assert d["n_identical"] == d["n_finished_both"] == d["n_games"] > 0


def test_the_cap_stops_the_game_and_says_so():
    """Drive a real session past a deliberately tiny cap."""
    old = _engine.WEB_MAX_ACTIONS
    _engine.WEB_MAX_ACTIONS = 12
    try:
        s = _game()
        while not s.over:
            if s.state.turn == s.seat:
                s.play(s.suggest(), max_moves=0)
            else:
                s.advance(1)
        assert len(s.wire_log) >= 12
        assert not s.state.is_terminal, (
            "the fixture resolved all nine half-suits inside 12 actions, "
            "which is not possible; the cap was not what ended it.")
        assert s.stopped is True
        assert s.over is True
        # The arbiter stops; it does not rewrite the board.
        assert any(w is None for w in s.state.set_winner)
        # And nothing further happens.
        assert s.advance(50) == []
        snap = s.snapshot()
        assert snap["terminal"] is True and snap["stopped"] is True
        assert snap["your_turn"] is False
        assert snap["must_pass"] is False
    finally:
        _engine.WEB_MAX_ACTIONS = old


def test_a_stopped_game_reveals_every_card():
    """The client walks `reveal` as six lists covering the deck.

    In a game that ends on the cards every card entered `revealed` as its
    half-suit resolved. In a stopped game the live ones never did, so the
    builder has to finish the map from the hands -- otherwise the review panel
    shows a player 36 of 54 cards with no explanation of where the rest went.
    """
    old = _engine.WEB_MAX_ACTIONS
    _engine.WEB_MAX_ACTIONS = 12
    try:
        s = _game()
        while not s.over:
            if s.state.turn == s.seat:
                s.play(s.suggest(), max_moves=0)
            else:
                s.advance(1)
        rev = s.snapshot()["reveal"]
        assert isinstance(rev, list) and len(rev) == NUM_PLAYERS
        assert sum(len(h) for h in rev) == 54, (
            f"a stopped game revealed {sum(len(h) for h in rev)} of 54 cards")
        # No card in two places.
        flat = [c for h in rev for c in h]
        assert len(set(flat)) == len(flat)
    finally:
        _engine.WEB_MAX_ACTIONS = old


def test_the_scores_at_a_stop_are_what_resolved():
    """Unresolved sets count for nobody -- play_capped's semantics, not a draw
    awarded to somebody or a set handed to whoever held the most of it."""
    old = _engine.WEB_MAX_ACTIONS
    _engine.WEB_MAX_ACTIONS = 12
    try:
        s = _game()
        while not s.over:
            if s.state.turn == s.seat:
                s.play(s.suggest(), max_moves=0)
            else:
                s.advance(1)
        a, b, nulls = s.state.scores()
        resolved = sum(1 for w in s.state.set_winner if w is not None)
        assert a + b + nulls == resolved
        snap = s.snapshot()
        assert snap["score"]["you"] + snap["score"]["them"] \
            + snap["score"]["nulled"] == resolved
    finally:
        _engine.WEB_MAX_ACTIONS = old


def test_the_client_is_told_about_a_stop_on_every_path():
    """`stopped` has to be in BOTH snapshots. Spectate used to differ from play
    on a game-over field and it broke the exhibition loop for weeks."""
    app = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
    assert "s.stopped" in app, (
        "public/app.js never reads `stopped`, so a stopped game renders as a "
        "plain game over on a board with live sets.")
    src = (ROOT / "api" / "_engine.py").read_text(encoding="utf-8")
    assert src.count('"stopped": self.stopped') == 2, (
        "`stopped` is not in both snapshot payloads (play and spectate).")
