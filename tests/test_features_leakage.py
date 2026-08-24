"""Feature-extraction leakage tests.

Features are a NEW pathway into a policy, so they get the same scrutiny as
observations: a feature vector must be reproducible from public information
plus the acting player's own hand, and must not change when hidden cards are
permuted into any other layout consistent with the public record.
"""

import random

import numpy as np

from fish.agents import ProbabilisticAgent, ValueSearchAgent
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.features import (extract, extract_perfect, feature_size,
                           perfect_feature_size)
from fish.observation import Observation
from fish.rules import RuleConfig
from fish.runner import play_game


def _mid_game(seed=5, steps=40):
    rules = RuleConfig()
    state = GameState.deal(rules, seed=seed)
    agents = [ProbabilisticAgent(n_samples=8) for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(steps):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    return rules, state, agents


def test_feature_vector_shape_and_finiteness():
    rules, state, _ = _mid_game()
    p = state.turn
    obs = Observation.from_state(state, p)
    bel = BeliefState(rules, observer=p)
    bel.update(obs)
    x = extract(obs, bel, rng=random.Random(0), n_worlds=8)
    assert x.shape == (feature_size("54"),)
    assert np.all(np.isfinite(x))
    assert x.dtype == np.float32


def test_features_reproducible_from_public_info_only():
    """Rebuild the observation from ONLY (rules, own initial hand, public
    history) and confirm identical features with a fixed sampling seed."""
    rules, state, _ = _mid_game(seed=9)
    p = state.turn
    engine_obs = Observation.from_state(state, p)
    public_obs = Observation.reconstruct(
        rules, p, engine_obs.initial_hand(), tuple(state.history))
    assert public_obs == engine_obs

    b1 = BeliefState(rules, observer=p); b1.update(engine_obs)
    b2 = BeliefState(rules, observer=p); b2.update(public_obs)
    x1 = extract(engine_obs, b1, rng=random.Random(3), n_worlds=12)
    x2 = extract(public_obs, b2, rng=random.Random(3), n_worlds=12)
    np.testing.assert_allclose(x1, x2, rtol=0, atol=0)


def test_features_invariant_to_consistent_hidden_permutations():
    """Replace the hidden cards with ANY other layout consistent with
    everything public. The acting player's features must not move: they
    cannot depend on unobservable detail."""
    rules, state, _ = _mid_game(seed=11)
    p = state.turn
    obs = Observation.from_state(state, p)
    bel = BeliefState(rules, observer=p)
    bel.update(obs)
    alt = bel.sample_current_hands(random.Random(21))   # a consistent world
    alt_state = GameState.from_components(rules, alt, state.turn,
                                          list(state.set_winner))
    alt_state.history = list(state.history)
    alt_obs = Observation.from_state(alt_state, p)
    assert alt_obs.hand == obs.hand                     # public facts match
    assert alt_obs.hand_counts == obs.hand_counts
    assert alt_obs.set_winner == obs.set_winner

    b2 = BeliefState(rules, observer=p)
    b2.update(alt_obs)
    x1 = extract(obs, bel, rng=random.Random(7), n_worlds=12)
    x2 = extract(alt_obs, b2, rng=random.Random(7), n_worlds=12)
    np.testing.assert_allclose(x1, x2, rtol=0, atol=1e-6)


def test_extract_never_touches_gamestate():
    """extract() must work with no GameState in scope at all."""
    rules, state, _ = _mid_game(seed=13)
    p = state.turn
    obs = Observation.from_state(state, p)
    bel = BeliefState(rules, observer=p)
    bel.update(obs)
    del state
    assert np.all(np.isfinite(extract(obs, bel, rng=random.Random(1),
                                      n_worlds=8)))


def test_perfect_features_are_well_formed():
    """The perfect-information evaluator's inputs are only ever built from
    a hypothesized world, never from the live game during action selection."""
    rules, state, _ = _mid_game(seed=17)
    x = extract_perfect(state.hands, state.set_winner, state.turn, 0, "54")
    assert x.shape == (perfect_feature_size("54"),)
    assert np.all(np.isfinite(x))
    # symmetry: the same position seen from the other team flips the
    # resolved-set differential
    y = extract_perfect(state.hands, state.set_winner, state.turn, 1, "54")
    g = 9 * 10
    assert x[g + 10] == -y[g + 10]


def test_value_search_degrades_gracefully_without_model():
    """No checkpoint -> static evaluation, still legal and terminating."""
    rules = RuleConfig()
    agents = [ValueSearchAgent(model_path="does/not/exist.pt", n_worlds=4,
                               n_candidates=3, n_samples=8)
              if i % 2 == 0 else ProbabilisticAgent(n_samples=8)
              for i in range(6)]
    st = play_game(agents, rules, seed=2, debug=True, agent_seed=1)
    assert st.is_terminal
    assert agents[0].uses_model is False
