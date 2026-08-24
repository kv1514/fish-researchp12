"""Information-integrity tests (SPEC sections 5 and 7.7).

The central proof: an Observation the engine hands to a player must be
identical to one reconstructed from ONLY (rules, player id, that player's
initial hand, public event log). If the engine ever smuggled private state
into observations, these tests break.
"""

import random

import pytest

from fish.agents import RandomAgent
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def _play_and_check(rules: RuleConfig, seed: int):
    state = GameState.deal(rules, seed=seed, debug=True)
    initial_hands = list(state.hands)
    agents = [RandomAgent() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    step = 0
    while not state.is_terminal:
        p = state.turn
        obs = Observation.from_state(state, p)
        for q in range(6):  # every seat, not just the actor
            engine_obs = Observation.from_state(state, q)
            rebuilt = Observation.reconstruct(
                rules, q, initial_hands[q], tuple(state.history))
            assert engine_obs == rebuilt, (
                f"observation for P{q} at step {step} contains non-public "
                f"information")
            assert engine_obs.initial_hand() == initial_hands[q]
        state.apply(p, agents[p].act(obs))
        step += 1
    for q in range(6):
        engine_obs = Observation.from_state(state, q)
        rebuilt = Observation.reconstruct(
            rules, q, initial_hands[q], tuple(state.history))
        assert engine_obs.hand == rebuilt.hand
        assert engine_obs.hand_counts == rebuilt.hand_counts
        assert engine_obs.set_winner == rebuilt.set_winner


@pytest.mark.parametrize("seed", range(20))
def test_observation_reconstructible_from_public_info_54(seed):
    _play_and_check(RuleConfig(), seed)


@pytest.mark.parametrize("seed", range(8))
def test_observation_reconstructible_from_public_info_48(seed):
    _play_and_check(RuleConfig(variant="48"), seed)


def test_observation_has_no_other_card_fields():
    """The observation type exposes exactly the public fields; on a fresh
    deal the only card information present is the observer's own hand."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=99, debug=True)
    for q in range(6):
        obs = Observation.from_state(state, q)
        fields = {f: getattr(obs, f) for f in
                  ("player", "rules", "hand", "turn", "hand_counts",
                   "set_winner", "history")}
        assert fields["history"] == ()
        assert fields["hand"] == state.hands[q]
        assert fields["hand_counts"] == (9,) * 6
        assert set(Observation.__dataclass_fields__) == set(fields)


def test_legal_actions_computable_from_observation_only():
    rules = RuleConfig()
    for seed in range(8):
        state = GameState.deal(rules, seed=seed, debug=True)
        agents = [RandomAgent() for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        while not state.is_terminal:
            p = state.turn
            obs = Observation.from_state(state, p)
            assert set(obs.legal_asks()) == set(state.legal_asks(p))
            assert obs.claimable_half_suits() == state.claimable_half_suits(p)
            assert set(obs.legal_passes()) == set(state.legal_passes(p))
            assert obs.must_claim() == state.must_claim(p)
            state.apply(p, agents[p].act(obs))


def test_observation_json_roundtrip():
    rules = RuleConfig()
    state = GameState.deal(rules, seed=5, debug=True)
    agents = [RandomAgent() for _ in range(6)]
    rng = random.Random(5)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(60):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    obs = Observation.from_state(state, 2)
    assert Observation.from_json(obs.to_json()) == obs
