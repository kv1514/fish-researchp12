"""Baseline Fish agents with a strict observation-only policy boundary."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Any, Callable, Hashable, Iterable, Mapping, Protocol, Sequence, TypeVar

from .belief import (
    OwnershipParticle,
    ParticleBelief,
    _action_card,
    _action_target,
    observation_hand,
    observation_player,
    public_card_catalog,
)


ActionT = TypeVar("ActionT")


class Agent(Protocol[ActionT]):
    """The only supported inference-time agent interface.

    Implementations receive a sanitized player observation and actions already
    deemed legal by the simulator.  They never receive an environment, game
    state, other player's observation, or privileged ownership mapping.
    """

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        ...


def _require_actions(legal_actions: Sequence[ActionT]) -> None:
    if not legal_actions:
        raise ValueError("agent was called without a legal action")


def _is_ask(action: Any) -> bool:
    return _action_card(action) is not None and _action_target(action) is not None


def _is_claim(action: Any) -> bool:
    return not _is_ask(action) and any(
        hasattr(action, name)
        for name in ("distribution", "assignments", "ownership", "half_suit", "suit")
    )


def _half_suit(card: Any, resolver: Callable[[Any], Hashable] | None) -> Hashable:
    if resolver is not None:
        return resolver(card)
    value = getattr(card, "half_suit", None)
    if callable(value):
        value = value()
    if value is None:
        value = getattr(card, "suit_group", None)
    return value


def _observed_half_suit(
    observation: Any,
    card: Any,
    resolver: Callable[[Any], Hashable] | None,
) -> Hashable:
    if resolver is not None:
        return resolver(card)
    ruleset = getattr(observation, "ruleset", None)
    if ruleset is not None:
        return ruleset.cards[int(card)].half_suit
    return _half_suit(card, None)


def _claim_components(observation: Any, action: Any) -> tuple[tuple[Any, ...], tuple[int, ...]] | None:
    """Return canonical claim cards/allocation without importing the core."""

    allocation = getattr(action, "allocation", None)
    half_suit = getattr(action, "half_suit", None)
    ruleset = getattr(observation, "ruleset", None)
    if allocation is None or half_suit is None or ruleset is None:
        return None
    return tuple(ruleset.half_suits[half_suit].cards), tuple(allocation)


def _claim_next_player(observation: Any) -> int | None:
    """Choose a public-legal successor for the optional post-claim rule."""
    ruleset = getattr(observation, "ruleset", None)
    if ruleset is None or not ruleset.house_rules.claimant_chooses_next_teammate:
        return None
    if getattr(getattr(observation, "phase", None), "value", None) == "forced_claims":
        return None
    player = observation_player(observation)
    counts = tuple(getattr(observation, "card_counts", (0,) * 6))
    active = [candidate for candidate in range(6) if candidate & 1 == player & 1 and counts[candidate] > 0]
    if not active:
        return None
    return max(active, key=lambda candidate: (counts[candidate], candidate == player))


class RandomAgent:
    def __init__(self, seed: int | None = None, *, claim_probability: float = 0.05) -> None:
        if not 0.0 <= claim_probability <= 1.0:
            raise ValueError("claim_probability must be in [0, 1]")
        self.rng = random.Random(seed)
        self.claim_probability = claim_probability

    def candidate_actions(self, observation: Any) -> tuple[Any, ...]:
        """Build a compact public-legal action set without 3**6 enumeration."""

        admin = tuple(getattr(observation, "legal_admin_actions", ()))
        if admin:
            return admin
        asks = list(getattr(observation, "legal_asks", ()))
        claim_suits = tuple(getattr(observation, "legal_claim_half_suits", ()))
        if claim_suits and (not asks or self.rng.random() < self.claim_probability):
            from .core import ClaimAction

            player = observation_player(observation)
            teammates = tuple(candidate for candidate in range(6) if candidate & 1 == player & 1)
            half_suit = self.rng.choice(claim_suits)
            allocation = tuple(self.rng.choice(teammates) for _ in range(6))
            # ``claim_probability`` is an action-type probability. Returning a
            # singleton avoids diluting it among dozens of legal asks.
            return (ClaimAction(player, half_suit, allocation, _claim_next_player(observation)),)
        return tuple(asks)

    def select_action(self, observation: Any) -> Any:
        return self.choose_action(observation, self.candidate_actions(observation))

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        del observation
        _require_actions(legal_actions)
        return self.rng.choice(legal_actions)


class BasicHeuristicAgent:
    """Prefer safe claims, concentrated suits, and targets with fewer cards."""

    def __init__(
        self,
        *,
        half_suit_of: Callable[[Any], Hashable] | None = None,
        seed: int | None = None,
        stalemate_claim_after: int = 256,
    ) -> None:
        if stalemate_claim_after < 1:
            raise ValueError("stalemate_claim_after must be positive")
        self.half_suit_of = half_suit_of
        self.rng = random.Random(seed)
        self.stalemate_claim_after = stalemate_claim_after
        self._progress_signature: tuple[Any, ...] | None = None
        self._progress_ply = 0

    def _stalemate_claim_due(self, observation: Any) -> bool:
        signature = tuple(getattr(observation, "resolved_owners", ()))
        ply = int(getattr(observation, "ply", 0))
        if signature != self._progress_signature:
            self._progress_signature = signature
            self._progress_ply = ply
            return False
        if ply - self._progress_ply < self.stalemate_claim_after:
            return False
        self._progress_ply = ply
        return True

    def _fallback_claim(self, observation: Any, half_suit: int) -> Any:
        from .core import ClaimAction

        ruleset = observation.ruleset
        player = observation_player(observation)
        hand = frozenset(observation_hand(observation))
        cards = ruleset.half_suits[half_suit].cards
        team = tuple(candidate for candidate in range(6) if candidate & 1 == player & 1)
        allocation = tuple(
            player if card in hand else self.rng.choice(team) for card in cards
        )
        return ClaimAction(
            player, half_suit, allocation, _claim_next_player(observation)
        )

    def candidate_actions(self, observation: Any) -> tuple[Any, ...]:
        admin = tuple(getattr(observation, "legal_admin_actions", ()))
        if admin:
            return admin
        asks = list(getattr(observation, "legal_asks", ()))
        ruleset = getattr(observation, "ruleset", None)
        player = observation_player(observation)
        hand = frozenset(observation_hand(observation))
        if ruleset is None:
            return tuple(asks)
        from .core import ClaimAction

        personally_complete = False
        for half_suit in getattr(observation, "legal_claim_half_suits", ()):
            cards = ruleset.half_suits[half_suit].cards
            if set(cards) <= hand:
                personally_complete = True
                asks.append(
                    ClaimAction(player, half_suit, (player,) * 6, _claim_next_player(observation))
                )
        if (
            not personally_complete
            and getattr(observation, "legal_claim_half_suits", ())
            and self._stalemate_claim_due(observation)
        ):
            half_suit = max(
                observation.legal_claim_half_suits,
                key=lambda item: len(hand.intersection(ruleset.half_suits[item].cards)),
            )
            return (self._fallback_claim(observation, half_suit),)
        # Endgame fallback: if no ask is possible, make one public-legal claim so
        # a baseline game cannot stall. Known own cards remain correctly assigned.
        if not asks and getattr(observation, "legal_claim_half_suits", ()):
            half_suit = observation.legal_claim_half_suits[0]
            asks.append(self._fallback_claim(observation, half_suit))
        return tuple(asks)

    def select_action(self, observation: Any) -> Any:
        return self.choose_action(observation, self.candidate_actions(observation))

    def score_action(self, observation: Any, action: Any) -> float:
        if _is_claim(action):
            components = _claim_components(observation, action)
            if components is None:
                return -1_000.0
            cards, allocation = components
            player = observation_player(observation)
            hand = frozenset(observation_hand(observation))
            # A legal claim says nothing about hidden ownership.  The basic
            # policy makes only the one claim it can prove from its own hand.
            if set(cards) <= hand and all(owner == player for owner in allocation):
                return 1_000.0
            return -1_000.0
        if not _is_ask(action):
            return -1_000.0
        hand = observation_hand(observation)
        card = _action_card(action)
        target = _action_target(action)
        suit = _observed_half_suit(observation, card, self.half_suit_of)
        suit_count = sum(
            _observed_half_suit(observation, held, self.half_suit_of) == suit
            for held in hand
        )
        counts = None
        for name in ("card_counts", "hand_sizes", "player_card_counts"):
            if hasattr(observation, name):
                counts = getattr(observation, name)
                break
        target_count = 9
        if counts is not None and target is not None:
            target_count = counts[target] if not isinstance(counts, Mapping) else counts[target]
        # Building a suit is useful, and a player with fewer cards is a more
        # concentrated target under an otherwise uniform prior.
        return suit_count * 2.0 + 1.0 / max(1, int(target_count))

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        _require_actions(legal_actions)
        scored = [(self.score_action(observation, action), action) for action in legal_actions]
        best = max(score for score, _ in scored)
        choices = [action for score, action in scored if math.isclose(score, best)]
        return self.rng.choice(choices)


class MemoryAgent(BasicHeuristicAgent):
    """A hard-memory agent using public ask successes and failures."""

    def __init__(self, cards: Iterable[Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cards, normalized_resolver = public_card_catalog(cards, self.half_suit_of)
        self.half_suit_of = normalized_resolver
        self.known_owner: dict[Any, int] = {}
        self.not_owner: dict[Any, set[int]] = {}
        self._processed_history = 0

    def _remember(self, observation: Any) -> None:
        from .belief import (
            _event_action,
            _event_actor,
            _event_success,
            observation_history,
        )

        history = observation_history(observation)
        # Observations can be reset between games.  Rebuild rather than carrying
        # knowledge across deals.
        if len(history) < self._processed_history:
            self.known_owner.clear()
            self.not_owner.clear()
            self._processed_history = 0
        for event in history[self._processed_history :]:
            action = _event_action(event)
            card = _action_card(action)
            target = _action_target(action)
            actor = _event_actor(event, action)
            success = _event_success(event)
            if card not in self.cards or target is None or actor is None:
                continue
            if success is True:
                self.known_owner[card] = actor
                self.not_owner.setdefault(card, set()).discard(actor)
            elif success is False:
                self.not_owner.setdefault(card, set()).add(target)
                if self.known_owner.get(card) == target:
                    self.known_owner.pop(card)
        self._processed_history = len(history)
        for card in observation_hand(observation):
            self.known_owner[card] = observation_player(observation)

    def score_action(self, observation: Any, action: Any) -> float:
        score = super().score_action(observation, action)
        if _is_claim(action):
            components = _claim_components(observation, action)
            if components is not None:
                cards, allocation = components
                if all(card in self.known_owner for card in cards):
                    return (
                        1_000.0
                        if all(self.known_owner[card] == owner for card, owner in zip(cards, allocation))
                        else -1_000.0
                    )
        if _is_ask(action):
            card = _action_card(action)
            target = _action_target(action)
            if self.known_owner.get(card) == target:
                score += 100.0
            if target in self.not_owner.get(card, ()):
                score -= 100.0
        return score

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        self._remember(observation)
        return super().choose_action(observation, legal_actions)

    def candidate_actions(self, observation: Any) -> tuple[Any, ...]:
        self._remember(observation)
        admin = tuple(getattr(observation, "legal_admin_actions", ()))
        if admin:
            return admin
        actions = list(super().candidate_actions(observation))
        ruleset = getattr(observation, "ruleset", None)
        if ruleset is None:
            return tuple(actions)
        from .core import ClaimAction

        player = observation_player(observation)
        for half_suit in getattr(observation, "legal_claim_half_suits", ()):
            cards = ruleset.half_suits[half_suit].cards
            if all(card in self.known_owner for card in cards):
                allocation = tuple(self.known_owner[card] for card in cards)
                if all(owner & 1 == player & 1 for owner in allocation):
                    claim = ClaimAction(
                        player, half_suit, allocation, _claim_next_player(observation)
                    )
                    if claim not in actions:
                        actions.append(claim)
        return tuple(actions)


class ProbabilisticAgent(BasicHeuristicAgent):
    """Select asks from correlated feasible ownership probabilities."""

    def __init__(
        self,
        cards: Iterable[Any],
        *,
        particle_count: int = 256,
        information_weight: float = 0.08,
        seed: int | None = None,
        half_suit_of: Callable[[Any], Hashable] | None = None,
    ) -> None:
        normalized_cards, normalized_resolver = public_card_catalog(cards, half_suit_of)
        super().__init__(half_suit_of=normalized_resolver, seed=seed)
        self.information_weight = information_weight
        self.belief = ParticleBelief(
            normalized_cards,
            particle_count=particle_count,
            seed=0 if seed is None else seed,
            half_suit_of=normalized_resolver,
        )

    def candidate_actions(self, observation: Any) -> tuple[Any, ...]:
        admin = tuple(getattr(observation, "legal_admin_actions", ()))
        if admin:
            return admin
        actions = list(getattr(observation, "legal_asks", ()))
        ruleset = getattr(observation, "ruleset", None)
        claim_suits = tuple(getattr(observation, "legal_claim_half_suits", ()))
        if ruleset is None or not claim_suits:
            return tuple(actions)
        stalled = self._stalemate_claim_due(observation)
        self.belief.update(observation)
        from collections import Counter
        from .core import ClaimAction

        player = observation_player(observation)
        best_fallback: tuple[int, tuple[int, ...], int] | None = None
        for half_suit in claim_suits:
            cards = ruleset.half_suits[half_suit].cards
            allocations = Counter(
                tuple(particle.owner(card) for card in cards)
                for particle in self.belief.particles
                if all(
                    particle.owner(card) is not None
                    and int(particle.owner(card)) & 1 == player & 1
                    for card in cards
                )
            )
            if not allocations:
                continue
            allocation, support = allocations.most_common(1)[0]
            typed_allocation = tuple(int(owner) for owner in allocation)
            if best_fallback is None or support > best_fallback[2]:
                best_fallback = (half_suit, typed_allocation, support)
            if support / len(self.belief.particles) >= 0.75:
                actions.append(
                    ClaimAction(
                        player,
                        half_suit,
                        typed_allocation,
                        _claim_next_player(observation),
                    )
                )
        if stalled:
            if best_fallback is not None:
                return (
                    ClaimAction(
                        player,
                        best_fallback[0],
                        best_fallback[1],
                        _claim_next_player(observation),
                    ),
                )
            half_suit = max(
                claim_suits,
                key=lambda item: len(
                    frozenset(observation_hand(observation)).intersection(
                        ruleset.half_suits[item].cards
                    )
                ),
            )
            return (self._fallback_claim(observation, half_suit),)
        if not actions and best_fallback is not None:
            actions.append(
                ClaimAction(
                    player,
                    best_fallback[0],
                    best_fallback[1],
                    _claim_next_player(observation),
                )
            )
        return tuple(actions)

    def _probabilistic_score(self, observation: Any, action: Any) -> float:
        base = super().score_action(observation, action)
        if _is_claim(action):
            components = _claim_components(observation, action)
            if components is None:
                return -1_000.0
            cards, allocation = components
            claimant = int(getattr(action, "claimant", observation_player(observation)))
            claiming_team = claimant & 1
            exact = 0
            opponent_held = 0
            for particle in self.belief.particles:
                actual = tuple(particle.owner(card) for card in cards)
                exact += actual == allocation
                opponent_held += any(
                    owner is not None and owner & 1 != claiming_team for owner in actual
                )
            sample_count = len(self.belief.particles)
            exact_probability = exact / sample_count
            opponent_probability = opponent_held / sample_count
            # Require substantial exact-allocation confidence; a claim that is
            # merely team-owned but misdistributed is null under baseline rules.
            return 100.0 * exact_probability - 120.0 * opponent_probability - 20.0
        if not _is_ask(action):
            return base
        card = _action_card(action)
        target = _action_target(action)
        probability = self.belief.probability(card, target)
        # A binary ask reveals most near p=.5. Entropy is measured in bits.
        entropy = 0.0
        if 0.0 < probability < 1.0:
            entropy = -probability * math.log2(probability) - (
                1.0 - probability
            ) * math.log2(1.0 - probability)
        return base + 20.0 * probability + self.information_weight * entropy

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        _require_actions(legal_actions)
        self.belief.update(observation)
        scored = [(self._probabilistic_score(observation, action), action) for action in legal_actions]
        best = max(score for score, _ in scored)
        choices = [action for score, action in scored if math.isclose(score, best)]
        return self.rng.choice(choices)


@dataclass(frozen=True, slots=True)
class SearchEstimate:
    action: Any
    value: float
    samples: int


class SearchAgent(ProbabilisticAgent):
    """Observation-safe determinization search over retained-turn ask chains.

    Each root action is evaluated in sampled feasible worlds.  On a successful
    ask, a shallow rollout searches another currently legal ask, capturing the
    strategic value of retaining the turn.  Crucially, particles come only from
    ``PlayerObservation``; the real hidden state is never accepted by this API.
    """

    def __init__(
        self,
        cards: Iterable[Any],
        *,
        determinizations: int = 128,
        depth: int = 2,
        success_reward: float = 1.0,
        failure_penalty: float = 0.2,
        max_root_actions: int = 12,
        max_rollout_actions: int = 4,
        **kwargs: Any,
    ) -> None:
        super().__init__(cards, **kwargs)
        if min(determinizations, depth, max_root_actions, max_rollout_actions) < 1:
            raise ValueError("search sizes and depth must be positive")
        self.determinizations = determinizations
        self.depth = depth
        self.success_reward = success_reward
        self.failure_penalty = failure_penalty
        self.max_root_actions = max_root_actions
        self.max_rollout_actions = max_rollout_actions
        self.last_estimates: tuple[SearchEstimate, ...] = ()

    def _world_action_value(
        self,
        particle: OwnershipParticle,
        observation: Any,
        action: Any,
        ask_actions: Sequence[Any],
        depth: int,
        used: frozenset[Any] = frozenset(),
    ) -> float:
        if _is_claim(action):
            components = _claim_components(observation, action)
            if components is None:
                return -6.0
            cards, allocation = components
            owners = tuple(particle.owner(card) for card in cards)
            claimant = int(getattr(action, "claimant", observation_player(observation)))
            if owners == allocation:
                return 6.0
            if any(owner is not None and owner & 1 != claimant & 1 for owner in owners):
                return -6.0
            return -2.0
        if not _is_ask(action):
            return -1.0
        card = _action_card(action)
        target = _action_target(action)
        if particle.owner(card) != target:
            return -self.failure_penalty
        value = self.success_reward
        if depth <= 1:
            return value
        next_actions = [
            candidate
            for candidate in ask_actions
            if candidate not in used
            and candidate != action
            and particle.owner(_action_card(candidate)) == _action_target(candidate)
        ]
        if next_actions:
            next_actions = sorted(
                next_actions,
                key=lambda candidate: self._probabilistic_score(observation, candidate),
                reverse=True,
            )[: self.max_rollout_actions]
            value += 0.85 * max(
                self._world_action_value(
                    particle,
                    observation,
                    candidate,
                    ask_actions,
                    depth - 1,
                    used | {action},
                )
                for candidate in next_actions
            )
        return value

    def choose_action(self, observation: Any, legal_actions: Sequence[ActionT]) -> ActionT:
        _require_actions(legal_actions)
        self.belief.update(observation)
        all_asks = [action for action in legal_actions if _is_ask(action)]
        ask_actions = sorted(
            all_asks,
            key=lambda action: self._probabilistic_score(observation, action),
            reverse=True,
        )[: self.max_root_actions]
        non_asks = [action for action in legal_actions if not _is_ask(action)]
        search_actions = [*ask_actions, *non_asks]
        particles = [self.belief.sample(self.rng) for _ in range(self.determinizations)]
        estimates: list[SearchEstimate] = []
        for action in search_actions:
            values = [
                self._world_action_value(
                    particle, observation, action, ask_actions, self.depth
                )
                for particle in particles
            ]
            # A tiny heuristic tie-break preserves sensible suit concentration.
            value = sum(values) / len(values) + 1e-4 * super().score_action(
                observation, action
            )
            estimates.append(SearchEstimate(action, value, len(values)))
        self.last_estimates = tuple(sorted(estimates, key=lambda item: item.value, reverse=True))
        best = self.last_estimates[0].value
        choices = [item.action for item in self.last_estimates if math.isclose(item.value, best)]
        return self.rng.choice(choices)


# Research-plan spelling.
BeliefAgent = ProbabilisticAgent
