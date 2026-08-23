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


def test_the_log_cannot_be_truncated_to_take_a_move_back():
    """The same hole in its cheating-rather-than-peeking form."""
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
