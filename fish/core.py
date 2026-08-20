"""Correct, information-safe simulation core for six-player Literature/Fish.

Cards are rich immutable metadata objects at the rules boundary and compact integer
IDs everywhere on the hot path.  A policy should receive only ``PlayerObservation``;
``GameState`` is deliberately a separate privileged type for the environment and
centralized training critics.
"""

from __future__ import annotations

import copy
import itertools
import random
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Iterable, Mapping, Sequence, TypeAlias


NUM_PLAYERS = 6
TEAM_A = (0, 2, 4)
TEAM_B = (1, 3, 5)
NULL_OWNER = 2
UNRESOLVED = -1
NO_OWNER = -1

CardId: TypeAlias = int


def team_of(player: int) -> int:
    """Return the fixed alternating-seating team for ``player``."""
    if not 0 <= player < NUM_PLAYERS:
        raise ValueError(f"invalid player: {player}")
    return player & 1


def teammates(player: int) -> tuple[int, int, int]:
    return TEAM_A if team_of(player) == 0 else TEAM_B


def opponents(player: int) -> tuple[int, int, int]:
    return TEAM_B if team_of(player) == 0 else TEAM_A


class ClaimTiming(str, Enum):
    TURN_ONLY = "turn_only"
    ANY_TURN = "any_turn"


class BadClaimAward(str, Enum):
    """Who receives a half-suit after a particular kind of bad claim."""

    NULL = "null"
    OPPONENT = "opponent"
    CLAIMING_TEAM = "claiming_team"


class ClaimOutcome(str, Enum):
    CORRECT = "correct"
    OPPONENT_HELD = "opponent_held"
    MISDISTRIBUTED = "misdistributed"


class GamePhase(str, Enum):
    PLAY = "play"
    SELECT_SUCCESSOR = "select_successor"
    SELECT_FORCED_CLAIMER = "select_forced_claimer"
    FORCED_CLAIMS = "forced_claims"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class HouseRules:
    """Configurable rule points that vary among Literature groups.

    ``mandatory_immediate_claims`` is intentionally based only on a personally
    complete six-card hand.  Making legality depend on a teammate's hidden cards
    would leak that information through the action mask.
    """

    claim_timing: ClaimTiming = ClaimTiming.TURN_ONLY
    mandatory_immediate_claims: bool = False
    claimant_chooses_next_teammate: bool = False
    allow_owned_card_bluff: bool = False
    misdistributed_claim_award: BadClaimAward = BadClaimAward.NULL
    opponent_held_claim_award: BadClaimAward = BadClaimAward.OPPONENT
    reveal_claim_distribution: bool = True
    cardless_players_may_claim: bool = False


@dataclass(frozen=True, slots=True)
class Card:
    id: CardId
    name: str
    rank: str
    suit: str | None
    half_suit: int


@dataclass(frozen=True, slots=True)
class HalfSuit:
    id: int
    name: str
    cards: tuple[CardId, CardId, CardId, CardId, CardId, CardId]

    @property
    def mask(self) -> int:
        mask = 0
        for card in self.cards:
            mask |= 1 << card
        return mask


@dataclass(frozen=True, slots=True)
class Ruleset:
    name: str
    cards: tuple[Card, ...]
    half_suits: tuple[HalfSuit, ...]
    house_rules: HouseRules = field(default_factory=HouseRules)

    def __post_init__(self) -> None:
        if len(self.cards) not in (48, 54):
            raise ValueError("a supported ruleset must have 48 or 54 cards")
        if len(self.cards) != 6 * len(self.half_suits):
            raise ValueError("every half-suit must contain exactly six cards")
        if tuple(card.id for card in self.cards) != tuple(range(len(self.cards))):
            raise ValueError("card IDs must be dense and ordered")
        seen: set[int] = set()
        for index, half_suit in enumerate(self.half_suits):
            if half_suit.id != index or len(half_suit.cards) != 6:
                raise ValueError("half-suit IDs must be dense and contain six cards")
            for card_id in half_suit.cards:
                if card_id in seen or self.cards[card_id].half_suit != index:
                    raise ValueError("invalid or duplicate half-suit membership")
                seen.add(card_id)
        if seen != set(range(len(self.cards))):
            raise ValueError("half-suits must partition the deck")

    @property
    def deck_size(self) -> int:
        return len(self.cards)

    @property
    def num_half_suits(self) -> int:
        return len(self.half_suits)

    def card(self, card: CardId | str) -> Card:
        if isinstance(card, int):
            if not 0 <= card < self.deck_size:
                raise KeyError(card)
            return self.cards[card]
        normalized = card.strip().upper().replace(" ", "")
        aliases = {"JOKER1": "JK1", "JOKER2": "JK2"}
        normalized = normalized.replace("_", "").replace("-", "")
        if normalized.startswith("10"):
            normalized = "T" + normalized[2:]
        normalized = aliases.get(normalized, normalized)
        for item in self.cards:
            if item.name.upper().replace(" ", "") == normalized:
                return item
        raise KeyError(card)

    def half_suit_mask(self, half_suit: int) -> int:
        if not 0 <= half_suit < self.num_half_suits:
            raise ValueError(f"invalid half-suit: {half_suit}")
        return self.half_suits[half_suit].mask

    @classmethod
    def standard_48(cls, house_rules: HouseRules | None = None) -> "Ruleset":
        return _build_ruleset(False, house_rules or HouseRules())

    @classmethod
    def joker_54(cls, house_rules: HouseRules | None = None) -> "Ruleset":
        return _build_ruleset(True, house_rules or HouseRules())

    # Friendly aliases used by configs and callers.
    classic_48 = standard_48
    variant_54 = joker_54


def _build_ruleset(include_eights_and_jokers: bool, house_rules: HouseRules) -> Ruleset:
    cards: list[Card] = []
    halves: list[HalfSuit] = []
    suits = (("Clubs", "C"), ("Diamonds", "D"), ("Hearts", "H"), ("Spades", "S"))
    rank_groups = (("Low", ("2", "3", "4", "5", "6", "7")),
                   ("High", ("9", "T", "J", "Q", "K", "A")))
    for suit_name, suit_short in suits:
        for group_name, ranks in rank_groups:
            half_id = len(halves)
            ids: list[int] = []
            for rank in ranks:
                card_id = len(cards)
                ids.append(card_id)
                cards.append(Card(card_id, f"{rank}{suit_short}", rank, suit_name, half_id))
            halves.append(HalfSuit(half_id, f"{group_name} {suit_name}", tuple(ids)))  # type: ignore[arg-type]

    if include_eights_and_jokers:
        half_id = len(halves)
        ids = []
        for suit_name, suit_short in suits:
            card_id = len(cards)
            ids.append(card_id)
            cards.append(Card(card_id, f"8{suit_short}", "8", suit_name, half_id))
        for joker_number in (1, 2):
            card_id = len(cards)
            ids.append(card_id)
            cards.append(Card(card_id, f"JK{joker_number}", f"Joker {joker_number}", None, half_id))
        halves.append(HalfSuit(half_id, "Eights and Jokers", tuple(ids)))  # type: ignore[arg-type]

    name = "54-card / 9-half-suit" if include_eights_and_jokers else "48-card standard"
    return Ruleset(name, tuple(cards), tuple(halves), house_rules)


@dataclass(frozen=True, slots=True)
class AskAction:
    asker: int
    target: int
    card: CardId


@dataclass(frozen=True, slots=True)
class ClaimAction:
    claimant: int
    half_suit: int
    # Owner at each position in Ruleset.half_suits[half_suit].cards.
    allocation: tuple[int, int, int, int, int, int]
    next_player: int | None = None

    @classmethod
    def from_mapping(
        cls,
        claimant: int,
        half_suit: int,
        mapping: Mapping[CardId, int],
        ruleset: Ruleset,
        next_player: int | None = None,
    ) -> "ClaimAction":
        cards = ruleset.half_suits[half_suit].cards
        if set(mapping) != set(cards):
            raise ValueError("claim mapping must contain exactly the half-suit's six cards")
        return cls(claimant, half_suit, tuple(mapping[card] for card in cards), next_player)  # type: ignore[arg-type]

    def as_mapping(self, ruleset: Ruleset) -> dict[CardId, int]:
        return dict(zip(ruleset.half_suits[self.half_suit].cards, self.allocation, strict=True))


@dataclass(frozen=True, slots=True)
class SelectSuccessorAction:
    """Public choice made when the player controlling the turn becomes empty."""

    selector: int
    successor: int


@dataclass(frozen=True, slots=True)
class SelectForcedClaimerAction:
    """An empty team chooses the opponent who must declare all remaining sets."""

    selector: int
    forced_claimer: int


AdministrativeAction: TypeAlias = SelectSuccessorAction | SelectForcedClaimerAction
Action: TypeAlias = AskAction | ClaimAction | AdministrativeAction


@dataclass(frozen=True, slots=True)
class AskEvent:
    asker: int
    target: int
    card: CardId
    success: bool
    card_counts: tuple[int, int, int, int, int, int]
    turn_after: int


@dataclass(frozen=True, slots=True)
class ClaimEvent:
    claimant: int
    half_suit: int
    allocation: tuple[int, int, int, int, int, int]
    outcome: ClaimOutcome
    awarded_team: int | None
    # Exact pre-claim owners are present only when the configured table rule makes
    # laying the claimed cards down public.
    revealed_owners: tuple[int, int, int, int, int, int] | None
    card_counts: tuple[int, int, int, int, int, int]
    turn_after: int


@dataclass(frozen=True, slots=True)
class SuccessorSelectedEvent:
    selector: int
    successor: int
    card_counts: tuple[int, int, int, int, int, int]
    turn_after: int


@dataclass(frozen=True, slots=True)
class ForcedClaimsStartedEvent:
    selector: int
    forced_claimer: int
    empty_team: int
    card_counts: tuple[int, int, int, int, int, int]
    turn_after: int


PublicEvent: TypeAlias = AskEvent | ClaimEvent | SuccessorSelectedEvent | ForcedClaimsStartedEvent


@dataclass(slots=True)
class GameState:
    """Privileged mutable simulator state. Never pass this object to a policy."""

    ruleset: Ruleset
    hands: list[int]
    owners: list[int]
    turn: int
    resolved_owners: list[int]
    scores: list[int]
    history: list[PublicEvent]
    phase: GamePhase = GamePhase.PLAY
    pending_selector: int | None = None
    forced_claimer: int | None = None
    ply: int = 0
    seed: int | None = None

    @property
    def done(self) -> bool:
        return all(owner != UNRESOLVED for owner in self.resolved_owners)

    @property
    def card_counts(self) -> tuple[int, int, int, int, int, int]:
        return tuple(hand.bit_count() for hand in self.hands)  # type: ignore[return-value]

    def clone(self) -> "GameState":
        return copy.deepcopy(self)

    def validate(self) -> None:
        rules = self.ruleset
        if len(self.hands) != NUM_PLAYERS or len(self.owners) != rules.deck_size:
            raise AssertionError("state dimensions do not match the ruleset")
        if len(self.resolved_owners) != rules.num_half_suits or len(self.scores) != 2:
            raise AssertionError("score/resolution dimensions do not match the ruleset")
        if not 0 <= self.turn < NUM_PLAYERS:
            raise AssertionError("turn is not a valid player")
        union = 0
        for player, hand in enumerate(self.hands):
            if union & hand:
                raise AssertionError("a card occurs in multiple hands")
            if hand >> rules.deck_size:
                raise AssertionError("hand contains an out-of-deck card")
            union |= hand
            bits = hand
            while bits:
                lsb = bits & -bits
                card = lsb.bit_length() - 1
                if self.owners[card] != player:
                    raise AssertionError("hand bit and owner table disagree")
                bits ^= lsb
        for half_suit in rules.half_suits:
            resolution = self.resolved_owners[half_suit.id]
            if resolution not in (UNRESOLVED, 0, 1, NULL_OWNER):
                raise AssertionError("invalid resolved owner")
            for card in half_suit.cards:
                owner = self.owners[card]
                in_hands = bool(union & (1 << card))
                if resolution == UNRESOLVED:
                    if owner not in range(NUM_PLAYERS) or not in_hands:
                        raise AssertionError("every unresolved card must have exactly one owner")
                elif owner != NO_OWNER or in_hands:
                    raise AssertionError("resolved cards must be removed from all hands")
        if self.scores != [self.resolved_owners.count(0), self.resolved_owners.count(1)]:
            raise AssertionError("scores disagree with resolved half-suits")
        if sum(self.card_counts) != 6 * self.resolved_owners.count(UNRESOLVED):
            raise AssertionError("card conservation failed")
        if self.ply != len(self.history):
            raise AssertionError("ply and public history length disagree")
        if self.done:
            if self.phase != GamePhase.TERMINAL:
                raise AssertionError("a resolved game must be in the terminal phase")
        elif self.phase == GamePhase.TERMINAL:
            raise AssertionError("terminal phase requires every half-suit resolved")
        elif self.phase == GamePhase.PLAY:
            if self.card_counts[self.turn] == 0:
                raise AssertionError("a cardless player may not own an ordinary turn")
            if all(self.card_counts[player] == 0 for player in opponents(self.turn)):
                raise AssertionError("ordinary play cannot continue after an opposing team empties")
            if self.pending_selector is not None or self.forced_claimer is not None:
                raise AssertionError("ordinary play may not retain pending administrative roles")
        elif self.phase == GamePhase.SELECT_SUCCESSOR:
            if self.pending_selector != self.turn or self.card_counts[self.turn] != 0:
                raise AssertionError("successor selection must belong to the emptied turn player")
            if not any(self.card_counts[p] for p in teammates(self.turn) if p != self.turn):
                raise AssertionError("successor selection requires an active teammate")
        elif self.phase == GamePhase.SELECT_FORCED_CLAIMER:
            if self.pending_selector != self.turn:
                raise AssertionError("forced-claimer selection must belong to the empty team's turn")
            if any(self.card_counts[p] for p in teammates(self.turn)):
                raise AssertionError("forced-claimer selection requires a wholly empty team")
        elif self.phase == GamePhase.FORCED_CLAIMS:
            if self.forced_claimer is None or self.turn != self.forced_claimer:
                raise AssertionError("forced-claim phase requires one stable forced claimer")
            claim_team = team_of(self.forced_claimer)
            if any(
                team_of(self.owners[card]) != claim_team
                for hs in self.ruleset.half_suits
                if self.resolved_owners[hs.id] == UNRESOLVED
                for card in hs.cards
            ):
                raise AssertionError("forced-claim team must own every unresolved card")


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    """The complete and only supported policy-facing view of a game."""

    ruleset: Ruleset
    player: int
    team: int
    own_hand: tuple[CardId, ...]
    turn: int
    phase: GamePhase
    pending_selector: int | None
    forced_claimer: int | None
    card_counts: tuple[int, int, int, int, int, int]
    scores: tuple[int, int]
    resolved_owners: tuple[int, ...]
    history: tuple[PublicEvent, ...]
    legal_asks: tuple[AskAction, ...]
    legal_claim_half_suits: tuple[int, ...]
    legal_admin_actions: tuple[AdministrativeAction, ...]
    done: bool
    ply: int


@dataclass(frozen=True, slots=True)
class Transition:
    event: PublicEvent
    observation: PlayerObservation
    rewards: tuple[float, float, float, float, float, float]
    terminated: bool


class IllegalAction(ValueError):
    pass


def validate_deal(ruleset: Ruleset, deal: Sequence[Iterable[CardId]]) -> tuple[tuple[int, ...], ...]:
    if len(deal) != NUM_PLAYERS:
        raise ValueError("a deal must contain six hands")
    normalized = tuple(tuple(sorted(hand)) for hand in deal)
    flat = tuple(card for hand in normalized for card in hand)
    if len(flat) != ruleset.deck_size or len(set(flat)) != ruleset.deck_size:
        raise ValueError("a deal must contain every card exactly once")
    if set(flat) != set(range(ruleset.deck_size)):
        raise ValueError("deal contains an invalid or missing card")
    expected = ruleset.deck_size // NUM_PLAYERS
    if any(len(hand) != expected for hand in normalized):
        raise ValueError(f"each initial hand must contain {expected} cards")
    return normalized


def deal_for_seed(ruleset: Ruleset, seed: int | None) -> tuple[tuple[int, ...], ...]:
    return _deal_with_rng(ruleset, random.Random(seed))


def _deal_with_rng(ruleset: Ruleset, rng: random.Random) -> tuple[tuple[int, ...], ...]:
    deck = list(range(ruleset.deck_size))
    rng.shuffle(deck)
    hands: list[list[int]] = [[] for _ in range(NUM_PLAYERS)]
    for index, card in enumerate(deck):
        hands[index % NUM_PLAYERS].append(card)
    return validate_deal(ruleset, hands)


class FishEnv:
    """Deterministic six-player Literature environment.

    The environment owns the hidden ``GameState``.  Decision code should be handed
    the result of :meth:`observe`, never the environment or :meth:`full_state`.
    """

    def __init__(
        self,
        ruleset: Ruleset | None = None,
        seed: int | None = None,
        debug: bool = True,
    ) -> None:
        self.ruleset = ruleset or Ruleset.joker_54()
        self.debug = debug
        self._rng = random.Random(seed)
        self._observation_cache: dict[int, PlayerObservation] = {}
        self._state: GameState
        self.reset(seed=seed)

    @property
    def current_player(self) -> int:
        return self._state.turn

    @property
    def done(self) -> bool:
        return self._state.done

    @property
    def phase(self) -> GamePhase:
        return self._state.phase

    @property
    def scores(self) -> tuple[int, int]:
        return tuple(self._state.scores)  # type: ignore[return-value]

    @property
    def history(self) -> tuple[PublicEvent, ...]:
        return tuple(self._state.history)

    def reset(
        self,
        seed: int | None = None,
        deal: Sequence[Iterable[CardId]] | None = None,
        turn: int | None = None,
    ) -> PlayerObservation:
        if seed is not None:
            self._rng.seed(seed)
        normalized = (
            validate_deal(self.ruleset, deal)
            if deal is not None
            else _deal_with_rng(self.ruleset, self._rng)
        )
        hands = [sum(1 << card for card in hand) for hand in normalized]
        owners = [NO_OWNER] * self.ruleset.deck_size
        for player, hand in enumerate(normalized):
            for card in hand:
                owners[card] = player
        chosen_turn = self._rng.randrange(NUM_PLAYERS) if turn is None else turn
        if not 0 <= chosen_turn < NUM_PLAYERS:
            raise ValueError("turn must be a player from 0 through 5")
        self._state = GameState(
            self.ruleset,
            hands,
            owners,
            chosen_turn,
            [UNRESOLVED] * self.ruleset.num_half_suits,
            [0, 0],
            [],
            seed=seed,
        )
        self._observation_cache.clear()
        if self.debug:
            self._state.validate()
        return self.observe(chosen_turn)

    def full_state(self) -> GameState:
        """Return a detached privileged copy for debugging/centralized critics."""
        return self._state.clone()

    def clone(self) -> "FishEnv":
        cloned = object.__new__(FishEnv)
        cloned.ruleset = self.ruleset
        cloned.debug = self.debug
        cloned._rng = random.Random()
        cloned._rng.setstate(self._rng.getstate())
        cloned._state = self._state.clone()
        cloned._observation_cache = self._observation_cache.copy()
        return cloned

    def observe(self, player: int) -> PlayerObservation:
        cached = self._observation_cache.get(player)
        if cached is not None:
            return cached
        team = team_of(player)
        hand = self._state.hands[player]
        own_cards = tuple(card for card in range(self.ruleset.deck_size) if hand & (1 << card))
        observation = PlayerObservation(
            ruleset=self.ruleset,
            player=player,
            team=team,
            own_hand=own_cards,
            turn=self._state.turn,
            phase=self._state.phase,
            pending_selector=self._state.pending_selector,
            forced_claimer=self._state.forced_claimer,
            card_counts=self._state.card_counts,
            scores=tuple(self._state.scores),  # type: ignore[arg-type]
            resolved_owners=tuple(self._state.resolved_owners),
            history=tuple(self._state.history),
            legal_asks=self.legal_asks(player),
            legal_claim_half_suits=self.legal_claim_half_suits(player),
            legal_admin_actions=self.legal_admin_actions(player),
            done=self._state.done,
            ply=self._state.ply,
        )
        self._observation_cache[player] = observation
        return observation

    def _player_may_claim(self, player: int) -> bool:
        if self._state.done:
            return False
        if self._state.phase == GamePhase.FORCED_CLAIMS:
            return player == self._state.forced_claimer
        if self._state.phase != GamePhase.PLAY:
            return False
        house = self.ruleset.house_rules
        if not house.cardless_players_may_claim and self._state.card_counts[player] == 0:
            return False
        return house.claim_timing == ClaimTiming.ANY_TURN or player == self._state.turn

    def mandatory_claim_half_suits(self, player: int | None = None) -> tuple[int, ...]:
        player = self._state.turn if player is None else player
        if not self.ruleset.house_rules.mandatory_immediate_claims or not self._player_may_claim(player):
            return ()
        hand = self._state.hands[player]
        return tuple(
            hs.id for hs in self.ruleset.half_suits
            if self._state.resolved_owners[hs.id] == UNRESOLVED and hand & hs.mask == hs.mask
        )

    def legal_asks(self, player: int | None = None) -> tuple[AskAction, ...]:
        player = self._state.turn if player is None else player
        if (
            self._state.done
            or self._state.phase != GamePhase.PLAY
            or player != self._state.turn
            or self._state.card_counts[player] == 0
        ):
            return ()
        if self.mandatory_claim_half_suits(player):
            return ()
        hand = self._state.hands[player]
        bluff = self.ruleset.house_rules.allow_owned_card_bluff
        actions: list[AskAction] = []
        live_opponents = tuple(target for target in opponents(player) if self._state.card_counts[target] > 0)
        for hs in self.ruleset.half_suits:
            if self._state.resolved_owners[hs.id] != UNRESOLVED or not (hand & hs.mask):
                continue
            for card in hs.cards:
                if not bluff and hand & (1 << card):
                    continue
                if not hand & (hs.mask & ~(1 << card)):
                    # Even an owned-card bluff requires a different card from the
                    # requested half-suit as authorization.
                    continue
                actions.extend(AskAction(player, target, card) for target in live_opponents)
        return tuple(actions)

    def legal_claim_half_suits(self, player: int | None = None) -> tuple[int, ...]:
        player = self._state.turn if player is None else player
        if not self._player_may_claim(player):
            return ()
        mandatory = self.mandatory_claim_half_suits(player)
        if mandatory:
            return mandatory
        return tuple(
            hs.id for hs in self.ruleset.half_suits
            if self._state.resolved_owners[hs.id] == UNRESOLVED
        )

    def legal_admin_actions(self, player: int | None = None) -> tuple[AdministrativeAction, ...]:
        player = self._state.turn if player is None else player
        if player != self._state.pending_selector:
            return ()
        counts = self._state.card_counts
        if self._state.phase == GamePhase.SELECT_SUCCESSOR:
            return tuple(
                SelectSuccessorAction(player, successor)
                for successor in teammates(player)
                if successor != player and counts[successor] > 0
            )
        if self._state.phase == GamePhase.SELECT_FORCED_CLAIMER:
            return tuple(
                SelectForcedClaimerAction(player, forced)
                for forced in opponents(player)
                if counts[forced] > 0
            )
        return ()

    def legal_actions(
        self,
        player: int | None = None,
        include_claims: bool = True,
    ) -> tuple[Action, ...]:
        """Enumerate legal actions without consulting hidden opponent ownership.

        Claim enumeration is necessarily large (up to 9 * 3**6 allocations), so
        callers that only need asks should set ``include_claims=False`` and callers
        sampling play should prefer :meth:`sample_legal_action`.
        """
        player = self._state.turn if player is None else player
        administrative = self.legal_admin_actions(player)
        if administrative:
            return administrative
        asks: tuple[Action, ...] = self.legal_asks(player)
        if not include_claims:
            return asks
        claims: list[Action] = []
        owners = teammates(player)
        house = self.ruleset.house_rules
        mandatory = set(self.mandatory_claim_half_suits(player))
        choose_next = (
            house.claimant_chooses_next_teammate
            and self._state.phase != GamePhase.FORCED_CLAIMS
        )
        for half_suit in self.legal_claim_half_suits(player):
            allocations: Iterable[tuple[int, ...]]
            if half_suit in mandatory:
                allocations = ((player,) * 6,)
            else:
                allocations = itertools.product(owners, repeat=6)
            for allocation in allocations:
                if choose_next:
                    next_players: tuple[int | None, ...] = tuple(
                        teammate for teammate in owners
                        if self._state.card_counts[teammate] > allocation.count(teammate)
                    ) or (None,)
                else:
                    next_players = (None,)
                for next_player in next_players:
                    claims.append(ClaimAction(player, half_suit, allocation, next_player))  # type: ignore[arg-type]
        return asks + tuple(claims)

    def sample_legal_action(
        self,
        player: int | None = None,
        rng: random.Random | None = None,
        claim_probability: float = 0.08,
    ) -> Action:
        """Sample uniformly within an action type without materializing claims."""
        player = self._state.turn if player is None else player
        rng = rng or self._rng
        administrative = self.legal_admin_actions(player)
        if administrative:
            return rng.choice(administrative)
        asks = self.legal_asks(player)
        half_suits = self.legal_claim_half_suits(player)
        mandatory = bool(self.mandatory_claim_half_suits(player))
        choose_claim = bool(half_suits) and (mandatory or not asks or rng.random() < claim_probability)
        if not choose_claim:
            if not asks:
                raise IllegalAction(f"player {player} has no legal action")
            return rng.choice(asks)
        owners = teammates(player)
        if mandatory:
            allocation = (player,) * 6
        else:
            allocation = tuple(rng.choice(owners) for _ in range(6))
        next_player: int | None = None
        choose_next = (
            self.ruleset.house_rules.claimant_chooses_next_teammate
            and self._state.phase != GamePhase.FORCED_CLAIMS
        )
        if choose_next:
            candidates = tuple(
                p for p in owners if self._state.card_counts[p] > allocation.count(p)
            )
            if candidates:
                next_player = rng.choice(candidates)
        return ClaimAction(player, rng.choice(half_suits), allocation, next_player)  # type: ignore[arg-type]

    def step(self, action: Action) -> Transition:
        if self._state.done:
            raise IllegalAction("the game is already complete")
        if isinstance(action, AskAction):
            event, awarded = self._apply_ask(action), None
        elif isinstance(action, ClaimAction):
            event, awarded = self._apply_claim(action)
        elif isinstance(action, SelectSuccessorAction):
            event, awarded = self._apply_select_successor(action), None
        elif isinstance(action, SelectForcedClaimerAction):
            event, awarded = self._apply_select_forced_claimer(action), None
        else:
            raise TypeError(f"unsupported action type: {type(action).__name__}")
        self._state.history.append(event)
        self._state.ply += 1
        self._observation_cache.clear()
        if self.debug:
            self._state.validate()
        rewards = [0.0] * NUM_PLAYERS
        if awarded is not None:
            for player in range(NUM_PLAYERS):
                rewards[player] = 1.0 if team_of(player) == awarded else -1.0
        next_observation = self.observe(self._state.turn)
        return Transition(event, next_observation, tuple(rewards), self._state.done)  # type: ignore[arg-type]

    def _validate_ask(self, action: AskAction) -> None:
        if self._state.phase != GamePhase.PLAY:
            raise IllegalAction("asks are available only during ordinary play")
        if action.asker != self._state.turn:
            raise IllegalAction("only the player whose turn it is may ask")
        if action.target not in opponents(action.asker):
            raise IllegalAction("an ask must target an opposing-team player")
        if not 0 <= action.card < self.ruleset.deck_size:
            raise IllegalAction("requested card is not in this deck")
        if self._state.card_counts[action.target] == 0:
            raise IllegalAction("an ask may not target a cardless player")
        hs_id = self.ruleset.cards[action.card].half_suit
        if self._state.resolved_owners[hs_id] != UNRESOLVED:
            raise IllegalAction("a resolved half-suit may not be requested")
        hand = self._state.hands[action.asker]
        authorization_mask = self.ruleset.half_suits[hs_id].mask & ~(1 << action.card)
        if not hand & authorization_mask:
            raise IllegalAction("asker must hold another card from the requested half-suit")
        if hand & (1 << action.card) and not self.ruleset.house_rules.allow_owned_card_bluff:
            raise IllegalAction("asker already possesses the requested card")
        if self.mandatory_claim_half_suits(action.asker):
            raise IllegalAction("a personally complete mandatory half-suit must be claimed first")

    def _apply_ask(self, action: AskAction) -> AskEvent:
        self._validate_ask(action)
        card_bit = 1 << action.card
        success = bool(self._state.hands[action.target] & card_bit)
        if success:
            self._state.hands[action.target] ^= card_bit
            self._state.hands[action.asker] |= card_bit
            self._state.owners[action.card] = action.asker
            self._state.turn = action.asker
            if all(self._state.card_counts[player] == 0 for player in opponents(action.asker)):
                self._state.phase = GamePhase.FORCED_CLAIMS
                self._state.forced_claimer = action.asker
                self._state.pending_selector = None
        else:
            self._state.turn = action.target
        return AskEvent(
            action.asker,
            action.target,
            action.card,
            success,
            self._state.card_counts,
            self._state.turn,
        )

    def _validate_claim(self, action: ClaimAction) -> None:
        if not self._player_may_claim(action.claimant):
            raise IllegalAction("claimant may not claim at this time")
        if not 0 <= action.half_suit < self.ruleset.num_half_suits:
            raise IllegalAction("invalid half-suit")
        if self._state.resolved_owners[action.half_suit] != UNRESOLVED:
            raise IllegalAction("half-suit is already resolved")
        if len(action.allocation) != 6 or any(owner not in teammates(action.claimant) for owner in action.allocation):
            raise IllegalAction("all six claim positions must be assigned to claiming-team players")
        mandatory = self.mandatory_claim_half_suits(action.claimant)
        if mandatory and action.half_suit not in mandatory:
            raise IllegalAction("a personally complete mandatory half-suit must be claimed first")
        if mandatory and action.allocation != (action.claimant,) * 6:
            raise IllegalAction("a mandatory personally complete claim must use its visible true allocation")
        forced = self._state.phase == GamePhase.FORCED_CLAIMS
        choose_next = self.ruleset.house_rules.claimant_chooses_next_teammate and not forced
        if choose_next:
            eligible = tuple(
                player for player in teammates(action.claimant)
                if self._state.card_counts[player] > action.allocation.count(player)
            )
            if eligible and action.next_player not in eligible:
                raise IllegalAction("claim must choose a teammate who remains active if correct")
            if not eligible and action.next_player is not None:
                raise IllegalAction("no teammate remains active, so the claim cannot choose one")
        elif action.next_player is not None:
            raise IllegalAction("this ruleset does not allow choosing the next player")

    @staticmethod
    def _award_for_bad_claim(claim_team: int, rule: BadClaimAward) -> int | None:
        if rule == BadClaimAward.NULL:
            return None
        if rule == BadClaimAward.CLAIMING_TEAM:
            return claim_team
        return 1 - claim_team

    def _apply_claim(self, action: ClaimAction) -> tuple[ClaimEvent, int | None]:
        self._validate_claim(action)
        was_forced = self._state.phase == GamePhase.FORCED_CLAIMS
        half_suit = self.ruleset.half_suits[action.half_suit]
        actual = tuple(self._state.owners[card] for card in half_suit.cards)
        claim_team = team_of(action.claimant)
        if any(team_of(owner) != claim_team for owner in actual):
            outcome = ClaimOutcome.OPPONENT_HELD
            awarded = self._award_for_bad_claim(
                claim_team, self.ruleset.house_rules.opponent_held_claim_award
            )
        elif action.allocation == actual:
            outcome = ClaimOutcome.CORRECT
            awarded = claim_team
        else:
            outcome = ClaimOutcome.MISDISTRIBUTED
            awarded = self._award_for_bad_claim(
                claim_team, self.ruleset.house_rules.misdistributed_claim_award
            )

        for card in half_suit.cards:
            owner = self._state.owners[card]
            self._state.hands[owner] &= ~(1 << card)
            self._state.owners[card] = NO_OWNER
        resolution = NULL_OWNER if awarded is None else awarded
        self._state.resolved_owners[action.half_suit] = resolution
        if awarded is not None:
            self._state.scores[awarded] += 1

        if (
            not was_forced
            and outcome == ClaimOutcome.CORRECT
            and self.ruleset.house_rules.claimant_chooses_next_teammate
        ):
            if action.next_player is not None:
                self._state.turn = action.next_player
        self._set_post_claim_phase(was_forced)
        revealed = actual if self.ruleset.house_rules.reveal_claim_distribution else None
        event = ClaimEvent(
            action.claimant,
            action.half_suit,
            action.allocation,
            outcome,
            awarded,
            revealed,  # type: ignore[arg-type]
            self._state.card_counts,
            self._state.turn,
        )
        return event, awarded

    def _set_post_claim_phase(self, was_forced: bool) -> None:
        """Enter an explicit public phase; never silently choose an active seat."""
        state = self._state
        if state.done:
            state.phase = GamePhase.TERMINAL
            state.pending_selector = None
            state.forced_claimer = None
            return
        if was_forced:
            # Forced authority is a role and survives the claimer losing all cards.
            state.phase = GamePhase.FORCED_CLAIMS
            state.pending_selector = None
            assert state.forced_claimer is not None
            state.turn = state.forced_claimer
            return

        counts = state.card_counts
        if counts[state.turn] > 0:
            if all(counts[player] == 0 for player in opponents(state.turn)):
                state.phase = GamePhase.FORCED_CLAIMS
                state.forced_claimer = state.turn
            else:
                state.phase = GamePhase.PLAY
                state.forced_claimer = None
            state.pending_selector = None
            return

        active_teammates = tuple(
            player for player in teammates(state.turn)
            if player != state.turn and counts[player] > 0
        )
        state.forced_claimer = None
        state.pending_selector = state.turn
        if active_teammates:
            state.phase = GamePhase.SELECT_SUCCESSOR
        else:
            # The entire team controlling the turn is empty.  Its emptied player
            # publicly chooses which opponent must make all remaining claims.
            state.phase = GamePhase.SELECT_FORCED_CLAIMER

    def _apply_select_successor(self, action: SelectSuccessorAction) -> SuccessorSelectedEvent:
        state = self._state
        if state.phase != GamePhase.SELECT_SUCCESSOR or action.selector != state.pending_selector:
            raise IllegalAction("no successor choice is pending for this selector")
        if action.successor == action.selector or action.successor not in teammates(action.selector):
            raise IllegalAction("successor must be another member of the selector's team")
        if state.card_counts[action.successor] == 0:
            raise IllegalAction("successor must hold at least one card")
        state.turn = action.successor
        state.pending_selector = None
        if all(state.card_counts[player] == 0 for player in opponents(action.successor)):
            state.phase = GamePhase.FORCED_CLAIMS
            state.forced_claimer = action.successor
        else:
            state.phase = GamePhase.PLAY
            state.forced_claimer = None
        return SuccessorSelectedEvent(
            action.selector, action.successor, state.card_counts, state.turn
        )

    def _apply_select_forced_claimer(
        self, action: SelectForcedClaimerAction
    ) -> ForcedClaimsStartedEvent:
        state = self._state
        if state.phase != GamePhase.SELECT_FORCED_CLAIMER or action.selector != state.pending_selector:
            raise IllegalAction("no forced-claimer choice is pending for this selector")
        if action.forced_claimer not in opponents(action.selector):
            raise IllegalAction("forced claimer must be an opposing-team player")
        if state.card_counts[action.forced_claimer] == 0:
            raise IllegalAction("forced claimer must hold a card when selected")
        state.turn = action.forced_claimer
        state.forced_claimer = action.forced_claimer
        state.pending_selector = None
        state.phase = GamePhase.FORCED_CLAIMS
        return ForcedClaimsStartedEvent(
            action.selector,
            action.forced_claimer,
            team_of(action.selector),
            state.card_counts,
            state.turn,
        )


__all__ = [
    "Action", "AdministrativeAction", "AskAction", "AskEvent", "BadClaimAward", "Card", "CardId",
    "ClaimAction", "ClaimEvent", "ClaimOutcome", "ClaimTiming", "FishEnv",
    "ForcedClaimsStartedEvent", "GamePhase", "GameState", "HalfSuit", "HouseRules", "IllegalAction", "NO_OWNER",
    "NULL_OWNER", "NUM_PLAYERS", "PlayerObservation", "PublicEvent", "Ruleset",
    "SelectForcedClaimerAction", "SelectSuccessorAction", "SuccessorSelectedEvent",
    "TEAM_A", "TEAM_B", "Transition", "UNRESOLVED", "deal_for_seed", "opponents",
    "team_of", "teammates", "validate_deal",
]
