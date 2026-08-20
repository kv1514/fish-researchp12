from __future__ import annotations

import json

import pytest

from fish.analysis import analysis_as_dict, analyze_observation, observation_from_dict
from fish.cli import main
from fish.core import AskAction


def sample_state():
    return {
        "ruleset": "54",
        "player": 0,
        "turn": 0,
        "own_hand": ["2C", "3C", "9D", "TD", "4H", "5S", "8C", "JK1", "AS"],
        "card_counts": [9, 9, 9, 9, 9, 9],
        "scores": [0, 0],
        "resolved_owners": ["unresolved"] * 9,
        "history": [],
    }


def test_observation_parser_generates_only_public_legal_asks():
    observation = observation_from_dict(sample_state())
    assert observation.own_hand
    assert observation.legal_asks
    assert all(isinstance(action, AskAction) for action in observation.legal_asks)
    assert all(action.target in (1, 3, 5) for action in observation.legal_asks)
    assert not any(action.card in observation.own_hand for action in observation.legal_asks)


def test_parser_rejects_nonconserving_observation():
    state = sample_state()
    state["card_counts"][1] = 8
    with pytest.raises(ValueError, match="conserve"):
        observation_from_dict(state)


def test_search_analysis_returns_ranked_actions_and_beliefs():
    observation = observation_from_dict(sample_state())
    result = analyze_observation(
        observation, particle_count=24, determinizations=12, alternatives=3, seed=4
    )
    payload = analysis_as_dict(result, observation.ruleset)
    assert payload["best_action"]
    assert 1 <= len(payload["alternatives"]) <= 3
    assert "uncalibrated" in payload["value_label"]


def test_cli_analyze_emits_json(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(sample_state()), encoding="utf-8")
    assert main([
        "analyze", str(state_path), "--particles", "18", "--determinizations", "8"
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["best_action"]
