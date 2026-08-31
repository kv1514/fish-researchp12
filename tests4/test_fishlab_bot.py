"""The FishLab adapter's translation layer.

The parts a live game does not reliably reach, and the two mistakes FishLab's
own docs single out: a wrong-team allocation (which their engine SKIPS rather
than rejects, so it looks like a bot that never declares) and a bot that
declines at `last_resort` (which books their all-to-one-seat fallback as ours).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "fishlab"))

from bot import Bridge                                        # noqa: E402

FISHLAB_CARDS = (
    ["2S", "3S", "4S", "5S", "6S", "7S"] + ["9S", "TS", "JS", "QS", "KS", "AS"]
    + ["2H", "3H", "4H", "5H", "6H", "7H"] + ["9H", "TH", "JH", "QH", "KH", "AH"]
    + ["2D", "3D", "4D", "5D", "6D", "7D"] + ["9D", "TD", "JD", "QD", "KD", "AD"]
    + ["2C", "3C", "4C", "5C", "6C", "7C"] + ["9C", "TC", "JC", "QC", "KC", "AC"]
    + ["8S", "8H", "8D", "8C", "RJ", "BJ"])


def _ready() -> Bridge:
    br = Bridge()
    r = br.hello({"op": "hello", "protocol": "fishlab-json-v1",
                  "cards": FISHLAB_CARDS})
    assert r.get("ok"), r
    return br


def test_handshake_derives_the_mapping_and_is_not_the_identity():
    """If it were the identity the mapping code would be untested by every
    game played through it. Ours is clubs-first, FishLab's spades-first."""
    br = _ready()
    assert br.set_to_hs != list(range(9)), (
        "their set order equals ours; this test can no longer detect a "
        "transposition and the harness is not exercising the mapping")
    assert sorted(br.set_to_hs) == list(range(9))


def test_a_deck_that_does_not_correspond_is_refused_not_guessed():
    br = Bridge()
    scrambled = list(FISHLAB_CARDS)
    scrambled[0], scrambled[6] = scrambled[6], scrambled[0]   # split a set
    r = br.hello({"op": "hello", "cards": scrambled})
    assert "error" in r and "correspond" in r["error"]
    assert not br.ready


def test_an_unknown_card_name_is_refused():
    br = Bridge()
    bad = list(FISHLAB_CARDS)
    bad[3] = "10S"                      # FishLab uses T, not 10
    r = br.hello({"op": "hello", "cards": bad})
    assert "error" in r and "10S" in r["error"]


def test_a_foreign_protocol_is_refused():
    br = Bridge()
    r = br.hello({"op": "hello", "protocol": "kv-json-v1",
                  "cards": FISHLAB_CARDS})
    assert "error" in r


def test_declaration_round_trips_through_their_within_set_order():
    """`owner[j]` is the seat holding THEIR cards[set*6+j], which is not our
    position j. Getting this wrong is the bug their docs call out."""
    from fish.engine import Claim
    from fish.cards import card_name, half_suit_cards
    br = _ready()
    for their_set in range(9):
        hs = br.set_to_hs[their_set]
        ours = list(half_suit_cards(hs))
        assign = tuple((i * 2) % 6 for i in range(6))
        out = br._declaration(Claim(hs, assign))
        assert out["set"] == their_set
        for j, seat in enumerate(out["owner"]):
            name = FISHLAB_CARDS[their_set * 6 + j]
            our_card = [c for c in ours if card_name(c) == name][0]
            assert seat == assign[our_card % 6], (
                f"set {their_set} position {j} ({name}) mis-permuted")


def test_pass_is_constrained_to_the_offered_candidates():
    """A pass naming a seat outside `candidates` is a fault, and so is failing
    to answer at all. The state below is deliberately one the belief REJECTS
    (45 of 54 cards with an empty history): every offered candidate is legal
    by construction, so the bot must still name one rather than fault the
    game. The path is rare enough that 25 complete games never reached it."""
    br = _ready()
    state = {"seat": 0, "turn": 0, "hand": [], "hand_counts": [0, 9, 9, 9, 9, 9],
             "set_winner": [None] * 9, "history": []}
    r = br.pass_turn({"op": "pass", "candidates": [2, 4], "state": state})
    assert r.get("action") == "pass"
    assert r["to"] in (2, 4)


def test_pass_with_no_candidates_is_an_error_not_a_guess():
    br = _ready()
    state = {"seat": 0, "turn": 0, "hand": [], "hand_counts": [0, 9, 9, 9, 9, 9],
             "set_winner": [None] * 9, "history": []}
    r = br.pass_turn({"op": "pass", "candidates": [], "state": state})
    assert "error" in r


def test_a_wrong_declaration_contributes_no_holders():
    """The whole reason this speaks FishLab's protocol. A failed declaration
    must add NO ClaimEvent, because pinning the claimed split raised
    BeliefContradiction in 5 of 5 real cases."""
    br = _ready()
    hist = [{"t": "declare", "actor": 1, "set": 2, "success": False,
             "winner": 0, "owner": [1, 3, 5, 1, 3, 5]}]
    assert br._history(hist) == ()
    ok = [{"t": "declare", "actor": 1, "set": 2, "success": True,
           "winner": 1, "owner": [1, 3, 5, 1, 3, 5]}]
    assert len(br._history(ok)) == 1


def test_hand_that_disagrees_with_hand_counts_is_refused():
    br = _ready()
    with pytest.raises(ValueError):
        br.observation({"seat": 0, "turn": 0, "hand": ["2S", "3S"],
                        "hand_counts": [9, 9, 9, 9, 9, 9],
                        "set_winner": [None] * 9, "history": []})
