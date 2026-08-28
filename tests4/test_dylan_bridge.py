"""The bridge to Dylan's v0.7 must not ask their engine an unfair question.

These tests run without their compiled binary: the choice under test is made
on our side of the bridge, before anything is spawned.

The bug this pins was found by an adversarial read of their C++ and it ran in
OUR favour, which is the direction that never gets caught by "does our number
look good". Their driver, forced to declare, picks the first live half-suit
the mover HOLDS A CARD IN (``engine/src/game.hpp:535``). Ours passed the
first live half-suit, full stop -- so their ``bestGuess`` was periodically
asked to name six owners in a half-suit it held nothing of, which it cannot
do, and under the opponent-award rule each of those handed us a set.
"""

from __future__ import annotations

from fish.cards import card_id, half_suit_mask
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.dylan_v07 import DylanV07

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _obs(hand_cards: list[str], live: list[int]) -> Observation:
    hand = 0
    for name in hand_cards:
        hand |= 1 << card_id(name)
    return Observation(
        player=0, rules=RULES, hand=hand, turn=0,
        hand_counts=(len(hand_cards), 9, 9, 9, 9, 9),
        set_winner=tuple(None if hs in live else 1 for hs in range(9)),
        history=())


def test_forced_half_suit_is_one_they_hold_a_card_in():
    """The whole point: skip live half-suits the mover holds nothing of."""
    obs = _obs(["2H", "3H"], live=[0, 1, 2, 3])
    hs_hearts = card_id("2H") // 6
    assert hs_hearts in (0, 1, 2, 3), "fixture must keep hearts live"
    chosen = DylanV07._forced_half_suit(obs, [0, 1, 2, 3])
    assert chosen == hs_hearts
    assert obs.hand & half_suit_mask(chosen)


def test_forced_half_suit_prefers_the_earliest_held_one():
    """Their loop breaks at the first match, so ties go to the lower index."""
    held = ["2C", "2H"]
    obs = _obs(held, live=list(range(9)))
    lo = min(card_id(c) // 6 for c in held)
    assert DylanV07._forced_half_suit(obs, list(range(9))) == lo


def test_forced_half_suit_ignores_a_half_suit_they_hold_that_is_dead():
    """A declared half-suit is not a candidate even if cards of it are held."""
    hs_clubs = card_id("2C") // 6
    hs_hearts = card_id("2H") // 6
    obs = _obs(["2C", "2H"], live=[hs_hearts])
    assert DylanV07._forced_half_suit(obs, [hs_hearts]) == hs_hearts
    assert hs_clubs != hs_hearts


def test_forced_half_suit_falls_back_when_they_hold_nothing():
    """Their driver ends the game here; ours still has to name something."""
    obs = _obs([], live=[2, 5, 7])
    assert DylanV07._forced_half_suit(obs, [2, 5, 7]) == 2


def test_the_old_behaviour_really_was_different():
    """Guard against a fix that is a no-op -- claimable[0] must be wrong here."""
    obs = _obs(["2H"], live=list(range(9)))
    claimable = list(range(9))
    assert DylanV07._forced_half_suit(obs, claimable) != claimable[0]
