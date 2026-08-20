from __future__ import annotations

import json

import pytest

from fish.core import Ruleset
from fish.selfplay import EvolutionConfig, LinearWeights, train_population


def test_weight_mutation_is_deterministic_and_bounded():
    import random

    left = LinearWeights().mutate(random.Random(4), 0.2)
    right = LinearWeights().mutate(random.Random(4), 0.2)
    assert left == right
    assert -5 <= left.suit_concentration <= 5


def test_tiny_population_selfplay_writes_append_only_generation_checkpoint(tmp_path):
    results = train_population(
        EvolutionConfig(
            population_size=2,
            generations=1,
            duplicate_deals=1,
            seed=9,
            max_plies=3000,
        ),
        ruleset=Ruleset.standard_48(),
        output_directory=tmp_path,
    )
    assert len(results) == 1
    checkpoint = tmp_path / "generation-0000.json"
    assert checkpoint.is_file()
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert payload["generation"] == 0
    assert len(payload["population_fitness"]) == 2
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        train_population(
            EvolutionConfig(
                population_size=2,
                generations=1,
                duplicate_deals=1,
                seed=9,
                max_plies=3000,
            ),
            ruleset=Ruleset.standard_48(),
            output_directory=tmp_path,
        )
