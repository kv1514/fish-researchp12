"""Small population self-play trainer for the pre-neural research phase.

This is an evolutionary baseline, not the intended final learning algorithm. It
is useful because it exercises population sampling, historical opponents,
duplicate deals, checkpoint preservation, and champion promotion before adding a
large ML dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
from statistics import fmean
from typing import Any, Sequence

from .agents import BasicHeuristicAgent, RandomAgent
from .core import FishEnv, Ruleset


@dataclass(frozen=True, slots=True)
class LinearWeights:
    suit_concentration: float = 2.0
    inverse_target_cards: float = 1.0
    low_target_cards: float = 0.05

    def mutate(self, rng: random.Random, sigma: float) -> "LinearWeights":
        return LinearWeights(
            max(-5.0, min(5.0, self.suit_concentration + rng.gauss(0.0, sigma))),
            max(-5.0, min(5.0, self.inverse_target_cards + rng.gauss(0.0, sigma))),
            max(-1.0, min(1.0, self.low_target_cards + rng.gauss(0.0, sigma / 5.0))),
        )


class LinearHeuristicAgent(BasicHeuristicAgent):
    def __init__(self, weights: LinearWeights, *, seed: int) -> None:
        super().__init__(seed=seed)
        self.weights = weights

    def score_action(self, observation: Any, action: Any) -> float:
        from .agents import _is_ask, _is_claim, _action_card, _action_target

        if not _is_ask(action):
            return super().score_action(observation, action)
        card = int(_action_card(action))
        target = int(_action_target(action))
        half_suit = observation.ruleset.cards[card].half_suit
        suit_count = sum(
            observation.ruleset.cards[held].half_suit == half_suit
            for held in observation.own_hand
        )
        target_cards = observation.card_counts[target]
        return (
            self.weights.suit_concentration * suit_count
            + self.weights.inverse_target_cards / max(1, target_cards)
            + self.weights.low_target_cards * (observation.ruleset.deck_size / 6 - target_cards)
        )


@dataclass(frozen=True, slots=True)
class EvolutionConfig:
    population_size: int = 6
    generations: int = 3
    duplicate_deals: int = 20
    mutation_sigma: float = 0.25
    historical_opponents: int = 3
    seed: int = 0
    max_plies: int = 3_000

    def __post_init__(self) -> None:
        if self.population_size < 2 or self.generations < 1 or self.duplicate_deals < 1:
            raise ValueError("population, generations, and deals must be positive")
        if self.mutation_sigma <= 0 or self.historical_opponents < 1:
            raise ValueError("mutation sigma and historical opponent count must be positive")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    generation: int
    champion: LinearWeights
    champion_fitness: float
    population_fitness: tuple[float, ...]
    checkpoint: str | None


def _new_policy(spec: LinearWeights | str, ruleset: Ruleset, seed: int) -> Any:
    if isinstance(spec, LinearWeights):
        return LinearHeuristicAgent(spec, seed=seed)
    if spec == "heuristic":
        return BasicHeuristicAgent(seed=seed)
    if spec == "random":
        return RandomAgent(seed=seed)
    raise ValueError(spec)


def _play_lineup(
    seed: int,
    lineup: Sequence[LinearWeights | str],
    ruleset: Ruleset,
    max_plies: int,
) -> tuple[int, int]:
    agents = tuple(
        _new_policy(spec, ruleset, seed * 1_000_003 + seat * 101)
        for seat, spec in enumerate(lineup)
    )
    env = FishEnv(ruleset, seed=seed, debug=False)
    for _ in range(max_plies):
        if env.done:
            return env.scores
        player = env.current_player
        env.step(agents[player].select_action(env.observe(player)))
    raise RuntimeError(f"self-play game {seed} exceeded {max_plies} plies")


def _duplicate_points(
    candidate: LinearWeights,
    opponent: LinearWeights | str,
    *,
    ruleset: Ruleset,
    deals: int,
    seed: int,
    max_plies: int,
) -> float:
    points = 0.0
    for index in range(deals):
        deal_seed = seed + index
        first = _play_lineup(
            deal_seed,
            (candidate, opponent, candidate, opponent, candidate, opponent),
            ruleset,
            max_plies,
        )
        swapped = _play_lineup(
            deal_seed,
            (opponent, candidate, opponent, candidate, opponent, candidate),
            ruleset,
            max_plies,
        )
        points += 1.0 if first[0] > first[1] else 0.5 if first[0] == first[1] else 0.0
        points += 1.0 if swapped[1] > swapped[0] else 0.5 if swapped[0] == swapped[1] else 0.0
    return points / (2.0 * deals)


def train_population(
    config: EvolutionConfig,
    *,
    ruleset: Ruleset | None = None,
    output_directory: str | Path | None = None,
) -> tuple[GenerationResult, ...]:
    """Evolve a linear baseline against heuristic and historical champions."""
    rules = ruleset or Ruleset.joker_54()
    rng = random.Random(config.seed)
    champion = LinearWeights()
    history: list[LinearWeights] = [champion]
    results: list[GenerationResult] = []
    output = None if output_directory is None else Path(output_directory)
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)

    for generation in range(config.generations):
        population = [champion] + [
            champion.mutate(rng, config.mutation_sigma)
            for _ in range(config.population_size - 1)
        ]
        opponents: list[LinearWeights | str] = ["heuristic"]
        opponents.extend(history[-config.historical_opponents :])
        fitness: list[float] = []
        for candidate_index, candidate in enumerate(population):
            rates = [
                _duplicate_points(
                    candidate,
                    opponent,
                    ruleset=rules,
                    deals=config.duplicate_deals,
                    seed=config.seed + generation * 1_000_000 + candidate_index * 10_000 + opponent_index * 100,
                    max_plies=config.max_plies,
                )
                for opponent_index, opponent in enumerate(opponents)
            ]
            fitness.append(fmean(rates))
        champion_index = max(range(len(population)), key=lambda index: fitness[index])
        champion = population[champion_index]
        history.append(champion)
        checkpoint_path: str | None = None
        if output is not None:
            checkpoint = output / f"generation-{generation:04d}.json"
            if checkpoint.exists():
                raise FileExistsError(
                    f"refusing to overwrite existing checkpoint: {checkpoint}"
                )
            checkpoint.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generation": generation,
                        "ruleset": rules.name,
                        "config": asdict(config),
                        "champion": asdict(champion),
                        "champion_fitness": fitness[champion_index],
                        "population_fitness": fitness,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            checkpoint_path = str(checkpoint)
        results.append(
            GenerationResult(
                generation,
                champion,
                fitness[champion_index],
                tuple(fitness),
                checkpoint_path,
            )
        )
    return tuple(results)


__all__ = [
    "EvolutionConfig",
    "GenerationResult",
    "LinearHeuristicAgent",
    "LinearWeights",
    "train_population",
]
