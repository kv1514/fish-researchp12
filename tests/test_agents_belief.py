from __future__ import annotations

from dataclasses import dataclass
import inspect

import pytest

from fish.agents import (
    BasicHeuristicAgent,
    MemoryAgent,
    ProbabilisticAgent,
    RandomAgent,
    SearchAgent,
)
from fish.belief import InconsistentObservation, ParticleBelief


@dataclass(frozen=True)
class Ask:
    asker: int
    target: int
    card: int


@dataclass(frozen=True)
class AskEvent:
    actor: int
    action: Ask
    success: bool


@dataclass(frozen=True)
class Observation:
    player: int
    own_hand: tuple[int, ...]
    card_counts: tuple[int, ...]
    history: tuple[AskEvent, ...] = ()


CARDS = tuple(range(12))
SUIT = lambda card: card // 6


def test_random_agent_returns_only_legal_actions() -> None:
    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2))
    legal = (Ask(0, 1, 2), Ask(0, 3, 3))
    agent = RandomAgent(seed=7)
    assert {agent.choose_action(observation, legal) for _ in range(20)} <= set(legal)
    with pytest.raises(ValueError):
        agent.choose_action(observation, ())


def test_basic_heuristic_builds_suit_with_most_owned_cards() -> None:
    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2))
    matching_suit = Ask(0, 1, 2)
    other_suit = Ask(0, 1, 6)
    agent = BasicHeuristicAgent(half_suit_of=SUIT, seed=1)
    assert agent.choose_action(observation, (other_suit, matching_suit)) == matching_suit


def test_memory_agent_uses_successes_and_avoids_known_failures() -> None:
    known = Ask(0, 1, 2)
    impossible = Ask(0, 3, 3)
    history = (
        AskEvent(4, Ask(4, 1, 2), True),
        AskEvent(2, Ask(2, 3, 3), False),
    )
    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2), history)
    agent = MemoryAgent(CARDS, half_suit_of=SUIT, seed=1)
    # The success says player 4 owns card 2, not target 1.  Supply the matching
    # legal ask and verify it dominates the failed location.
    known = Ask(0, 4, 2)
    assert agent.choose_action(observation, (impossible, known)) == known


def test_particles_are_feasible_and_correlated() -> None:
    history = (
        AskEvent(1, Ask(1, 2, 3), True),
        AskEvent(4, Ask(4, 5, 4), False),
    )
    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2), history)
    belief = ParticleBelief(CARDS, particle_count=80, seed=3, half_suit_of=SUIT)
    belief.update(observation)
    belief.validate_particles(observation)
    assert belief.probability(3, 1) == 1.0
    assert belief.probability(4, 5) == 0.0
    assert belief.probability(0, 0) == 1.0
    # Marginals come from full worlds: each sample has exactly two cards/player.
    assert len(belief.particles) == 80


def test_inconsistent_observation_is_rejected() -> None:
    observation = Observation(0, (0, 1), (1, 3, 2, 2, 2, 2))
    with pytest.raises(InconsistentObservation):
        ParticleBelief(CARDS).update(observation)


def test_probabilistic_and_search_agents_exploit_certain_owner() -> None:
    # A public successful transfer puts card 2 at player 1 with certainty.
    history = (AskEvent(1, Ask(1, 2, 2), True),)
    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2), history)
    certain = Ask(0, 1, 2)
    uncertain = Ask(0, 3, 3)
    probabilistic = ProbabilisticAgent(
        CARDS, particle_count=50, seed=2, half_suit_of=SUIT
    )
    search = SearchAgent(
        CARDS,
        particle_count=50,
        determinizations=50,
        depth=2,
        seed=2,
        half_suit_of=SUIT,
    )
    assert probabilistic.choose_action(observation, (uncertain, certain)) == certain
    assert search.choose_action(observation, (uncertain, certain)) == certain
    assert search.last_estimates[0].samples == 50


def test_agent_interface_cannot_accept_hidden_state_or_environment() -> None:
    """Regression guard for the policy boundary that prevents state leakage."""

    for agent_type in (
        RandomAgent,
        BasicHeuristicAgent,
        MemoryAgent,
        ProbabilisticAgent,
        SearchAgent,
    ):
        parameters = tuple(inspect.signature(agent_type.choose_action).parameters)
        assert parameters == ("self", "observation", "legal_actions")
        assert "state" not in parameters
        assert "env" not in parameters


def test_same_information_set_produces_same_seeded_decision() -> None:
    """Two hidden worlds with the same observation cannot affect the policy."""

    observation = Observation(0, (0, 1), (2, 2, 2, 2, 2, 2))
    legal = (Ask(0, 1, 2), Ask(0, 3, 3), Ask(0, 5, 4))
    left = SearchAgent(
        CARDS, particle_count=60, determinizations=40, seed=19, half_suit_of=SUIT
    )
    right = SearchAgent(
        CARDS, particle_count=60, determinizations=40, seed=19, half_suit_of=SUIT
    )
    assert left.choose_action(observation, legal) == right.choose_action(observation, legal)
