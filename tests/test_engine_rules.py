import pytest

from fish.cards import card_id
from fish.engine import Ask, Claim, Pass, ClaimEvent, IllegalAction, NULL_TEAM
from fish.rules import RuleConfig

from helpers import make_state, mask


def cid(name: str) -> int:
    return card_id(name)


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------

def test_successful_ask_transfers_card_and_keeps_turn():
    s = make_state([["2C", "3C"], ["4C"], ["5C"], ["6C"], ["7C"], []], turn=0)
    ev = s.apply(0, Ask(1, cid("4C")))
    assert ev.success
    assert s.hands[0] & (1 << cid("4C"))
    assert not s.hands[1] & (1 << cid("4C"))
    assert s.turn == 0


def test_failed_ask_passes_turn_to_target():
    s = make_state([["2C", "3C"], ["4C"], ["5C", "6C", "7C"], [], [], []], turn=0)
    ev = s.apply(0, Ask(1, cid("5C")))  # 5C is with P2, not P1
    assert not ev.success
    assert s.turn == 1


def test_cannot_ask_teammate():
    s = make_state([["2C"], ["4C", "5C"], ["3C"], ["6C"], [], ["7C"]], turn=0)
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(2, cid("3C")))


def test_cannot_ask_without_card_in_half_suit():
    s = make_state([["2C"], ["9H"], ["3C", "4C"], ["TH", "JH"],
                    ["5C", "6C", "7C"], ["QH", "KH", "AH"]], turn=0)
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(1, cid("9H")))


def test_cannot_ask_for_card_you_hold():
    s = make_state([["2C", "3C"], ["4C"], ["5C", "6C", "7C"], [], [], []], turn=0)
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(1, cid("3C")))


def test_bluff_ask_allowed_when_configured():
    rules = RuleConfig(allow_bluff_asks=True)
    s = make_state([["2C", "3C"], ["4C"], ["5C", "6C", "7C"], [], [], []],
                   rules=rules, turn=0)
    ev = s.apply(0, Ask(1, cid("3C")))  # asking for a card you hold: always "no"
    assert not ev.success
    assert s.turn == 1


def test_cannot_ask_cardless_target():
    s = make_state([
        ["2C", "3C", "2D"], ["4C"], ["5C", "6C", "7C"],
        ["2H", "3H", "4H", "5H", "6H", "7H"], ["3D", "4D"], ["5D", "6D", "7D"],
    ], turn=0)
    s.apply(0, Ask(1, cid("4C")))
    assert s.hand_count(1) == 0
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(1, cid("5C")))


def test_cannot_ask_out_of_turn():
    s = make_state([["2C"], ["3C"], ["4C", "5C", "6C", "7C"], [], [], []], turn=0)
    with pytest.raises(IllegalAction):
        s.apply(1, Ask(0, cid("2C")))


def test_cannot_ask_from_resolved_half_suit():
    s = make_state([
        ["2C", "2D", "3D"], ["3C"], ["4C", "5C"], [],
        ["6C", "7C"], ["4D", "5D", "6D", "7D"],
    ], turn=0)
    s.apply(0, Claim(0, (0, 2, 2, 0, 4, 4)))
    assert s.set_winner[0] is not None
    assert s.turn == 0
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(5, cid("3C")))


def test_legal_asks_enumeration_matches_rules():
    s = make_state([
        ["2C", "3C", "9H"], ["4C"], ["5C"],
        ["TH", "JH", "QH", "KH", "AH"], ["6C"], ["7C"],
    ], turn=0)
    asks = s.legal_asks(0)
    targets = {a.target for a in asks}
    cards = {a.card for a in asks}
    assert targets <= {1, 3, 5}
    assert cid("4C") in cards and cid("TH") in cards
    assert cid("2C") not in cards      # own card
    assert cid("2D") not in cards      # holds no Low Diamonds
    assert len(asks) == 9 * 3          # 9 unheld cards x 3 opponents


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

def _low_clubs_split_state(rules=None, turn=0):
    # Low clubs: P0 has 2C,3C; P2 has 4C; P4 has 5C,6C,7C (all team 0).
    return make_state([
        ["2C", "3C", "2H", "3H"], ["9D", "TD", "JD"], ["4C", "4H"],
        ["9H", "QH", "6H", "7H"], ["5C", "6C", "7C", "5H"],
        ["TH", "JH", "KH", "AH", "QD", "KD", "AD"],
    ], rules=rules, turn=turn)


def test_correct_claim_scores_for_team():
    s = _low_clubs_split_state()
    ev = s.apply(0, Claim(0, (0, 0, 2, 4, 4, 4)))
    assert isinstance(ev, ClaimEvent)
    assert ev.winner == 0
    assert s.set_winner[0] == 0
    assert s.hands[0] & mask("2C", "3C") == 0
    assert s.turn == 0


def test_claim_with_opponent_card_goes_to_opponents():
    s = make_state([
        ["2C", "3C", "2H", "3H"], ["4C"], ["5C", "4H"],
        ["9H", "TH", "JH"], ["6C", "7C", "5H", "6H", "7H"],
        ["QH", "KH", "AH"],
    ], turn=0)
    ev = s.apply(0, Claim(0, (0, 0, 2, 4, 4, 4)))
    assert ev.winner == 1
    assert s.set_winner[0] == 1


def test_wrong_distribution_within_team_awards_opponents_by_default():
    """The baseline: a misdeclared half-suit is the opposing team's set."""
    s = _low_clubs_split_state()
    nulls_before = s.scores()[2]
    ev = s.apply(0, Claim(0, (0, 2, 2, 4, 4, 4)))
    assert ev.winner == 1
    a, b, n = s.scores()
    assert (a, b) == (0, 1) and n == nulls_before


def test_wrong_distribution_configurable_to_null_variant():
    """The v0.4-era void rule stays reproducible, as an explicit variant."""
    rules = RuleConfig(wrong_distribution_outcome="null")
    s = _low_clubs_split_state(rules=rules)
    nulls_before = s.scores()[2]
    ev = s.apply(0, Claim(0, (0, 2, 2, 4, 4, 4)))
    assert ev.winner == NULL_TEAM
    a, b, n = s.scores()
    assert (a, b) == (0, 0) and n == nulls_before + 1


def test_claim_reveals_actual_holders():
    s = _low_clubs_split_state()
    ev = s.apply(0, Claim(0, (0, 0, 2, 4, 4, 4)))
    assert ev.revealed == (0, 0, 2, 4, 4, 4)


def test_claim_assignment_must_be_own_team():
    s = _low_clubs_split_state()
    with pytest.raises(IllegalAction):
        s.apply(0, Claim(0, (0, 0, 1, 4, 4, 4)))


def test_claim_off_turn_illegal_by_default_legal_when_configured():
    s = _low_clubs_split_state()
    with pytest.raises(IllegalAction):
        s.apply(2, Claim(0, (0, 0, 2, 4, 4, 4)))
    rules = RuleConfig(claims_any_time=True)
    s2 = _low_clubs_split_state(rules=rules)
    ev = s2.apply(2, Claim(0, (0, 0, 2, 4, 4, 4)))
    assert ev.winner == 0
    assert s2.turn == 0  # off-turn claim does not steal the turn


def test_cannot_claim_resolved_half_suit_twice():
    s = _low_clubs_split_state()
    s.apply(0, Claim(0, (0, 0, 2, 4, 4, 4)))
    with pytest.raises(IllegalAction):
        s.apply(0, Claim(0, (0, 0, 2, 4, 4, 4)))


def test_claim_assignment_accepts_any_sequence_type():
    """A factually exact claim must score for the claiming team regardless of
    how the assignment was built. Comparing a tuple to a list is always False
    in Python, which once nulled perfectly correct claims from any caller
    that produced lists (e.g. RL action decoding)."""
    s = _low_clubs_split_state()
    ev = s.apply(0, Claim(0, [0, 0, 2, 4, 4, 4]))   # list, not tuple
    assert ev.winner == 0
    assert ev.declared == ev.revealed == (0, 0, 2, 4, 4, 4)


def test_pass_rejects_out_of_range_teammate():
    """check_legal is the safety boundary: bad ids must raise IllegalAction,
    never corrupt the turn (Pass(-1) once wrapped to seat 5) or crash."""
    s = make_state([
        ["2C", "3C", "4C", "5C", "6C", "7C"], ["9D", "TD"],
        ["2H", "3H", "4H"], ["9H", "JD", "QD", "KD", "AD"],
        ["5H", "6H", "7H"], ["TH", "JH", "QH", "KH", "AH"],
    ], turn=0)
    s.apply(0, Claim(0, (0,) * 6))     # P0 is now cardless and must pass
    assert s.hand_count(0) == 0
    for bad in (-1, 6, 7, 99):
        with pytest.raises(IllegalAction):
            s.apply(0, Pass(bad))
    assert s.turn == 0                 # state uncorrupted
    s.apply(0, Pass(2))
    assert s.turn == 2


def test_opponent_claim_of_set_you_hold_awards_your_team():
    s = make_state([
        ["2C", "2H"], ["3C", "4C"], ["3H"], ["5C", "6C"],
        ["4H", "5H", "6H", "7H"], ["7C"],
    ], turn=1)
    ev = s.apply(1, Claim(0, (1, 1, 1, 3, 3, 5)))
    assert ev.winner == 0


# ---------------------------------------------------------------------------
# Passing / cardless players / endgame
# ---------------------------------------------------------------------------

def test_cardless_after_own_claim_must_pass_to_teammate_with_cards():
    s = make_state([
        ["2C", "3C", "4C", "5C", "6C", "7C"], ["9D", "TD"],
        ["2H", "3H", "4H"], ["9H", "JD", "QD", "KD", "AD"],
        ["5H", "6H", "7H"], ["TH", "JH", "QH", "KH", "AH"],
    ], turn=0)
    s.apply(0, Claim(0, (0,) * 6))
    assert s.hand_count(0) == 0
    assert s.turn == 0
    assert s.legal_asks(0) == []
    assert {p.teammate for p in s.legal_passes(0)} == {2, 4}
    with pytest.raises(IllegalAction):
        s.apply(0, Ask(1, cid("9H")))
    with pytest.raises(IllegalAction):
        s.apply(0, Pass(1))  # opponent
    s.apply(0, Pass(2))
    assert s.turn == 2


def test_turn_auto_advances_when_whole_team_cardless():
    s = make_state([
        ["2C", "3C", "4C", "5C", "6C", "7C"], ["9D", "TD", "JD"], [],
        ["QD", "KD", "AD"], [], ["9H", "TH", "JH", "QH", "KH", "AH"],
    ], turn=0)
    s.apply(0, Claim(0, (0,) * 6))
    assert s.turn in (1, 3, 5)
    assert s.hand_count(s.turn) > 0


def test_forced_claim_when_no_asks_available():
    s = make_state([
        ["2C", "3C", "4C", "5C", "6C", "7C"], ["9D", "TD", "JD"],
        ["2H", "3H", "4H"], ["QD", "KD", "AD"], ["5H", "6H", "7H"],
        ["9H", "TH", "JH", "QH", "KH", "AH"],
    ], turn=0)
    assert s.legal_asks(0) == []
    assert s.must_claim(0)
    ev = s.apply(0, Claim(0, (0,) * 6))
    assert ev.winner == 0


def test_endgame_opposing_team_out_of_cards_forces_claims():
    s = make_state([
        ["2C", "3C"], [], ["4C", "5C"], [], ["6C", "7C"], [],
    ], turn=0)
    assert s.legal_asks(0) == []
    assert s.must_claim(0)
    ev = s.apply(0, Claim(0, (0, 0, 2, 2, 4, 4)))
    assert ev.winner == 0
    assert s.is_terminal
    a, b, n = s.scores()
    assert (a, b) == (1, 0) and a + b + n == 9


def test_claim_does_not_end_nonfinal_game():
    s = make_state([
        ["2C", "3C"], ["9D", "TD", "JD"], ["4C", "5C"],
        ["QD", "KD", "AD"], ["6C", "7C"], ["9H", "TH", "JH", "QH", "KH", "AH"],
    ], turn=0)
    s.apply(0, Claim(0, (0, 0, 2, 2, 4, 4)))
    assert s.set_winner[0] == 0
    assert not s.is_terminal


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

def test_48_variant_deals_and_plays():
    from fish.engine import GameState
    rules = RuleConfig(variant="48")
    s = GameState.deal(rules, seed=7, debug=True)
    assert sum(s.hand_counts()) == 48
    assert all(c == 8 for c in s.hand_counts())
    assert len(s.set_winner) == 8
    for h in s.hands:
        assert h < (1 << 48)  # no 8s or jokers anywhere


def test_54_variant_deals_nine_each():
    from fish.engine import GameState
    s = GameState.deal(RuleConfig(), seed=7, debug=True)
    assert sum(s.hand_counts()) == 54
    assert all(c == 9 for c in s.hand_counts())
    assert len(s.set_winner) == 9


def test_jokers_are_individually_askable():
    s = make_state([["8C", "8D"], ["RJ"], ["BJ", "8H", "8S"], [], [], []],
                   turn=0)
    ev = s.apply(0, Ask(1, cid("RJ")))   # ask for the RED joker specifically
    assert ev.success
    assert s.hands[0] & (1 << cid("RJ"))
    assert not s.hands[0] & (1 << cid("BJ"))   # the black one stayed put
    ev2 = s.apply(0, Claim(8, (0, 0, 2, 2, 0, 2)))
    assert ev2.winner == 0
