from fish.cards import (
    BLACK_JOKER, CARD_NAMES, RED_JOKER, card_id, card_long_name, card_name,
    cards_per_player, deck_size, half_suit_cards, half_suit_mask,
    half_suit_of, is_red, mask_to_cards, num_half_suits, opponents, team_of,
    teammates,
)


def test_deck_composition():
    assert len(CARD_NAMES) == 54
    assert len(set(CARD_NAMES)) == 54
    assert [card_name(c) for c in half_suit_cards(0)] == \
        ["2C", "3C", "4C", "5C", "6C", "7C"]
    assert [card_name(c) for c in half_suit_cards(7)] == \
        ["9S", "TS", "JS", "QS", "KS", "AS"]
    assert [card_name(c) for c in half_suit_cards(8)] == \
        ["8C", "8D", "8H", "8S", "RJ", "BJ"]
    assert card_id("RJ") != card_id("BJ")


def test_jokers_are_red_and_black():
    assert card_name(RED_JOKER) == "RJ"
    assert card_name(BLACK_JOKER) == "BJ"
    assert card_long_name(RED_JOKER) == "Red Joker"
    assert card_long_name(BLACK_JOKER) == "Black Joker"
    assert is_red(RED_JOKER) and not is_red(BLACK_JOKER)
    assert is_red(card_id("2H")) and is_red(card_id("AD"))
    assert not is_red(card_id("2C")) and not is_red(card_id("KS"))


def test_joker_name_aliases_parse():
    for alias in ("RJ", "rj", "X1", "joker1", "Red Joker", "red"):
        assert card_id(alias) == RED_JOKER
    for alias in ("BJ", "bj", "X2", "joker2", "Black Joker", "black"):
        assert card_id(alias) == BLACK_JOKER


def test_half_suit_structure():
    for c in range(54):
        assert c in half_suit_cards(half_suit_of(c))
        assert half_suit_mask(half_suit_of(c)) & (1 << c)
    assert deck_size("48") == 48 and deck_size("54") == 54
    assert num_half_suits("48") == 8 and num_half_suits("54") == 9
    assert cards_per_player("48") == 8 and cards_per_player("54") == 9
    # the 48-card variant uses exactly cards 0..47: no 8s, no jokers
    for hs in range(8):
        for c in half_suit_cards(hs):
            assert c < 48
            name = card_name(c)
            assert not name.startswith("8"), f"{name} is an 8"
            assert name not in ("RJ", "BJ"), f"{name} is a joker"


def test_teams():
    assert team_of(0) == team_of(2) == team_of(4) == 0
    assert team_of(1) == team_of(3) == team_of(5) == 1
    assert teammates(0) == (0, 2, 4)
    assert teammates(3) == (1, 3, 5)
    assert opponents(0) == (1, 3, 5)
    assert opponents(5) == (0, 2, 4)


def test_mask_to_cards():
    assert mask_to_cards(0) == []
    assert mask_to_cards(0b1011) == [0, 1, 3]
    assert mask_to_cards(1 << 53) == [53]
