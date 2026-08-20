"""Duplicate-match evaluation, confidence intervals, tournaments, and ratings."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from statistics import NormalDist, fmean, stdev
from typing import Any, Callable, Hashable, Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    estimate: float
    low: float
    high: float
    confidence: float
    samples: int


def mean_confidence_interval(
    values: Sequence[float], confidence: float = 0.95
) -> ConfidenceInterval:
    """Normal-approximation CI for paired score differences."""

    if not values:
        raise ValueError("at least one value is required")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie between zero and one")
    mean = fmean(values)
    if len(values) == 1:
        return ConfidenceInterval(mean, mean, mean, confidence, 1)
    critical = NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    margin = critical * stdev(values) / math.sqrt(len(values))
    return ConfidenceInterval(mean, mean - margin, mean + margin, confidence, len(values))


def wilson_interval(
    successes: float, trials: int, confidence: float = 0.95
) -> ConfidenceInterval:
    """Wilson score interval; fractional successes support half-point draws."""

    if trials < 1 or not 0.0 <= successes <= trials:
        raise ValueError("successes must be between zero and trials")
    z = NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)
        )
        / denominator
    )
    return ConfidenceInterval(proportion, center - radius, center + radius, confidence, trials)


@dataclass(frozen=True, slots=True)
class GameOutcome:
    seed: int
    even_score: float
    odd_score: float
    policies: tuple[Hashable, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def even_points(self) -> float:
        if self.even_score > self.odd_score:
            return 1.0
        if self.even_score < self.odd_score:
            return 0.0
        return 0.5


@dataclass(frozen=True, slots=True)
class DuplicatePair:
    seed: int
    first: GameOutcome
    swapped: GameOutcome

    @property
    def policy_a_points(self) -> float:
        # A is the even team in the first game and odd team in the swap.
        return self.first.even_points + (1.0 - self.swapped.even_points)

    @property
    def paired_margin(self) -> float:
        first_margin = self.first.even_score - self.first.odd_score
        swapped_margin_for_a = self.swapped.odd_score - self.swapped.even_score
        return 0.5 * (first_margin + swapped_margin_for_a)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    policy_a: Hashable
    policy_b: Hashable
    pairs: tuple[DuplicatePair, ...]
    point_rate: ConfidenceInterval
    paired_margin: ConfidenceInterval


PlayGame = Callable[[int, Sequence[Any]], tuple[float, float] | GameOutcome]


def make_seeded_game_runner(
    env_factory: Callable[[], Any],
    *,
    max_plies: int = 10_000,
) -> PlayGame:
    """Adapt a FishEnv factory to the duplicate evaluator's callback.

    This function is the sole evaluation layer that sees an environment.  Each
    policy is passed only ``env.observe(current_player)`` and a compact action set
    derived from that observation.  Agents exposing ``select_action`` control
    their own public candidate construction; simpler policies may expose only
    ``choose_action`` and receive the observation's asks/admin actions.
    """

    if max_plies < 1:
        raise ValueError("max_plies must be positive")

    def play(seed: int, policies: Sequence[Any]) -> tuple[float, float]:
        if len(policies) != 6:
            raise ValueError("Fish evaluation requires one policy per seat")
        env = env_factory()
        env.reset(seed=seed)
        for _ in range(max_plies):
            if env.done:
                return float(env.scores[0]), float(env.scores[1])
            player = env.current_player
            observation = env.observe(player)
            policy = policies[player]
            if hasattr(policy, "select_action"):
                action = policy.select_action(observation)
            else:
                candidates = tuple(getattr(observation, "legal_admin_actions", ()))
                if not candidates:
                    candidates = tuple(getattr(observation, "legal_asks", ()))
                action = policy.choose_action(observation, candidates)
            env.step(action)
        raise RuntimeError(f"game exceeded the {max_plies}-ply evaluation limit")

    return play


class DuplicateEvaluator:
    """Evaluate two team policies on identical seeded deals with team swaps.

    ``play_game(seed, six_policies)`` is the only environment-specific adapter.
    It must recreate the same hidden deal for a repeated seed and return scores
    for the even and odd teams.  Policies are rotated within each team across
    pairs, controlling both deal luck and seat position when team policies are
    supplied as three-member lineups.
    """

    def __init__(self, play_game: PlayGame, *, confidence: float = 0.95) -> None:
        self.play_game = play_game
        self.confidence = confidence

    @staticmethod
    def _lineup(policy: Any | Sequence[Any]) -> tuple[Any, Any, Any]:
        if isinstance(policy, Sequence) and not isinstance(policy, (str, bytes)):
            if len(policy) != 3:
                raise ValueError("team lineups must contain exactly three policies")
            return tuple(policy)  # type: ignore[return-value]
        return policy, policy, policy

    @staticmethod
    def _rotate(lineup: tuple[Any, Any, Any], offset: int) -> tuple[Any, Any, Any]:
        offset %= 3
        return lineup[offset:] + lineup[:offset]

    @staticmethod
    def _seats(even: Sequence[Any], odd: Sequence[Any]) -> tuple[Any, ...]:
        return even[0], odd[0], even[1], odd[1], even[2], odd[2]

    def _run(self, seed: int, policies: Sequence[Any]) -> GameOutcome:
        result = self.play_game(seed, policies)
        labels = tuple(getattr(policy, "name", type(policy).__name__) for policy in policies)
        if isinstance(result, GameOutcome):
            return result
        return GameOutcome(seed, float(result[0]), float(result[1]), labels)

    def evaluate(
        self,
        policy_a: Any | Sequence[Any],
        policy_b: Any | Sequence[Any],
        *,
        deals: int,
        seed: int = 0,
        policy_a_name: Hashable = "A",
        policy_b_name: Hashable = "B",
    ) -> EvaluationReport:
        if deals < 1:
            raise ValueError("deals must be positive")
        lineup_a = self._lineup(policy_a)
        lineup_b = self._lineup(policy_b)
        pairs: list[DuplicatePair] = []
        for index in range(deals):
            deal_seed = seed + index
            rotated_a = self._rotate(lineup_a, index)
            rotated_b = self._rotate(lineup_b, index)
            first = self._run(deal_seed, self._seats(rotated_a, rotated_b))
            swapped = self._run(deal_seed, self._seats(rotated_b, rotated_a))
            pairs.append(DuplicatePair(deal_seed, first, swapped))
        point_successes = sum(pair.policy_a_points for pair in pairs)
        return EvaluationReport(
            policy_a_name,
            policy_b_name,
            tuple(pairs),
            wilson_interval(point_successes, 2 * deals, self.confidence),
            mean_confidence_interval(
                [pair.paired_margin for pair in pairs], self.confidence
            ),
        )


@dataclass(slots=True)
class Rating:
    value: float = 1000.0
    games: int = 0
    uncertainty: float = 350.0


class EloRatings:
    """Transparent online rating scaffold with decaying uncertainty.

    Duplicate reports should be fed as individual game points.  This is not a
    replacement for a full Glicko/Bradley-Terry fit, but provides a reproducible
    league ordering while retaining a visible uncertainty indicator.
    """

    def __init__(self, *, base: float = 1000.0, k_factor: float = 24.0) -> None:
        self.base = base
        self.k_factor = k_factor
        self.ratings: dict[Hashable, Rating] = {}

    def get(self, policy: Hashable) -> Rating:
        return self.ratings.setdefault(policy, Rating(self.base))

    @staticmethod
    def expected(rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

    def update(self, policy_a: Hashable, policy_b: Hashable, score_a: float) -> None:
        if not 0.0 <= score_a <= 1.0:
            raise ValueError("score must be in [0, 1]")
        a = self.get(policy_a)
        b = self.get(policy_b)
        expected_a = self.expected(a.value, b.value)
        delta = self.k_factor * (score_a - expected_a)
        a.value += delta
        b.value -= delta
        a.games += 1
        b.games += 1
        a.uncertainty = 350.0 / math.sqrt(1.0 + a.games / 8.0)
        b.uncertainty = 350.0 / math.sqrt(1.0 + b.games / 8.0)

    def update_report(self, report: EvaluationReport) -> None:
        for pair in report.pairs:
            self.update(report.policy_a, report.policy_b, pair.first.even_points)
            self.update(report.policy_a, report.policy_b, 1.0 - pair.swapped.even_points)

    def table(self) -> list[tuple[Hashable, Rating]]:
        return sorted(self.ratings.items(), key=lambda item: item[1].value, reverse=True)


@dataclass(frozen=True, slots=True)
class TournamentResult:
    reports: tuple[EvaluationReport, ...]
    ratings: tuple[tuple[Hashable, Rating], ...]


def round_robin(
    policies: Mapping[Hashable, Any],
    evaluator: DuplicateEvaluator,
    *,
    deals_per_pair: int,
    seed: int = 0,
) -> TournamentResult:
    """Run a duplicate round robin and derive deterministic online ratings."""

    names = list(policies)
    reports: list[EvaluationReport] = []
    ratings = EloRatings()
    pair_index = 0
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            report = evaluator.evaluate(
                policies[left],
                policies[right],
                deals=deals_per_pair,
                seed=seed + pair_index * deals_per_pair,
                policy_a_name=left,
                policy_b_name=right,
            )
            reports.append(report)
            ratings.update_report(report)
            pair_index += 1
    return TournamentResult(tuple(reports), tuple(ratings.table()))
