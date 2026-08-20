"""Constraint and particle based ownership beliefs for imperfect-information Fish.

This module deliberately has no dependency on ``GameState`` or ``FishEnv``.  A
belief is rebuilt from a player's legal observation and the public history.  The
card catalogue is public ruleset information and is therefore injected by the
caller.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import random
from typing import Any, Callable, Hashable, Iterable, Mapping, Sequence


CardLike = Hashable
Owner = int | None


def public_card_catalog(
    cards_or_ruleset: Any,
    half_suit_of: Callable[[CardLike], Hashable] | None = None,
) -> tuple[tuple[CardLike, ...], Callable[[CardLike], Hashable] | None]:
    """Normalize a Ruleset, Card metadata sequence, or raw public card IDs."""

    if hasattr(cards_or_ruleset, "cards") and hasattr(cards_or_ruleset, "half_suits"):
        ruleset = cards_or_ruleset
        return (
            tuple(card.id for card in ruleset.cards),
            half_suit_of or (lambda card: ruleset.cards[int(card)].half_suit),
        )
    items = tuple(cards_or_ruleset)
    if items and all(hasattr(card, "id") and hasattr(card, "half_suit") for card in items):
        half_by_id = {card.id: card.half_suit for card in items}
        return tuple(half_by_id), half_suit_of or half_by_id.__getitem__
    return items, half_suit_of


def observation_player(observation: Any) -> int:
    """Return the observing player across the supported observation spellings."""

    for name in ("player_id", "player", "observer", "observer_id"):
        if hasattr(observation, name):
            return int(getattr(observation, name))
    raise TypeError("observation does not expose an observing player")


def observation_hand(observation: Any) -> tuple[CardLike, ...]:
    for name in ("hand", "own_hand", "cards"):
        if hasattr(observation, name):
            return tuple(getattr(observation, name))
    raise TypeError("observation does not expose the player's hand")


def observation_counts(observation: Any, num_players: int) -> tuple[int, ...]:
    for name in ("card_counts", "hand_sizes", "player_card_counts"):
        if hasattr(observation, name):
            value = getattr(observation, name)
            if isinstance(value, Mapping):
                return tuple(int(value.get(player, 0)) for player in range(num_players))
            return tuple(int(count) for count in value)
    raise TypeError("observation does not expose public card counts")


def observation_history(observation: Any) -> tuple[Any, ...]:
    for name in ("history", "public_history", "events", "action_history"):
        if hasattr(observation, name):
            return tuple(getattr(observation, name))
    return ()


def _event_action(event: Any) -> Any:
    return getattr(event, "action", event)


def _action_card(action: Any) -> Any | None:
    for name in ("card", "requested_card"):
        if hasattr(action, name):
            return getattr(action, name)
    return None


def _action_target(action: Any) -> int | None:
    for name in ("target", "target_player", "opponent"):
        if hasattr(action, name):
            return int(getattr(action, name))
    return None


def _event_actor(event: Any, action: Any) -> int | None:
    for obj in (event, action):
        for name in ("actor", "asker", "player", "player_id"):
            if hasattr(obj, name):
                return int(getattr(obj, name))
    return None


def _event_success(event: Any) -> bool | None:
    for name in ("success", "succeeded", "was_successful", "card_transferred"):
        if hasattr(event, name):
            return bool(getattr(event, name))
    result = getattr(event, "result", None)
    if isinstance(result, bool):
        return result
    if result is not None:
        text = str(result).lower()
        if any(word in text for word in ("success", "transferred", "yes")):
            return True
        if any(word in text for word in ("failure", "failed", "no")):
            return False
    return None


def _event_resolved_cards(event: Any) -> tuple[Any, ...]:
    for name in ("resolved_cards", "claimed_cards", "cards_removed"):
        if hasattr(event, name):
            return tuple(getattr(event, name))
    return ()


@dataclass(frozen=True, slots=True)
class OwnershipParticle:
    """A single feasible current ownership assignment.

    Resolved cards map to ``None`` and active cards map to exactly one player.
    """

    owners: Mapping[CardLike, Owner]

    def owner(self, card: CardLike) -> Owner:
        return self.owners[card]

    def hand(self, player: int) -> frozenset[CardLike]:
        return frozenset(card for card, owner in self.owners.items() if owner == player)


class InconsistentObservation(ValueError):
    """Raised when no ownership assignment can satisfy the public facts."""


class ParticleBelief:
    """Maintain correlated, feasible ownership samples.

    The sampler enforces exact public hand sizes, the observer's entire hand,
    successful transfers, and current exclusions implied by failed asks.  Public
    events can optionally expose ``resolved_cards``; those cards are assigned no
    owner.  The implementation uses randomized backtracking rather than treating
    card marginals as independent, so every emitted particle is a coherent world.
    """

    def __init__(
        self,
        cards: Iterable[CardLike],
        *,
        num_players: int = 6,
        particle_count: int = 256,
        seed: int = 0,
        half_suit_of: Callable[[CardLike], Hashable] | None = None,
    ) -> None:
        self.cards, normalized_resolver = public_card_catalog(cards, half_suit_of)
        if len(set(self.cards)) != len(self.cards):
            raise ValueError("card catalogue must contain unique cards")
        if num_players < 2:
            raise ValueError("num_players must be at least two")
        if particle_count < 1:
            raise ValueError("particle_count must be positive")
        self.num_players = num_players
        self.particle_count = particle_count
        self._rng = random.Random(seed)
        self.half_suit_of = normalized_resolver or (
            lambda card: getattr(card, "half_suit", None)
        )
        self.particles: tuple[OwnershipParticle, ...] = ()
        self.domains: dict[CardLike, frozenset[Owner]] = {}
        self.participation: dict[Hashable, frozenset[int]] = {}
        self._history_length = -1
        self._observation_signature: tuple[Any, ...] | None = None

    def update(self, observation: Any) -> "ParticleBelief":
        """Rebuild particles solely from a legal player observation."""

        player = observation_player(observation)
        hand = frozenset(observation_hand(observation))
        counts = observation_counts(observation, self.num_players)
        history = observation_history(observation)
        signature = (
            player,
            hand,
            counts,
            tuple(getattr(observation, "resolved_owners", ())),
            history,
        )
        if signature == self._observation_signature and self.particles:
            return self
        if len(counts) != self.num_players:
            raise InconsistentObservation("public card count vector has wrong length")
        if counts[player] != len(hand):
            raise InconsistentObservation("observer hand disagrees with public card count")

        all_players = frozenset(range(self.num_players))
        domains: dict[CardLike, set[Owner]] = {card: set(all_players) for card in self.cards}
        for card in hand:
            if card not in domains:
                raise InconsistentObservation(f"observed unknown card: {card!r}")
            domains[card] = {player}
        for card in set(self.cards) - hand:
            domains[card].discard(player)

        participation: dict[Hashable, set[int]] = defaultdict(set)
        for event in history:
            action = _event_action(event)
            card = _action_card(action)
            target = _action_target(action)
            actor = _event_actor(event, action)
            success = _event_success(event)
            if card in domains and target is not None and actor is not None:
                suit = self.half_suit_of(card)
                participation[suit].add(actor)
                if success is True:
                    domains[card] = {actor}
                elif success is False:
                    domains[card].discard(target)
            for resolved in _event_resolved_cards(event):
                if resolved in domains:
                    domains[resolved] = {None}

        # The observer's current hand is the strongest fact and supersedes old
        # transfers in a supplied truncated or synthetic history.
        for card in hand:
            domains[card] = {player}

        active_total = sum(counts)
        explicit_resolved = sum(1 for domain in domains.values() if domain == {None})
        unresolved_needed = len(self.cards) - active_total
        if explicit_resolved > unresolved_needed:
            raise InconsistentObservation("too many publicly resolved cards")

        # Some core observations identify resolved half-suits instead of listing
        # their cards. Resolve those identities from public ruleset metadata (or
        # the injected half-suit function) rather than requiring a redundant
        # private-state field on the observation.
        if hasattr(observation, "resolved_owners"):
            resolved_owners = tuple(getattr(observation, "resolved_owners"))
            ruleset = getattr(observation, "ruleset", None)
            for half_suit, resolution in enumerate(resolved_owners):
                if int(resolution) == -1:  # core.UNRESOLVED, without importing core
                    continue
                if ruleset is not None and hasattr(ruleset, "half_suits"):
                    resolved_cards = ruleset.half_suits[half_suit].cards
                else:
                    resolved_cards = tuple(
                        card for card in self.cards if self.half_suit_of(card) == half_suit
                    )
                for card in resolved_cards:
                    if card in domains:
                        domains[card] = {None}

        # Accept a direct set of card identities when available as well.
        for name in ("resolved_cards", "cards_resolved"):
            if hasattr(observation, name):
                for card in getattr(observation, name):
                    if card in domains:
                        domains[card] = {None}

        # If only the total tells us cards have been resolved, their identities
        # must be available through history; guessing would leak/forge evidence.
        explicit_resolved = sum(1 for domain in domains.values() if domain == {None})
        if explicit_resolved != unresolved_needed:
            raise InconsistentObservation(
                "resolved card identities are missing from the public observation"
            )
        if any(not domain for domain in domains.values()):
            raise InconsistentObservation("public facts eliminate every owner for a card")

        samples: list[OwnershipParticle] = []
        attempts = max(64, self.particle_count * 12)
        for _ in range(attempts):
            assignment = self._sample_assignment(domains, counts)
            if assignment is not None:
                samples.append(OwnershipParticle(assignment))
                if len(samples) >= self.particle_count:
                    break
        if not samples:
            raise InconsistentObservation("no ownership assignment satisfies the observation")

        self.domains = {card: frozenset(domain) for card, domain in domains.items()}
        self.participation = {suit: frozenset(players) for suit, players in participation.items()}
        self.particles = tuple(samples)
        self._history_length = len(history)
        self._observation_signature = signature
        return self

    def _sample_assignment(
        self, domains: Mapping[CardLike, set[Owner]], counts: Sequence[int]
    ) -> dict[CardLike, Owner] | None:
        remaining = list(counts)
        result: dict[CardLike, Owner] = {}
        undecided: list[CardLike] = []

        for card, domain in domains.items():
            if domain == {None}:
                result[card] = None
            elif len(domain) == 1:
                owner = next(iter(domain))
                if owner is None:
                    result[card] = None
                else:
                    result[card] = owner
                    remaining[owner] -= 1
            else:
                undecided.append(card)
        if any(value < 0 for value in remaining):
            return None

        # Random tie breakers give particle diversity; MRV and capacity checks
        # keep rejection low near the end of a deal.
        tie_breakers = {card: self._rng.random() for card in undecided}
        undecided.sort(key=lambda card: (len(domains[card]), tie_breakers[card]))

        def assign(index: int) -> bool:
            if index == len(undecided):
                return all(value == 0 for value in remaining)
            card = undecided[index]
            candidates = [
                owner
                for owner in domains[card]
                if owner is not None and remaining[owner] > 0
            ]
            self._rng.shuffle(candidates)
            candidates.sort(key=lambda owner: remaining[owner], reverse=True)
            for owner in candidates:
                result[card] = owner
                remaining[owner] -= 1
                # Every player's remaining capacity must be fillable by cards
                # still compatible with that player.
                feasible = True
                tail = undecided[index + 1 :]
                for candidate_player, capacity in enumerate(remaining):
                    if capacity > sum(candidate_player in domains[item] for item in tail):
                        feasible = False
                        break
                if feasible and assign(index + 1):
                    return True
                remaining[owner] += 1
                del result[card]
            return False

        return result if assign(0) else None

    def probability(self, card: CardLike, owner: Owner) -> float:
        if not self.particles:
            raise RuntimeError("belief must be updated before it is queried")
        return sum(particle.owner(card) == owner for particle in self.particles) / len(
            self.particles
        )

    def probabilities(self, card: CardLike) -> dict[Owner, float]:
        if card not in self.cards:
            raise KeyError(card)
        return {
            owner: probability
            for owner in [*range(self.num_players), None]
            if (probability := self.probability(card, owner)) > 0.0
        }

    def most_likely_owner(self, card: CardLike) -> Owner:
        probabilities = self.probabilities(card)
        return max(probabilities, key=probabilities.__getitem__)

    def sample(self, rng: random.Random | None = None) -> OwnershipParticle:
        if not self.particles:
            raise RuntimeError("belief must be updated before sampling")
        chooser = rng or self._rng
        return chooser.choice(self.particles)

    def effective_sample_size(self) -> float:
        # Samples are unweighted.  Keeping this API makes a future weighted
        # Bayesian/learned proposal drop-in compatible.
        return float(len(self.particles))

    def validate_particles(self, observation: Any) -> None:
        """Assert all particles obey current hand and count information."""

        player = observation_player(observation)
        hand = frozenset(observation_hand(observation))
        counts = observation_counts(observation, self.num_players)
        for particle in self.particles:
            assert particle.hand(player) == hand
            actual = Counter(owner for owner in particle.owners.values() if owner is not None)
            assert tuple(actual[index] for index in range(self.num_players)) == counts


# Name used by the research plan; the implementation is particle based but also
# exposes its propagated feasible domains.
FeasibleBelief = ParticleBelief
