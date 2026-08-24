"""Experiment registry and champion-league tests.

These enforce the research-integrity rules: experiments must be
reproducible from their manifest, and a new champion must beat the
incumbent convincingly rather than merely once.
"""

import tempfile
from pathlib import Path

import pytest

from fish.eval.league import Entry, League
from fish.registry import Experiment, load_all, record, summary


def test_experiment_manifest_captures_provenance():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "experiments.jsonl"
        exp = Experiment(name="demo", kind="matchup",
                         config={"x": "memory", "y": "probabilistic",
                                 "base_seed": 7, "agent_seed_base": 3},
                         result={"pair_score": 0.42},
                         evidence_tier="PROMISING")
        record(exp, path)
        rows = load_all(path)
        assert len(rows) == 1
        r = rows[0]
        assert r["name"] == "demo"
        assert r["commit"]                    # provenance present
        assert r["python"] and r["platform"]
        assert r["config"]["base_seed"] == 7  # enough to re-run
        assert r["id"]


def test_registry_is_append_only():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "experiments.jsonl"
        record(Experiment(name="a", kind="ablation"), path)
        record(Experiment(name="b", kind="benchmark"), path)
        rows = load_all(path)
        assert [r["name"] for r in rows] == ["a", "b"]
        assert "a" in summary(path) and "b" in summary(path)


def test_league_versions_are_immutable():
    with tempfile.TemporaryDirectory() as d:
        lg = League(Path(d) / "league.json")
        lg.register("probabilistic-v1", "probabilistic", {}, notes="baseline")
        with pytest.raises(ValueError):
            lg.register("probabilistic-v1", "probabilistic", {"n_samples": 64})


def test_champion_promotion_requires_convincing_evidence():
    with tempfile.TemporaryDirectory() as d:
        lg = League(Path(d) / "league.json")
        lg.register("v1", "probabilistic", {})
        lg.register("v2", "paired_search", {})
        # a coin-flip result must NOT promote
        with pytest.raises(ValueError):
            lg.promote("v2", {"wilson_ci": [0.42, 0.61], "pair_score": 0.52})
        assert lg.champion() is None
        # a decisive result promotes
        lg.promote("v2", {"wilson_ci": [0.58, 0.79], "pair_score": 0.68})
        assert lg.champion().version == "v2"


def test_league_persists_and_reloads():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "league.json"
        lg = League(p)
        lg.register("v1", "memory", {}, rating=1120.0, rating_stderr=26.0)
        again = League(p)
        assert "v1" in again.entries
        assert again.entries["v1"].rating == 1120.0
        assert again.entries["v1"].spec() == ("memory", {})
        assert "v1" in again.table()
