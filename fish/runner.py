"""Observation-safe match runner and policy construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import random
from time import perf_counter
from typing import Any, Sequence

from .agents import (
    BasicHeuristicAgent,
    MemoryAgent,
    ProbabilisticAgent,
    RandomAgent,
    SearchAgent,
)
from .core import (
    AskEvent,
    ClaimAction,
    ClaimEvent,
    FishEnv,
    HouseRules,
    PlayerObservation,
    Ruleset,
    teammates,
)


POLICY_NAMES = ("random", "heuristic", "memory", "probabilistic", "search")


@dataclass(frozen=True, slots=True)
class MatchResult:
    seed: int
    scores: tuple[int, int]
    winner: int | None
    plies: int
    elapsed_seconds: float
    terminated: bool
    truncated: bool

    @property
    def decisions_per_second(self) -> float:
        return self.plies / self.elapsed_seconds if self.elapsed_seconds > 0 else float("inf")


def make_agent(
    name: str,
    ruleset: Ruleset,
    *,
    seed: int,
    particle_count: int = 96,
    determinizations: int = 48,
) -> Any:
    """Create a fresh policy for one seat, preventing memory across deals."""
    normalized = name.lower().replace("-", "_")
    cards = range(ruleset.deck_size)
    half_suit_of = lambda card: ruleset.cards[int(card)].half_suit
    if normalized == "random":
        return RandomAgent(seed)
    if normalized in ("heuristic", "basic", "basic_heuristic"):
        return BasicHeuristicAgent(half_suit_of=half_suit_of, seed=seed)
    if normalized == "memory":
        return MemoryAgent(cards, half_suit_of=half_suit_of, seed=seed)
    if normalized in ("probabilistic", "belief"):
        return ProbabilisticAgent(
            cards,
            particle_count=particle_count,
            half_suit_of=half_suit_of,
            seed=seed,
        )
    if normalized in ("search", "sampled_search", "ismcts_baseline"):
        return SearchAgent(
            cards,
            particle_count=particle_count,
            determinizations=determinizations,
            depth=2,
            half_suit_of=half_suit_of,
            seed=seed,
        )
    raise ValueError(f"unknown policy {name!r}; choose from {', '.join(POLICY_NAMES)}")


def _public_exact_owners(observation: PlayerObservation) -> dict[int, int]:
    """Reconstruct exact current ownership from public transfers and own cards."""
    known: dict[int, int] = {}
    resolved: set[int] = set()
    for event in observation.history:
        if isinstance(event, AskEvent) and event.success:
            known[event.card] = event.asker
        elif isinstance(event, ClaimEvent):
            cards = observation.ruleset.half_suits[event.half_suit].cards
            resolved.update(cards)
            for card in cards:
                known.pop(card, None)
    for card in observation.own_hand:
        known[card] = observation.player
    for card in resolved:
        known.pop(card, None)
    return known


def _next_player_for_claim(observation: PlayerObservation) -> int | None:
    if (
        not observation.ruleset.house_rules.claimant_chooses_next_teammate
        or getattr(observation.phase, "value", observation.phase) == "forced_claims"
    ):
        return None
    active = [
        player
        for player in teammates(observation.player)
        if observation.card_counts[player] > 0
    ]
    if not active:
        return None
    # Public, deterministic choice: give control to the teammate with the most
    # remaining options, keeping the current player on ties.
    return max(active, key=lambda player: (observation.card_counts[player], player == observation.player))


def candidate_actions(
    observation: PlayerObservation,
    policy: Any,
    rng: random.Random,
    *,
    random_claim_probability: float = 0.08,
) -> tuple[Any, ...]:
    """Build a compact action set from one legal observation only.

    Enumerating 3**6 distributions for every unresolved set would distort a
    random policy toward claims and waste most policy time. Instead we add exact
    claims supported by public knowledge, plus one low-rate speculative claim for
    RandomAgent. When no ask exists, one claim is mandatory to make endgames
    progress.
    """
    if observation.legal_admin_actions:
        return tuple(observation.legal_admin_actions)
    actions: list[Any] = list(observation.legal_asks)
    known = _public_exact_owners(observation)
    team = set(teammates(observation.player))
    next_player = _next_player_for_claim(observation)
    for half_suit_id in observation.legal_claim_half_suits:
        cards = observation.ruleset.half_suits[half_suit_id].cards
        if all(card in known and known[card] in team for card in cards):
            allocation = tuple(known[card] for card in cards)
            actions.append(
                ClaimAction(observation.player, half_suit_id, allocation, next_player)
            )

    unresolved_claims = tuple(observation.legal_claim_half_suits)
    force_speculative_claim = (
        isinstance(policy, RandomAgent)
        and unresolved_claims
        and rng.random() < random_claim_probability
    )
    should_speculate = not actions or force_speculative_claim
    if should_speculate and unresolved_claims:
        half_suit_id = rng.choice(unresolved_claims)
        allocation = tuple(rng.choice(tuple(team)) for _ in range(6))
        candidate = ClaimAction(
            observation.player, half_suit_id, allocation, next_player
        )
        if candidate not in actions:
            actions.append(candidate)
        # RandomAgent uses a hierarchical distribution over action type. If a
        # claim was selected, do not dilute its probability by the often
        # hundreds of flat ASK tuples.
        if force_speculative_claim:
            return (candidate,)
    if not actions:
        raise RuntimeError(f"player {observation.player} has no candidate action")
    return tuple(actions)


def play_game(
    seed: int,
    policy_names: Sequence[str],
    *,
    ruleset: Ruleset | None = None,
    debug: bool = False,
    max_plies: int = 10_000,
    particle_count: int = 96,
    determinizations: int = 48,
) -> MatchResult:
    """Play one reproducible game with fresh, observation-only policies."""
    if len(policy_names) != 6:
        raise ValueError("exactly six seat policies are required")
    rules = ruleset or Ruleset.joker_54()
    agents = tuple(
        make_agent(
            name,
            rules,
            seed=(seed * 1_000_003 + seat * 97) & ((1 << 63) - 1),
            particle_count=particle_count,
            determinizations=determinizations,
        )
        for seat, name in enumerate(policy_names)
    )
    action_rngs = tuple(random.Random(seed * 65_537 + seat) for seat in range(6))
    env = FishEnv(rules, seed=seed, debug=debug)
    started = perf_counter()
    while not env.done and len(env.history) < max_plies:
        player = env.current_player
        observation = env.observe(player)
        if hasattr(agents[player], "select_action"):
            action = agents[player].select_action(observation)
        else:
            actions = candidate_actions(observation, agents[player], action_rngs[player])
            action = agents[player].choose_action(observation, actions)
        # The environment is the only component allowed to consult true
        # ownership while resolving the selected action.
        env.step(action)
    elapsed = perf_counter() - started
    scores = env.scores
    terminated = env.done
    winner = None if scores[0] == scores[1] else int(scores[1] > scores[0])
    return MatchResult(
        seed=seed,
        scores=scores,
        winner=winner,
        plies=len(env.history),
        elapsed_seconds=elapsed,
        terminated=terminated,
        truncated=not terminated,
    )


def evaluation_adapter(
    *,
    ruleset: Ruleset | None = None,
    debug: bool = False,
    max_plies: int = 10_000,
    particle_count: int = 96,
    determinizations: int = 48,
):
    """Return the adapter expected by :class:`DuplicateEvaluator`."""
    rules = ruleset or Ruleset.joker_54()

    def run(seed: int, policies: Sequence[str]) -> tuple[float, float]:
        result = play_game(
            seed,
            policies,
            ruleset=rules,
            debug=debug,
            max_plies=max_plies,
            particle_count=particle_count,
            determinizations=determinizations,
        )
        if result.truncated:
            raise RuntimeError(f"game {seed} exceeded {max_plies} plies")
        return float(result.scores[0]), float(result.scores[1])

    return run


__all__ = [
    "MatchResult",
    "POLICY_NAMES",
    "candidate_actions",
    "evaluation_adapter",
    "make_agent",
    "play_game",
]
