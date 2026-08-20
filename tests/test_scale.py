from __future__ import annotations

import json

import pytest

from fish.scale import (
    SimulationConfig,
    estimate_storage,
    lineup_for_game,
    run_simulation,
    seed_for_game,
    shard_specs,
)


def test_ten_million_plan_is_compact_and_does_not_materialize_games():
    config = SimulationConfig(
        games=10_000_000,
        lineup=("random",) * 6,
        shard_size=10_000,
    )
    storage = estimate_storage(config)
    assert storage["shards"] == 1_000
    assert storage["detailed_game_traces"] == 0
    assert storage["estimated_metadata_bytes"] < 2_000_000


def test_duplicate_lineups_share_seed_rotate_and_swap_teams():
    lineup = ("random", "heuristic", "memory", "probabilistic", "search", "random")
    config = SimulationConfig(games=6, lineup=lineup, paired=True, base_seed=90)
    assert seed_for_game(config, 0) == seed_for_game(config, 1) == 90
    assert lineup_for_game(config, 0) == lineup
    assert lineup_for_game(config, 1) == (
        "heuristic", "random", "probabilistic", "memory", "random", "search"
    )
    assert lineup_for_game(config, 2) == (
        "memory", "probabilistic", "search", "random", "random", "heuristic"
    )


def test_shards_cover_every_game_exactly_once():
    config = SimulationConfig(games=11, lineup=("random",) * 6, shard_size=4)
    specs = shard_specs(config)
    assert [(item.start_game, item.end_game) for item in specs] == [(0, 4), (4, 8), (8, 11)]
    assert sum(item.games for item in specs) == 11


def test_single_worker_run_checkpoints_and_resumes_without_replaying(tmp_path):
    output = tmp_path / "simulation"
    config = SimulationConfig(
        games=8,
        lineup=("random",) * 6,
        ruleset="48",
        base_seed=800,
        workers=1,
        shard_size=3,
        max_plies=2_000,
    )
    first = run_simulation(config, output)
    assert first.complete
    assert first.completed_games == 8
    assert first.completed_shards == 3
    assert first.team_a_wins + first.team_b_wins + first.ties == 8
    assert len(list((output / "shards").glob("shard-*.json"))) == 3
    assert json.loads((output / "manifest.json").read_text())["fingerprint"] == config.fingerprint

    resumed = run_simulation(config, output, resume=True)
    assert resumed.complete
    assert resumed.completed_games == first.completed_games
    assert resumed.invocation_games_per_second == 0.0
    with pytest.raises(FileExistsError, match="pass resume=True"):
        run_simulation(config, output)


def test_resume_rejects_configuration_drift(tmp_path):
    output = tmp_path / "simulation"
    config = SimulationConfig(games=2, lineup=("random",) * 6, workers=1)
    run_simulation(config, output)
    changed = SimulationConfig(
        games=2,
        lineup=("heuristic",) * 6,
        workers=1,
    )
    with pytest.raises(ValueError, match="does not match"):
        run_simulation(changed, output, resume=True)
