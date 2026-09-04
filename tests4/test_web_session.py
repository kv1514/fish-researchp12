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
from fish.rules import RuleConfig                                # noqa: E402
from api._engine import (CHAMPION_GAMMA, MAX_LOG, Session,      # noqa: E402
                         new_session)

#: A FIXED fixture for the one test that needs a game played to its end.
#:
#: new_session() derives the deal from secrets.token_urlsafe(12) and ignores
#: any seed, deliberately, so nobody can pick a deal they solved offline. That
#: makes it a fresh random game every run -- and about 1.5% of play-mode games
#: on the shipped path do not terminate at all. They livelock: a captured hang
#: had 7 of 9 half-suits resolved, 12 cards left, and its last 200 actions were
#: one 8-action cycle repeating 25 times, cards passed between the same seats
#: with nobody ever declaring. See RESEARCH_FRONTIER.md.
#:
#: So the test below used to be a coin flip that came up tails in CI roughly
#: once in fifty runs. Pinning the deal is not hiding that: what the test
#: asserts is the SHAPE of the reveal payload at game over, which does not
#: depend on which deal was dealt, and reaching game over is a precondition of
#: the assertion rather than the thing being measured. The livelock is a real
#: defect, it is recorded as one, and it is not this test's job to find it.
#:
#: The nonces are the FIRST candidates of a fixed enumeration -- "fixture-
#: <mode>-0", "-1", and so on -- and both index 0 terminate, so nothing was
#: skipped and no deal was selected for its outcome.
FIXTURE_NONCE = {"spectate": "fixture-spectate-0", "play": "fixture-play-0"}


def _fixture(mode: str) -> Session:
    rules = RuleConfig(variant="54", starting_player=0,
                       wrong_distribution_outcome="opponent")
    if mode == "spectate":
        return Session(-1, FIXTURE_NONCE[mode], rules, CHAMPION_GAMMA,
                       mode="spectate")
    return Session(0, FIXTURE_NONCE[mode], rules, CHAMPION_GAMMA)


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
    for mode in ("spectate", "play"):
        s = _fixture(mode)
        tok, log = s.token(), list(s.wire_log)
        # THE BOUND IS DERIVED FROM MAX_LOG, and that is the point of it.
        # At six actions an iteration a 250-iteration loop can build a
        # 1,500-action log, and Session.restore refuses anything past
        # MAX_LOG = 1,200. So a game that failed to finish did not fail on
        # this test's own "fixture never finished" -- it failed one loop
        # earlier, inside the engine, with "action log too long", which is a
        # far worse error for exactly the same bug. It happened once in CI.
        #
        # MAX_LOG // 6 caps the log at 1,194 at the last restore, so the
        # engine can no longer be the thing that complains, and the
        # assertion below is what fires. It is not a smaller test: 1,200
        # actions is about ten times a real game. Measured over 100 fresh
        # fixtures (40 spectate, 60 play, all terminating): median 105,
        # max 191.
        #
        # WHAT PRODUCED THOSE LONG GAMES IS NOW EXPLAINED, and it was not
        # a long game: it is a livelock. See FIXTURE_NONCE above. The deal
        # is pinned now, so this loop terminates in about 95 actions and the
        # bound is slack rather than load-bearing.
        for _ in range(MAX_LOG // 6):
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


def test_the_evaluation_branches_actually_differ():
    """Three documented fields were identical by construction, and inert.

    _rank_moves evaluates a candidate by mutating ctx.M -- forcing the asked
    card to us for the success branch, redistributing it away from the target
    for the failure branch -- and calling _live_eval in between. That only
    works if _live_eval reads M. It read ctx.team_exp / ctx.opp_exp instead,
    which DecisionContext freezes at construction, so both branches returned
    the same number: measured, 8 of 8 ranked asks had
    eval_if_success == eval_if_fail == eval_expected, all 0.000000.

    Any caption built on the difference -- "this move cost you X sets" -- would
    have printed zero forever, which is worse than printing nothing.
    """
    s = new_session({"seat": 0})
    moves = s.analysis()["moves"]
    assert len(moves) > 5, "fixture too small"
    differing = [m for m in moves
                 if m["eval_if_success"] != m["eval_if_fail"]]
    assert len(differing) > len(moves) // 2, (
        f"only {len(differing)}/{len(moves)} candidates distinguish landing "
        f"from missing")
    for m in moves:
        # Landing a card can never be worth LESS than missing it: the success
        # branch puts the card in our own hand, the miss branch puts it
        # anywhere but the target.
        assert m["eval_if_success"] >= m["eval_if_fail"] - 1e-9, m
        # And the expectation must sit between its own branches.
        lo, hi = sorted((m["eval_if_fail"], m["eval_if_success"]))
        assert lo - 1e-9 <= m["eval_expected"] <= hi + 1e-9, m


# --------------------------------------------------------------- claim check


def test_claim_check_prices_the_players_own_split():
    """The number returned is about the split that was SENT, not the engine's.

    The whole feature is that a player can be told their split is wrong.  A
    route that quietly re-prices the engine's answer would return a
    reassuring number for every input, and would be worse than no route.
    """
    s = new_session({"seat": 0})
    snap = s.snapshot()
    team = sorted([snap["seat"]] + list(snap["teammates"]))
    hs = next(i for i, w in enumerate(snap["set_winner"]) if not w)

    r = s.claim_check(hs, [team[0]] * 6)
    assert r["assignment"] == [team[0]] * 6
    assert 0.0 <= r["p_exact"] <= 1.0
    assert 0.0 <= r["p_team"] <= 1.0
    # p_team is over ALL splits, so it can never be below any one of them
    assert r["p_team"] >= r["p_exact"] - 1e-9, (r["p_team"], r["p_exact"])

    # and a different split must be able to get a different number
    other = s.claim_check(hs, r["engine"]["assignment"])
    assert other["engine"]["same"] is True
    assert other["p_team"] == r["p_team"], "p_team is a property of the set"


def test_the_engines_figure_is_recomputed_the_same_way_as_the_players():
    """Two methods wearing one label is the failure this guards against.

    `claim4.best_for_half_suit` has two tiers: above its enumeration cap it
    returns a PRODUCT of per-card marginals rather than a joint, which at the
    opening it always does.  Quoting that beside an exact joint would put two
    different estimators side by side under one heading.
    """
    from fish4.analyse import Analyser
    from fish4.claim4 import ClaimConfig, ClaimEvaluator
    from fish.cards import half_suit_cards
    from api._engine import _analyser_spec

    s = new_session({"seat": 0})
    snap = s.snapshot()
    hs = next(i for i, w in enumerate(snap["set_winner"]) if not w)
    r = s.claim_check(hs, [snap["seat"]] * 6)

    obs = s.obs()
    an = Analyser(s.rules, s.seat, value_model=None, gamma=s.gamma,
                  n_draws=s.draws, seed=s.seed & 0x7FFFFFFF, **_analyser_spec())
    ctx = an.context(obs)
    ev = ClaimEvaluator(ctx, ClaimConfig()).best_for_half_suit(hs)
    assert ev is not None
    direct = float(ctx.post.prob_assignment(list(half_suit_cards(hs)),
                                            list(ev[2].assignment)))
    assert abs(r["engine"]["p_exact"] - round(direct, 4)) < 1e-9, (
        "the engine's figure was quoted rather than recomputed")


def test_claim_check_refuses_what_the_engine_would_refuse():
    s = new_session({"seat": 0})
    snap = s.snapshot()
    team = sorted([snap["seat"]] + list(snap["teammates"]))
    hs = next(i for i, w in enumerate(snap["set_winner"]) if not w)
    opp = next(p for p in range(6) if p not in team)

    for bad, why in (([team[0]] * 5, "wrong length"),
                     ([opp] * 6, "a card on the other team")):
        try:
            s.claim_check(hs, bad)
        except ValueError:
            continue
        raise AssertionError(f"{why} was accepted")


def test_no_claim_check_for_a_spectator():
    """Same trap analysis() and deductions() guard: seat -1 would silently
    build seat 5's view, and price a split using another player's hand."""
    s = new_session({"mode": "spectate"})
    try:
        s.claim_check(0, [0] * 6)
    except ValueError:
        return
    raise AssertionError("a spectator was allowed to price a split")


def test_the_declaration_ledger_survives_the_log_tail():
    """A ledger missing its first rows reads as a complete one.

    The client is sent `self.log[-LOG_TAIL:]`, and a full game runs well past
    LOG_TAIL actions, so a ledger filtered from the slice would silently lose
    the early half-suits. It has to come from the whole history.
    """
    from api._engine import LOG_TAIL

    # new_session IGNORES any seed on purpose -- letting a client choose the
    # deal is exactly what the nonce prevents -- so this test cannot pin the
    # game and has to search for one that can actually discriminate. A game
    # whose declarations all happen to land inside the last LOG_TAIL actions
    # proves nothing about where the ledger was built from, and roughly one
    # game in forty is like that. Hoping is not a test design: play until a
    # game with a declaration OUTSIDE the tail turns up, and assert on that.
    discriminating = None
    for _ in range(40):
        s = new_session({"seat": 0})
        s.advance(600)
        while not s.state.is_terminal:
            s.play(s.suggest())
        snap = s.snapshot()
        assert snap["terminal"]
        led = snap["declarations"]

        # This one holds for EVERY game and is the property that matters:
        # every set that resolved has exactly one declaration behind it.
        resolved = sum(1 for w in s.state.set_winner if w is not None)
        assert len(led) == resolved, (
            f"{len(led)} ledger rows for {resolved} resolved sets")

        in_tail = [r for r in snap["log"] if r.get("t") == "claim"]
        assert len(led) >= len(in_tail), (
            "the ledger has fewer rows than the tail alone shows, which means "
            "it is not built from the whole history")
        if len(s.log) > LOG_TAIL and len(led) > len(in_tail):
            discriminating = (len(led), len(in_tail), len(s.log))
            break

    assert discriminating is not None, (
        "40 games and not one had a declaration outside the last "
        f"{LOG_TAIL} actions, so the tail-trimming case was never exercised. "
        "That is a real signal, not a flake: either games got much shorter or "
        "declarations moved much later.")
    n_led, n_tail, n_log = discriminating
    assert n_led > n_tail, (
        f"ledger {n_led} rows against {n_tail} claims visible in the "
        f"{LOG_TAIL}-action tail of a {n_log}-action game -- a ledger filtered "
        f"from the slice would have lost the earlier half-suits")


def test_every_declaration_is_classified_and_the_classes_are_exclusive():
    """right / split / ownership, and the split class means what it says."""
    from fish.cards import team_of

    s = new_session({"seat": 0})
    s.advance(600)
    while not s.state.is_terminal:
        s.play(s.suggest())
    for r in s.snapshot()["declarations"]:
        assert r["klass"] in ("right", "split", "ownership"), r["klass"]
        ct = team_of(r["claimer"])
        if r["klass"] == "right":
            assert r["winner"] == ct
            assert r["declared"] == r["revealed"]
        elif r["klass"] == "split":
            # the defining property: our own team held all six anyway
            assert all(team_of(h) == ct for h in r["revealed"])
            assert r["declared"] != r["revealed"]
        else:
            assert any(team_of(h) != ct for h in r["revealed"])
