"""Test helpers: build exact GameStates from card names."""

from fish.cards import card_id, half_suit_cards, num_half_suits
from fish.engine import GameState, NULL_TEAM
from fish.rules import RuleConfig


def mask(*names: str) -> int:
    m = 0
    for n in names:
        m |= 1 << card_id(n)
    return m


def make_state(hands_by_name: list[list[str]], rules: RuleConfig | None = None,
               turn: int = 0, debug: bool = True) -> GameState:
    """Build a state with EXACTLY the given six hands.

    Every half-suit must be either fully listed across the hands or not
    listed at all; unlisted half-suits are marked pre-resolved (null) so the
    deck stays consistent while tests stay small and precise.
    """
    rules = rules or RuleConfig()
    hands = [0] * 6
    used = 0
    for p, names in enumerate(hands_by_name):
        hands[p] = mask(*names)
        assert hands[p] & used == 0, "card assigned twice"
        used |= hands[p]
    pre_resolved = []
    for hs in range(num_half_suits(rules.variant)):
        listed = [c for c in half_suit_cards(hs) if used & (1 << c)]
        if not listed:
            pre_resolved.append(hs)
        elif len(listed) != 6:
            raise ValueError(
                f"half-suit {hs} partially listed ({len(listed)}/6): "
                "list all six cards or none")
    state = GameState(rules, hands, turn, debug=debug)
    for hs in pre_resolved:
        state.set_winner[hs] = NULL_TEAM
    if debug:
        state.check_invariants()
    return state
