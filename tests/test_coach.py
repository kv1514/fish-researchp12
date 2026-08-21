"""Live-coach tests.

The coach is the one component a human drives directly, so the tests cover
both correctness (its view must match what the player legally knows) and
the error messages, which are the actual product for anyone typing a real
game in under time pressure.
"""

import pytest

from fish.cards import card_id, card_name
from fish.coach import CoachError, CoachSession
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

HAND = ["2C", "3C", "4C", "2H", "3H", "9D", "TD", "8C", "RJ"]


def test_requires_a_full_legal_hand():
    with pytest.raises(CoachError, match="deals 9 cards"):
        CoachSession.create(seat=0, hand_names=["2C", "3C"])
    with pytest.raises(CoachError, match="same card twice"):
        CoachSession.create(seat=0, hand_names=["2C"] * 9)
    with pytest.raises(CoachError, match="not a card"):
        CoachSession.create(seat=0, hand_names=["ZZ"] + HAND[1:])
    with pytest.raises(CoachError, match="Seat must be"):
        CoachSession.create(seat=9, hand_names=HAND)


def test_48_card_deck_rejects_eights_and_jokers():
    with pytest.raises(CoachError, match="not in the 48-card deck"):
        CoachSession.create(seat=0, variant="48",
                            hand_names=["2C", "3C", "4C", "5C", "6C", "7C",
                                        "8C", "RJ"])


def test_jokers_are_enterable_by_colour_and_alias():
    s = CoachSession.create(seat=0, hand_names=HAND)
    assert s.initial_hand & (1 << card_id("RJ"))
    alt = CoachSession.create(
        seat=0, hand_names=HAND[:-1] + ["red joker"])
    assert alt.initial_hand == s.initial_hand


def test_successful_ask_moves_the_card_into_my_hand():
    s = CoachSession.create(seat=0, hand_names=HAND)
    s.add_ask(0, 1, "8S", True)
    names = {c["name"] for c in s.advise()["hand"]}
    assert "8S" in names
    s.add_ask(1, 0, "8C", True)          # opponent takes one from me
    names = {c["name"] for c in s.advise()["hand"]}
    assert "8C" not in names


def test_turn_tracking_follows_the_rules():
    s = CoachSession.create(seat=0, hand_names=HAND)
    a = s.advise()
    assert a["on_move"] and a["turn"] == 0
    s.add_ask(0, 1, "8S", True)
    assert s.advise()["turn"] == 0        # success keeps the turn
    s.add_ask(0, 3, "8D", False)
    assert s.advise()["turn"] == 3        # failure hands it to the target


def test_rejects_impossible_answers_with_a_human_message():
    s = CoachSession.create(seat=0, hand_names=HAND)
    with pytest.raises(CoachError, match="You are holding"):
        s.add_ask(1, 0, "2C", False)      # I hold 2C; I cannot have said no
    with pytest.raises(CoachError, match="not holding"):
        s.add_ask(1, 0, "5S", True)       # I do not hold 5S
    with pytest.raises(CoachError, match="already hold"):
        s.add_ask(0, 1, "2C", True)       # cannot ask for my own card
    with pytest.raises(CoachError, match="no Low Spades"):
        s.add_ask(0, 1, "5S", True)       # I hold none of that half-suit
    with pytest.raises(CoachError, match="teammates"):
        s.add_ask(0, 2, "5C", True)       # P2 is my teammate


def test_undo_restores_previous_state():
    s = CoachSession.create(seat=0, hand_names=HAND)
    before = s.advise()["hand"]
    s.add_ask(0, 1, "8S", True)
    assert len(s.advise()["hand"]) == len(before) + 1
    s.undo()
    assert s.advise()["hand"] == before
    with pytest.raises(CoachError, match="Nothing to undo"):
        for _ in range(5):
            s.undo()


def test_claim_resolves_a_half_suit():
    s = CoachSession.create(seat=0, hand_names=HAND)
    # someone else claims Low Spades, held entirely by team B
    s.add_claim(claimer=1, half_suit=3, holders=[1, 1, 3, 3, 5, 5])
    a = s.advise()
    assert a["set_winner"][3] == 1
    assert a["scores"]["team1"] == 1


def test_coach_view_matches_the_engine_view_exactly():
    """The whole premise: own hand + public log reproduces the player's
    legal view. Verify against a real engine game."""
    from fish.agents import MemoryAgent
    import random
    rules = RuleConfig()
    state = GameState.deal(rules, seed=17)
    seat = 0
    agents = [MemoryAgent() for _ in range(6)]
    rng = random.Random(17)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    initial = state.hands[seat]
    s = CoachSession(seat=seat, initial_hand=initial, rules=rules)
    for _ in range(40):
        if state.is_terminal:
            break
        p = state.turn
        ev = state.apply(p, agents[p].act(Observation.from_state(state, p)))
        s.events.append(ev)
    engine_view = Observation.from_state(state, seat)
    coach_view = s.observation()
    assert coach_view.hand == engine_view.hand
    assert coach_view.hand_counts == engine_view.hand_counts
    assert coach_view.set_winner == engine_view.set_winner
    assert coach_view.turn == engine_view.turn


def test_advice_is_deterministic():
    s = CoachSession.create(seat=0, hand_names=HAND)
    s.add_ask(0, 1, "8S", True)
    assert s.advise()["recommendation"] == s.advise()["recommendation"]


def test_advice_names_a_legal_action_when_on_move():
    s = CoachSession.create(seat=0, hand_names=HAND)
    a = s.advise()
    assert a["on_move"]
    assert a["recommendation"]
    assert a["recommendation_kind"] in ("ask", "claim", "pass")
    for row in a["asks"]:
        assert 0.0 <= row["p_success"] <= 1.0


def test_nulled_claim_credits_nobody():
    """A team can hold all six cards and still score nothing by naming the
    wrong teammate. That outcome is invisible in the revealed holders, so the
    player must tell us; recording it as a win would corrupt the scoreboard
    that later claim decisions depend on."""
    s = CoachSession.create(seat=0, hand_names=HAND)
    s.add_claim(claimer=1, half_suit=3, holders=[1, 1, 3, 3, 5, 5],
                nulled=True)
    a = s.advise()
    assert a["set_winner"][3] == -1
    assert a["scores"]["team1"] == 0
    assert a["scores"]["null"] == 1


def test_null_is_rejected_when_an_opponent_held_a_card():
    s = CoachSession.create(seat=0, hand_names=HAND)
    with pytest.raises(CoachError, match="only be nulled"):
        s.add_claim(claimer=1, half_suit=3, holders=[1, 1, 3, 3, 5, 2],
                    nulled=True)


def test_claim_outcome_defaults_are_still_correct():
    s = CoachSession.create(seat=0, hand_names=HAND)
    # P2 (team A) held one, so team B's claim loses them the set
    s.add_claim(claimer=1, half_suit=3, holders=[1, 1, 3, 3, 5, 2])
    assert s.advise()["set_winner"][3] == 0


def test_claim_rejects_holders_that_contradict_my_own_hand():
    s = CoachSession.create(seat=0, hand_names=HAND)
    with pytest.raises(CoachError, match="not holding"):
        s.add_claim(claimer=0, half_suit=3, holders=[0, 0, 2, 2, 4, 4])
    with pytest.raises(CoachError, match="You are holding"):
        # 2C is mine, so it cannot be revealed with P2
        s.add_claim(claimer=0, half_suit=0, holders=[2, 0, 0, 0, 0, 0])


def test_cannot_claim_the_same_half_suit_twice():
    s = CoachSession.create(seat=0, hand_names=HAND)
    s.add_claim(claimer=1, half_suit=3, holders=[1, 1, 3, 3, 5, 5])
    with pytest.raises(CoachError, match="already been claimed"):
        s.add_claim(claimer=3, half_suit=3, holders=[1, 1, 3, 3, 5, 5])
