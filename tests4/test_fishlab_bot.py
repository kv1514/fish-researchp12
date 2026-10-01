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
    """A failed declaration must assert NO holders, because pinning the claimed
    split raised BeliefContradiction in 5 of 5 real cases.

    It must still contribute the EVENT. Dropping it -- the first version of
    this adapter -- lost the six cards that left the table, which is its own
    contradiction (see the regression below).
    """
    br = _ready()
    hist = [{"t": "declare", "actor": 1, "set": 2, "success": False,
             "winner": 0, "owner": [1, 3, 5, 1, 3, 5],
             "counts": [9, 7, 9, 8, 9, 6]}]
    evs = br._history(hist, per=9)
    assert len(evs) == 1
    ev = evs[0]
    assert ev.revealed_known is False
    # 9 - the published post-event counts, seat by seat.
    assert ev.surrendered == (0, 2, 0, 1, 0, 3)

    ok = [{"t": "declare", "actor": 1, "set": 2, "success": True,
           "winner": 1, "owner": [1, 3, 5, 1, 3, 5],
           "counts": [9, 6, 9, 7, 9, 7]}]
    evs = br._history(ok, per=9)
    assert len(evs) == 1 and evs[0].revealed_known is True


def test_the_position_that_failed_fish_bots_check():
    """Regression: the exact shape `fish bots check kraken` died on.

    Seat 0 holds seven cards; two half-suits were resolved by WRONG
    declarations, and one of them took a card out of seat 0's hand. With the
    event dropped, seat 0's reconstructed deal came to eight cards, its
    nine-card quota could not be filled from the cards left open to it, and the
    propagator reported `player 0 count infeasible` on a perfectly legal
    position. The fix is not to guess which card it was -- that is not public --
    but to carry the published count and leave the identity open.
    """
    from fish.beliefs import BeliefState

    br = _ready()
    # Seat 0 is dealt nine, gives 2S away by ask, and loses one more card to a
    # wrong declaration of Low Diamonds. Nothing else moves. The half-suit
    # indices are looked up rather than written down, because the two projects
    # number them differently and a hardcoded index would make this test pass
    # for the wrong reason.
    from fish.cards import card_id, half_suit_of
    low_diamonds = br.hs_to_set[half_suit_of(card_id("2D"))]
    sw = [None] * 9
    sw[low_diamonds] = 0
    hist = [
        # Seat 1 may ask for 2S only while holding another Low Spade, and seat
        # 0 keeps only 3S of that half-suit, so four of them are still open to
        # seat 1 and the ask is legal.
        {"t": "ask", "actor": 1, "target": 0, "card": "2S", "success": True,
         "counts": [8, 10, 9, 9, 9, 9]},
        # Seat 3 declares Low Diamonds for its own team and is wrong, because
        # seat 0 -- an opponent -- holds one of the six. Team 0 takes it.
        {"t": "declare", "actor": 3, "set": low_diamonds, "success": False,
         "winner": 0, "owner": [3, 3, 3, 3, 3, 3],
         "counts": [7, 10, 9, 5, 9, 8]},
    ]
    # Seat 0's remaining seven: one Low Spade and all of High Spades. None is a
    # Low Diamond, which is what makes its share of that half-suit unnameable.
    state = {"seat": 0, "turn": 0, "deck_sets": 9,
             "hand": ["3S", "9S", "TS", "JS", "QS", "KS", "AS"],
             "hand_counts": [7, 10, 9, 5, 9, 8],
             "set_winner": sw,
             "history": hist}
    obs = br.observation(state)

    assert bin(obs.initial_hand()).count("1") == 8, (
        "eight cards are nameable: the seven held plus the one given away")
    mask, count = obs.unknown_own_cards()
    assert count == 1 and bin(mask).count("1") == 6, (
        "the ninth was one of that half-suit's six, and only the count is public")

    # The whole point: this must not raise.
    b = BeliefState(obs.rules, observer=0)
    b.update(obs)


def test_hand_that_disagrees_with_hand_counts_is_refused():
    br = _ready()
    with pytest.raises(ValueError):
        br.observation({"seat": 0, "turn": 0, "hand": ["2S", "3S"],
                        "hand_counts": [9, 9, 9, 9, 9, 9],
                        "set_winner": [None] * 9, "history": []})


def test_every_script_the_readme_tells_you_to_run_exists():
    """The README's FIRST command was ``./build.sh`` for a build.sh that had
    been replaced by build.py. Anyone following it got "No such file or
    directory" on line one. A README is an interface; this checks it compiles.
    """
    import re

    here = Path(__file__).resolve().parents[1] / "fishlab"
    text = (here / "README.md").read_text(encoding="utf-8")
    # Scripts named as a command (./x.py, python3 x.py) or in backticks.
    named = set(re.findall(r'(?:\./|python3?\s+|`)([A-Za-z0-9_]+\.(?:py|sh))',
                           text))
    assert named, "the README names no script at all; the pattern stopped matching"
    missing = sorted(n for n in named
                     if not (here / n).exists()
                     and not (here.parent / "scripts4" / n).exists())
    assert not missing, (
        f"fishlab/README.md tells the reader to run {missing}, which do not "
        f"exist in fishlab/ or scripts4/."
    )


def test_an_unrevealed_resolution_without_counts_is_refused():
    """`revealed_known=False` with no `surrendered` accounts for nothing.

    The six cards left the table; if neither the holders nor the hand-size
    change is recorded, a seat cannot say how many of them were its own.
    Reading the missing count as zero would silently disclaim cards it may have
    held -- which is precisely the contradiction `surrendered` exists to
    remove, reintroduced through the back door.
    """
    from fish.engine import ClaimEvent
    from fish.observation import Observation
    from fish.rules import RuleConfig

    ev = ClaimEvent(claimer=1, half_suit=2, declared=(1,) * 6,
                    revealed=(1,) * 6, winner=0, revealed_known=False)
    obs = Observation(player=0, rules=RuleConfig(), hand=0, turn=0,
                      hand_counts=(3, 9, 9, 9, 9, 9),
                      set_winner=(None, None, 0) + (None,) * 6,
                      history=(ev,))
    with pytest.raises(ValueError, match="surrendered"):
        obs.unknown_own_cards()
