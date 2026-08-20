from __future__ import annotations

import json

import pytest

from fish.league import LeagueRegistry
from fish.storage import ExperimentStore


def test_league_is_append_only_and_promotion_is_conservative(tmp_path):
    registry = LeagueRegistry(tmp_path / "league.json")
    registry.register("random-v1", "random", rating=200, rating_uncertainty=10, config={})
    registry.register("belief-v1", "belief", rating=260, rating_uncertainty=10, config={})
    assert registry.champion_id == "random-v1"
    assert registry.promotion_margin("belief-v1") > 0
    registry.promote("belief-v1")
    assert LeagueRegistry(tmp_path / "league.json").champion_id == "belief-v1"
    with pytest.raises(ValueError):
        registry.register("belief-v1", "belief", rating=300, rating_uncertainty=1, config={})


def test_league_hashes_artifacts(tmp_path):
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"checkpoint")
    registry = LeagueRegistry(tmp_path / "league.json")
    record = registry.register(
        "model-v1", "neural", rating=1000, rating_uncertainty=30, config={}, artifact=artifact
    )
    assert record.artifact_sha256 is not None
    assert len(record.artifact_sha256) == 64


def test_store_keeps_summaries_and_optional_compressed_trace(tmp_path):
    path = tmp_path / "experiments.sqlite"
    with ExperimentStore(path) as store:
        store.create_experiment("smoke", {"seed": 7})
        store.add_game(
            "smoke",
            0,
            seed=7,
            ruleset="nine_suit_54",
            team_a_policy="random",
            team_b_policy="random",
            score_a=5,
            score_b=4,
            null_sets=0,
            winner=0,
            decisions=91,
            trace={"actions": [["ask", 1, 3]]},
        )
        store.add_game(
            "smoke",
            1,
            seed=8,
            ruleset="nine_suit_54",
            team_a_policy="random",
            team_b_policy="random",
            score_a=3,
            score_b=5,
            null_sets=1,
            winner=1,
            decisions=80,
        )
        assert store.read_trace("smoke", 0)["actions"][0][0] == "ask"
        assert store.read_trace("smoke", 1) is None
