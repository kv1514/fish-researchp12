from __future__ import annotations

import math

import pytest

from fish.evaluation import (
    DuplicateEvaluator,
    EloRatings,
    make_seeded_game_runner,
    mean_confidence_interval,
    round_robin,
    wilson_interval,
)
from fish.agents import RandomAgent
from fish.core import FishEnv, Ruleset


def test_confidence_intervals_cover_estimates_and_shrink() -> None:
    interval = wilson_interval(60, 100)
    assert interval.low < 0.6 < interval.high
    assert interval.samples == 100
    paired = mean_confidence_interval([1.0, 1.1, 0.9, 1.0])
    assert paired.low < 1.0 < paired.high
    assert paired.samples == 4


def test_duplicate_evaluation_cancels_deal_luck_and_swaps_teams() -> None:
    calls: list[tuple[int, tuple[str, ...]]] = []

    def play(seed: int, policies: tuple[str, ...]) -> tuple[float, float]:
        calls.append((seed, tuple(policies)))
        luck = float((seed * 17) % 11 - 5)
        even_strength = 1.0 if policies[0] == "strong" else 0.0
        odd_strength = 1.0 if policies[1] == "strong" else 0.0
        return luck + even_strength, odd_strength

    report = DuplicateEvaluator(play).evaluate(
        "strong", "weak", deals=9, seed=100, policy_a_name="S", policy_b_name="W"
    )
    assert len(calls) == 18
    assert all(calls[index][0] == calls[index + 1][0] for index in range(0, 18, 2))
    assert calls[0][1] == ("strong", "weak", "strong", "weak", "strong", "weak")
    assert calls[1][1] == ("weak", "strong", "weak", "strong", "weak", "strong")
    assert report.paired_margin.estimate == pytest.approx(1.0)


def test_elo_updates_are_zero_sum_and_order_stronger_policy_first() -> None:
    ratings = EloRatings(base=1000, k_factor=20)
    for _ in range(20):
        ratings.update("strong", "weak", 1.0)
    assert ratings.get("strong").value > ratings.get("weak").value
    assert ratings.get("strong").value + ratings.get("weak").value == pytest.approx(2000)
    assert ratings.get("strong").uncertainty < 350
    assert ratings.table()[0][0] == "strong"


def test_round_robin_runs_every_pair() -> None:
    def play(seed: int, policies: tuple[str, ...]) -> tuple[float, float]:
        del seed
        return (1.0, 0.0) if policies[0] < policies[1] else (0.0, 1.0)

    result = round_robin(
        {"a": "a", "b": "b", "c": "c"},
        DuplicateEvaluator(play),
        deals_per_pair=2,
    )
    assert len(result.reports) == math.comb(3, 2)
    assert {name for name, _ in result.ratings} == {"a", "b", "c"}


def test_invalid_statistical_inputs_fail_loudly() -> None:
    with pytest.raises(ValueError):
        wilson_interval(2, 1)
    with pytest.raises(ValueError):
        mean_confidence_interval([])


def test_seeded_runner_keeps_environment_outside_policy_boundary() -> None:
    ruleset = Ruleset.standard_48()
    runner = make_seeded_game_runner(lambda: FishEnv(ruleset, debug=True), max_plies=500)
    policies = tuple(
        RandomAgent(seed=player + 40, claim_probability=0.25) for player in range(6)
    )
    even, odd = runner(77, policies)
    assert 0 <= even <= ruleset.num_half_suits
    assert 0 <= odd <= ruleset.num_half_suits
    assert even + odd <= ruleset.num_half_suits
