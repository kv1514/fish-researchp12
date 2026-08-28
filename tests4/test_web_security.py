"""The serverless table is on a public URL, so its boundary is a security one.

Each test here corresponds to an exploit that was reproduced against the live
deployment. They exist because the ordinary information-boundary tests could not
catch any of them: those check that a *policy* cannot see hidden state, and every
hole below was in the transport around the policy instead.

The unifying mistake was authenticating the wrong thing. The token proved which
game a client was playing and said nothing about what had happened in it, so the
client could assert a history that never occurred and read the engine's honest
answer to it.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("FISH_SECRET", "test-secret-for-web-security-tests")

from api._engine import (Session, log_hash, new_session,  # noqa: E402
                         seed_from_nonce, unseal)
from fish.cards import card_name, mask_to_cards  # noqa: E402


def _fresh():
    s = new_session({"seat": 0, "gamma": 0.35})
    played = s.advance()
    return s, s.token(), list(played)


# ---------------------------------------------------------------------------
# S1: the token must commit to the action log
# ---------------------------------------------------------------------------

def test_a_fabricated_claim_log_cannot_be_replayed():
    """The whole-deal oracle.

    A claim resolves against the true hands and reports the holders, which is
    correct - a resolved claim is public. What was not correct was letting a
    client assert nine claims that never happened. One request returned all 54
    card locations, and because the function is stateless nothing was persisted:
    the attacker discarded the reply and played the real game knowing every hand.
    """
    _, tok, _ = _fresh()
    fabricated = [{"t": "claim", "hs": k, "assignment": [0, 0, 0, 0, 0, 0]}
                  for k in range(9)]
    with pytest.raises(ValueError):
        Session.restore(tok, fabricated)


def test_a_truncated_log_fails_against_a_CURRENT_token():
    """The same hole in its cheating-rather-than-peeking form.

    Renamed. The old name -- "the log cannot be truncated to take a move back"
    -- asserted a property this system does not have: it holds only while the
    token is the current one. See the honest sibling below.
    """
    s, _, acts = _fresh()
    while not s.snapshot()["your_turn"] and not s.snapshot()["terminal"]:
        break
    acts = acts + s.play(s.suggest())
    tok = s.token()
    assert len(acts) >= 1
    with pytest.raises(ValueError):
        Session.restore(tok, acts[:-1])


def test_an_appended_action_is_rejected():
    _, tok, acts = _fresh()
    with pytest.raises(ValueError):
        Session.restore(tok, acts + [{"t": "pass", "teammate": 2}])


def test_the_honest_log_still_replays():
    s, tok, acts = _fresh()
    back = Session.restore(tok, acts)
    assert back.snapshot()["hand"] == s.snapshot()["hand"]
    assert back.seed == s.seed


def test_the_token_commits_to_the_log():
    _, tok, acts = _fresh()
    assert unseal(tok)["h"] == log_hash(acts)


# ---------------------------------------------------------------------------
# S3: the seed space must be too large to enumerate
# ---------------------------------------------------------------------------

def test_the_seed_is_not_small_enough_to_enumerate():
    """seed -> deal is public deterministic code, so the key does not protect it.

    At the original 2**30 there were fewer seeds than there are 9-card hands
    (C(54,9) = 5.3e9), so a player's own nine cards pinned their deal uniquely
    and a sweep was hours of CPU. Worse, seed -> hands is unkeyed, so a
    precomputed table would have broken every past and future game and survived
    rotating FISH_SECRET.
    """
    seeds = [seed_from_nonce(f"nonce-{i}") for i in range(16)]
    assert min(s.bit_length() for s in seeds) > 200
    assert min(seeds) > math.comb(54, 9)
    assert len(set(seeds)) == len(seeds)


def test_a_large_seed_still_deals_a_legal_game():
    """The fix is only usable if the engine accepts the wider seed."""
    s = new_session({"seat": 0, "gamma": 0.35})
    assert sorted(h.bit_count() for h in s.state.hands) == [9] * 6
    seen = set()
    for h in s.state.hands:
        cards = set(mask_to_cards(h))
        assert not (cards & seen)
        seen |= cards
    assert len(seen) == 54


# ---------------------------------------------------------------------------
# S4: a hostile token must fail as a ValueError, not a TypeError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tok", [
    "abc." + "é" * 27,          # compare_digest raises TypeError on non-ASCII
    "no-dot-at-all",
    "",
    "." * 5,
    "abc.",
])
def test_hostile_tokens_raise_valueerror(tok):
    with pytest.raises(ValueError):
        unseal(tok)


def test_a_short_fish_secret_is_refused_in_favour_of_the_random_fallback():
    """A short deploy-time secret is worse than no deploy-time secret.

    Any single token an attacker holds is an offline oracle on the key, so a
    short value can be ground out and then used to forge sessions and derive
    deals. The random per-process fallback is at least unguessable, at the cost
    of games not surviving a move between instances.
    """
    from api import _engine
    old = os.environ.get("FISH_SECRET")
    try:
        os.environ["FISH_SECRET"] = "short"
        assert _engine._secret() == _engine._EPHEMERAL_SECRET
        os.environ["FISH_SECRET"] = "x" * _engine.MIN_SECRET_BYTES
        assert _engine._secret() == b"x" * _engine.MIN_SECRET_BYTES
    finally:
        if old is None:
            os.environ.pop("FISH_SECRET", None)
        else:
            os.environ["FISH_SECRET"] = old


# ---------------------------------------------------------------------------
# What the seat is entitled to see
# ---------------------------------------------------------------------------

def test_a_snapshot_never_carries_another_seat_hand_before_the_end():
    s, _, _ = _fresh()
    snap = s.snapshot()
    assert snap["reveal"] is None, "hands revealed before the game ended"
    mine = {c["name"] for c in snap["hand"]}
    assert mine == {card_name(c) for c in mask_to_cards(s.state.hands[s.seat])}
    blob = repr(snap)
    for p in range(6):
        if p == s.seat:
            continue
        for c in mask_to_cards(s.state.hands[p]):
            n = card_name(c)
            if n in mine:
                continue
            assert f'"{n}"' not in blob, f"{n} (P{p}'s) appeared in the payload"


# -- decision traces are exhibition-only -------------------------------------
#
# A trace carries a bot's ranked candidates and its confidence. Those are
# derived from the public record plus THAT SEAT'S OWN HAND, so handing one to
# a seated human would push information across the boundary this whole module
# exists to defend. In spectate every seat is a bot and there is no hand to
# protect, which is the one place reasoning can be shown.

def test_a_seated_game_never_carries_a_decision_trace():
    s = new_session({"seat": 0})
    s.advance(8)
    snap = s.snapshot()
    assert "why" not in snap, "a seated player was handed engine reasoning"
    assert not s.traces
    blob = json.dumps(snap)
    for marker in ('"ranked"', '"p_hit"', '"tie_group"', '"confidence"'):
        assert marker not in blob, f"{marker} leaked into a seated payload"


def test_the_bots_in_a_seated_game_are_not_even_tracing():
    """Belt and braces: the flag is off at the source, not filtered at the door."""
    s = new_session({"seat": 0})
    s.advance(8)
    for p, bot in s.bots.items():
        assert getattr(bot, "trace", False) is False, f"seat {p} is tracing"
        assert getattr(bot, "last_trace", None) is None


def test_the_exhibition_does_carry_traces_and_only_for_our_seats():
    s = new_session({"mode": "spectate", "step": 1})
    s.advance(10)
    why = s.snapshot()["why"]
    assert why, "the exhibition explained nothing"
    for key, tr in why.items():
        assert int(key) >= 0
        # Odd seats are ours; the even seats run Dylan's engine, which has no
        # trace to give and must not be presented as if it had one.
        assert tr["seat"] % 2 == 1, "a trace was attributed to their engine"
        assert tr["kind"] in {"ask", "declare", "pass", "exact", "signal"}


def test_a_trace_carries_beliefs_and_never_ground_truth():
    """The distinction that makes the exhibition safe to explain.

    An ask trace names cards the asker wants. That is not a leak: an ask is a
    public act, the alternatives it ranks are ones the asker provably does not
    hold (ask legality), and the numbers beside them are the engine's BELIEF,
    not the deal. What would be a leak is a field asserting where a card
    actually is. Only a declaration carries holders, and a declaration is a
    public claim the moment it is made -- so the invariant is that ask traces
    carry no holder field at all, and declare traces carry only the split the
    engine is about to announce anyway.

    (An earlier version of this test compared ranked cards against the seat's
    CURRENT hand and failed, correctly: a seat that asks for 2H and gets it
    holds it moments later. The hand at inspection time is not the hand at
    decision time, and the property worth pinning was never about hands.)
    """
    s = new_session({"mode": "spectate", "step": 1})
    s.advance(12)
    seen_kinds = set()
    for tr in s.snapshot()["why"].values():
        seen_kinds.add(tr["kind"])
        for row in tr.get("ranked", []):
            assert "holder" not in row, "an ask trace asserted a card's location"
            assert set(row) <= {"rank", "target", "card", "half_suit",
                                "score", "p_hit", "chosen"}
        for row in tr.get("split", []):
            # The engine's own declaration, which the table is about to hear.
            assert set(row) == {"card", "holder"}
            assert 0 <= row["holder"] < 6
    assert "ask" in seen_kinds, "fixture never produced an ask trace"


def test_an_old_token_with_its_own_log_still_restores_and_that_is_by_design():
    """The honest sibling of the truncation test.

    A response hands the client a signed token for the position it describes.
    Keeping an old one together with the log that matched it yields a pair
    that verifies, because it really was issued. No stateless check can refuse
    it, so this test asserts the property the system HAS rather than the one
    the old test name wished for.
    """
    s = new_session({"seat": 0})
    early_tok, early_log = s.token(), list(s.wire_log)
    # The human starts, so advance() alone is a no-op; make a move first.
    s.play(s.suggest())
    later_tok, later_log = s.token(), list(s.wire_log)
    assert len(later_log) > len(early_log), "fixture did not advance"

    # Both pairs verify. The early one is a rollback and it is accepted.
    back = Session.restore(early_tok, early_log)
    assert len(back.wire_log) == len(early_log)
    assert len(Session.restore(later_tok, later_log).wire_log) == len(later_log)
    # Crossing them does not: the token commits to ITS OWN log.
    with pytest.raises(ValueError):
        Session.restore(early_tok, later_log)


def test_the_rollback_oracle_is_real_and_is_documented_as_such():
    """Pin the consequence, so nobody re-derives it as a surprise.

    Nine restores of ONE saved token+log pair, each declaring a different
    half-suit and each thrown away, read off every card location while the
    real game stays where it was. A declaration is legal on any unresolved
    half-suit whether or not the declarer holds a card in it, and resolving
    one reveals the true holders -- correctly, since a resolved declaration is
    public.

    This is asserted rather than fixed because there is no stateless fix, and
    it is worth a test because the RESEARCH consequence is easy to forget:
    site transcripts are not evidence of honest play.
    """
    from fish.engine import Claim

    s = new_session({"seat": 0})
    tok, log = s.token(), list(s.wire_log)
    learned = {}
    for hs in range(9):
        branch = Session.restore(tok, log)      # the same signed pair, reused
        if branch.state.set_winner[hs] is not None:
            continue
        ev = branch.state.apply(branch.seat, Claim(hs, tuple([branch.seat] * 6)))
        learned[hs] = ev.revealed

    assert len(learned) == 9, "the oracle should reach every half-suit"
    assert all(len(v) == 6 for v in learned.values())
    real = Session.restore(tok, log)
    assert len(real.wire_log) == len(log), "the real game must be untouched"
    assert not any(w is not None for w in real.state.set_winner)

    # And the docstring must say so, so the code and the claim cannot drift.
    import api._engine as eng
    doc = eng.log_hash.__doc__
    assert "does **not** close" in doc.lower() or "NOT** CLOSE" in doc
    assert "not evidence of honest play" in doc
