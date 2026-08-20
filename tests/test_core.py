from __future__ import annotations

from dataclasses import fields
import random

import pytest

from fish.core import (
    AskAction,
    AskEvent,
    BadClaimAward,
    ClaimAction,
    ClaimOutcome,
    ClaimTiming,
    FishEnv,
    ForcedClaimsStartedEvent,
    GamePhase,
    HouseRules,
    IllegalAction,
    NULL_OWNER,
    Ruleset,
    SelectForcedClaimerAction,
    SelectSuccessorAction,
    SuccessorSelectedEvent,
    deal_for_seed,
    team_of,
    validate_deal,
)


def round_robin_deal(ruleset: Ruleset) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(range(player, ruleset.deck_size, 6)) for player in range(6))


def team_zero_owns_first_half(ruleset: Ruleset) -> tuple[tuple[int, ...], ...]:
    hands = [list(hand) for hand in round_robin_deal(ruleset)]
    # Swap each odd-owned card in half-suit zero for a card held by the even player.
    for odd_card, replacement in ((1, 6), (3, 8), (5, 10)):
        odd_player = odd_card % 6
        even_player = replacement % 6
        hands[odd_player].remove(odd_card)
        hands[even_player].remove(replacement)
        hands[odd_player].append(replacement)
        hands[even_player].append(odd_card)
    return validate_deal(ruleset, hands)


@pytest.mark.parametrize(
    ("ruleset", "deck_size", "half_suits", "hand_size"),
    [
        (Ruleset.standard_48(), 48, 8, 8),
        (Ruleset.joker_54(), 54, 9, 9),
    ],
)
def test_ruleset_catalogue_and_seeded_deal(ruleset, deck_size, half_suits, hand_size):
    assert ruleset.deck_size == deck_size
    assert ruleset.num_half_suits == half_suits
    assert all(len(half.cards) == 6 for half in ruleset.half_suits)
    assert deal_for_seed(ruleset, 1234) == deal_for_seed(ruleset, 1234)
    deal = deal_for_seed(ruleset, 1234)
    assert all(len(hand) == hand_size for hand in deal)
    assert sorted(card for hand in deal for card in hand) == list(range(deck_size))


def test_54_variant_has_unique_jokers_and_eights_half_suit():
    ruleset = Ruleset.joker_54()
    special = ruleset.half_suits[8]
    assert [ruleset.cards[c].name for c in special.cards] == ["8C", "8D", "8H", "8S", "JK1", "JK2"]
    assert ruleset.card("joker 1").id != ruleset.card("joker 2").id
    assert ruleset.card("8s").half_suit == 8


def test_validate_deal_rejects_duplicate_and_wrong_hand_size():
    ruleset = Ruleset.standard_48()
    deal = [list(hand) for hand in round_robin_deal(ruleset)]
    deal[0][0] = deal[1][0]
    with pytest.raises(ValueError):
        validate_deal(ruleset, deal)
    with pytest.raises(ValueError):
        validate_deal(ruleset, round_robin_deal(Ruleset.joker_54()))


def test_successful_ask_transfers_card_and_retains_turn():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    transition = env.step(AskAction(0, 1, 1))
    assert isinstance(transition.event, AskEvent)
    assert transition.event.success
    assert transition.event.card_counts == (10, 8, 9, 9, 9, 9)
    assert env.current_player == 0
    assert 1 in env.observe(0).own_hand
    assert 1 not in env.observe(1).own_hand


def test_failed_ask_passes_turn_to_target():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    transition = env.step(AskAction(0, 3, 1))
    assert not transition.event.success
    assert transition.event.card_counts == (9, 9, 9, 9, 9, 9)
    assert env.current_player == 3


@pytest.mark.parametrize(
    "action",
    [
        AskAction(1, 0, 1),  # not the turn
        AskAction(0, 2, 1),  # teammate
        AskAction(0, 1, 0),  # already owns it
        AskAction(0, 1, 99),  # not in deck
    ],
)
def test_illegal_asks_are_rejected(action):
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    with pytest.raises(IllegalAction):
        env.step(action)


def test_asker_must_hold_a_card_from_requested_half_suit():
    ruleset = Ruleset.joker_54()
    contiguous = tuple(tuple(range(player * 9, (player + 1) * 9)) for player in range(6))
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=contiguous, turn=0)
    with pytest.raises(IllegalAction):
        env.step(AskAction(0, 1, 12))


def test_owned_card_bluff_is_configurable_and_always_fails():
    ruleset = Ruleset.joker_54(HouseRules(allow_owned_card_bluff=True))
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=0)
    transition = env.step(AskAction(0, 1, 0))
    assert not transition.event.success
    assert env.current_player == 1


def test_correct_claim_scores_and_removes_six_cards():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=0)
    allocation = (0, 0, 2, 2, 4, 4)
    transition = env.step(ClaimAction(0, 0, allocation))
    assert transition.event.outcome == ClaimOutcome.CORRECT
    assert transition.event.awarded_team == 0
    assert transition.event.revealed_owners == allocation
    assert env.scores == (1, 0)
    state = env.full_state()
    assert state.resolved_owners[0] == 0
    assert all(state.owners[card] == -1 for card in ruleset.half_suits[0].cards)
    assert sum(state.card_counts) == 48


def test_wrong_teammate_distribution_is_null_by_default():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=0)
    transition = env.step(ClaimAction(0, 0, (0, 0, 0, 2, 4, 4)))
    assert transition.event.outcome == ClaimOutcome.MISDISTRIBUTED
    assert transition.event.awarded_team is None
    assert env.full_state().resolved_owners[0] == NULL_OWNER
    assert env.scores == (0, 0)


def test_opponent_held_claim_scores_for_opponent_by_default():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    transition = env.step(ClaimAction(0, 0, (0, 0, 2, 2, 4, 4)))
    assert transition.event.outcome == ClaimOutcome.OPPONENT_HELD
    assert transition.event.awarded_team == 1
    assert env.scores == (0, 1)
    assert transition.rewards == (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)


@pytest.mark.parametrize(
    ("award", "expected_resolution", "score"),
    [
        (BadClaimAward.OPPONENT, 1, (0, 1)),
        (BadClaimAward.CLAIMING_TEAM, 0, (1, 0)),
        (BadClaimAward.NULL, NULL_OWNER, (0, 0)),
    ],
)
def test_misdistributed_claim_house_rules(award, expected_resolution, score):
    ruleset = Ruleset.joker_54(HouseRules(misdistributed_claim_award=award))
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=0)
    env.step(ClaimAction(0, 0, (0, 0, 0, 2, 4, 4)))
    assert env.full_state().resolved_owners[0] == expected_resolution
    assert env.scores == score


def test_claim_mapping_helper_uses_canonical_card_order():
    ruleset = Ruleset.standard_48()
    cards = ruleset.half_suits[0].cards
    mapping = dict(zip(cards, (0, 0, 2, 2, 4, 4), strict=True))
    action = ClaimAction.from_mapping(0, 0, mapping, ruleset)
    assert action.allocation == (0, 0, 2, 2, 4, 4)
    assert action.as_mapping(ruleset) == mapping
    with pytest.raises(ValueError):
        ClaimAction.from_mapping(0, 0, {cards[0]: 0}, ruleset)


def test_claim_timing_and_next_teammate_are_configurable():
    house = HouseRules(
        claim_timing=ClaimTiming.ANY_TURN,
        claimant_chooses_next_teammate=True,
    )
    ruleset = Ruleset.joker_54(house)
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=1)
    transition = env.step(ClaimAction(2, 0, (0, 0, 2, 2, 4, 4), next_player=4))
    assert transition.event.outcome == ClaimOutcome.CORRECT
    assert env.current_player == 4


def test_claim_reveal_can_be_disabled():
    ruleset = Ruleset.joker_54(HouseRules(reveal_claim_distribution=False))
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    transition = env.step(ClaimAction(0, 0, (0, 0, 2, 2, 4, 4)))
    assert transition.event.revealed_owners is None


def test_mandatory_claim_mask_does_not_use_hidden_teammate_cards():
    ruleset = Ruleset.joker_54(HouseRules(mandatory_immediate_claims=True))
    env = FishEnv(ruleset, seed=1)
    # Team zero collectively owns the set, but player zero cannot see all of it.
    env.reset(deal=team_zero_owns_first_half(ruleset), turn=0)
    assert env.mandatory_claim_half_suits(0) == ()
    assert env.legal_asks(0)

    contiguous = tuple(tuple(range(player * 9, (player + 1) * 9)) for player in range(6))
    env.reset(deal=contiguous, turn=0)
    assert env.mandatory_claim_half_suits(0) == (0,)
    assert env.legal_asks(0) == ()
    assert env.legal_claim_half_suits(0) == (0,)
    assert env.legal_actions(0) == (ClaimAction(0, 0, (0, 0, 0, 0, 0, 0)),)
    with pytest.raises(IllegalAction):
        env.step(ClaimAction(0, 0, (0, 0, 0, 0, 0, 2)))


def test_legal_claims_enumerate_all_public_allocations_not_only_true_one():
    ruleset = Ruleset.standard_48()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    actions = env.legal_actions(0, include_claims=True)
    claims_for_zero = [a for a in actions if isinstance(a, ClaimAction) and a.half_suit == 0]
    assert len(claims_for_zero) == 3**6
    assert all(set(action.allocation) <= {0, 2, 4} for action in claims_for_zero)


def test_observation_contains_no_privileged_state_or_opponent_hands():
    ruleset = Ruleset.joker_54()
    deal_a = [list(hand) for hand in round_robin_deal(ruleset)]
    deal_b = [hand.copy() for hand in deal_a]
    # Change whether P1 owns 1 while preserving every public count and P0's hand.
    deal_b[1].remove(1)
    deal_b[3].remove(3)
    deal_b[1].append(3)
    deal_b[3].append(1)
    env_a = FishEnv(ruleset, seed=1)
    env_b = FishEnv(ruleset, seed=1)
    obs_a = env_a.reset(deal=deal_a, turn=0)
    obs_b = env_b.reset(deal=deal_b, turn=0)

    assert obs_a == obs_b
    assert AskAction(0, 1, 1) in obs_a.legal_asks
    assert AskAction(0, 1, 1) in obs_b.legal_asks
    names = {item.name for item in fields(obs_a)}
    assert names.isdisjoint({"hands", "owners", "state", "environment", "env"})
    assert not hasattr(obs_a, "__dict__")  # slots block accidental hidden attachments

    # Identical pre-action policy inputs can legitimately lead to different results.
    assert env_a.step(AskAction(0, 1, 1)).event.success
    assert not env_b.step(AskAction(0, 1, 1)).event.success


def test_public_history_is_identical_for_every_observer():
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=round_robin_deal(ruleset), turn=0)
    event = env.step(AskAction(0, 1, 1)).event
    for player in range(6):
        observation = env.observe(player)
        assert observation.history == (event,)
        assert observation.card_counts == (10, 8, 9, 9, 9, 9)


def test_full_state_and_clone_are_detached():
    env = FishEnv(Ruleset.joker_54(), seed=987)
    privileged = env.full_state()
    privileged.hands[0] = 0
    assert env.full_state().hands[0] != 0
    clone = env.clone()
    action = env.sample_legal_action(claim_probability=0.0)
    env.step(action)
    assert clone.history == ()
    assert clone.full_state().hands != env.full_state().hands or clone.current_player != env.current_player


@pytest.mark.parametrize("ruleset_factory", [Ruleset.standard_48, Ruleset.joker_54])
def test_randomized_games_preserve_all_invariants(ruleset_factory):
    # Random claims guarantee progressive resolution, while asks exercise transfers.
    for seed in range(40):
        ruleset = ruleset_factory()
        env = FishEnv(ruleset, seed=seed, debug=True)
        rng = random.Random(seed ^ 0xF15A)
        for _ in range(500):
            if env.done:
                break
            action = env.sample_legal_action(rng=rng, claim_probability=0.18)
            transition = env.step(action)
            state = env.full_state()
            state.validate()
            assert sum(state.card_counts) + 6 * sum(
                owner != -1 for owner in state.resolved_owners
            ) == ruleset.deck_size
            assert transition.observation.player == env.current_player
        assert env.done, f"seed {seed} did not terminate"
        assert sum(env.scores) + env.full_state().resolved_owners.count(NULL_OWNER) == ruleset.num_half_suits
        assert sum(env.full_state().card_counts) == 0


def test_team_layout_is_fixed_and_alternating():
    assert tuple(team_of(player) for player in range(6)) == (0, 1, 0, 1, 0, 1)


def test_emptied_turn_player_explicitly_selects_active_teammate():
    ruleset = Ruleset.joker_54()
    contiguous = tuple(tuple(range(player * 9, (player + 1) * 9)) for player in range(6))
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=contiguous, turn=0)
    # Remove P0's three high clubs (and three opposing cards), leaving only low clubs.
    env.step(ClaimAction(0, 1, (0, 0, 0, 2, 2, 2)))
    env.step(ClaimAction(0, 0, (0, 0, 0, 0, 0, 0)))

    observation = env.observe(0)
    assert observation.phase == GamePhase.SELECT_SUCCESSOR
    assert observation.pending_selector == 0
    assert observation.legal_asks == ()
    assert observation.legal_claim_half_suits == ()
    assert set(observation.legal_admin_actions) == {
        SelectSuccessorAction(0, 2),
        SelectSuccessorAction(0, 4),
    }
    with pytest.raises(IllegalAction):
        env.step(AskAction(0, 1, 12))

    transition = env.step(SelectSuccessorAction(0, 4))
    assert isinstance(transition.event, SuccessorSelectedEvent)
    assert env.phase == GamePhase.PLAY
    assert env.current_player == 4


def test_empty_team_selects_forced_claimer_who_keeps_role_when_cardless():
    ruleset = Ruleset.joker_54()
    # Team A owns IDs 0..26; Team B owns 27..53. Resolving half-suits
    # 0..4 therefore empties A while four B-only half-suits remain.
    deal = (
        tuple(range(0, 9)),
        tuple(range(27, 36)),
        tuple(range(9, 18)),
        tuple(range(36, 45)),
        tuple(range(18, 27)),
        tuple(range(45, 54)),
    )
    env = FishEnv(ruleset, seed=1)
    env.reset(deal=deal, turn=0)

    env.step(ClaimAction(0, 0, (0, 0, 0, 0, 0, 0)))
    env.step(ClaimAction(0, 1, (0, 0, 0, 2, 2, 2)))
    assert env.phase == GamePhase.SELECT_SUCCESSOR
    env.step(SelectSuccessorAction(0, 2))
    env.step(ClaimAction(2, 2, (2, 2, 2, 2, 2, 2)))
    assert env.phase == GamePhase.SELECT_SUCCESSOR
    env.step(SelectSuccessorAction(2, 4))
    env.step(ClaimAction(4, 3, (4, 4, 4, 4, 4, 4)))
    # This claim contains three Team B cards, but removes Team A's final cards.
    env.step(ClaimAction(4, 4, (4, 4, 4, 4, 4, 4)))

    observation = env.observe(4)
    assert observation.phase == GamePhase.SELECT_FORCED_CLAIMER
    assert set(observation.legal_admin_actions) == {
        SelectForcedClaimerAction(4, 1),
        SelectForcedClaimerAction(4, 3),
        SelectForcedClaimerAction(4, 5),
    }
    transition = env.step(SelectForcedClaimerAction(4, 1))
    assert isinstance(transition.event, ForcedClaimsStartedEvent)
    assert env.phase == GamePhase.FORCED_CLAIMS
    assert env.current_player == 1
    assert env.legal_asks(1) == ()

    # P1 owns all of half-suit five and loses its last six cards by declaring it.
    env.step(ClaimAction(1, 5, (1, 1, 1, 1, 1, 1)))
    assert env.observe(1).own_hand == ()
    assert env.phase == GamePhase.FORCED_CLAIMS
    assert env.current_player == 1
    assert env.legal_claim_half_suits(1) == (6, 7, 8)

    # The forced role, not ordinary hand activity, authorizes every final claim.
    while not env.done:
        half_suit = env.legal_claim_half_suits(1)[0]
        state = env.full_state()
        actual = tuple(state.owners[card] for card in ruleset.half_suits[half_suit].cards)
        env.step(ClaimAction(1, half_suit, actual))
    assert env.phase == GamePhase.TERMINAL
    assert env.full_state().card_counts == (0, 0, 0, 0, 0, 0)
