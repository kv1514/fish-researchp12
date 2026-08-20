from __future__ import annotations

from fish.agents import BasicHeuristicAgent, ProbabilisticAgent, RandomAgent, SearchAgent
from fish.belief import ParticleBelief
from fish.core import ClaimAction, FishEnv, Ruleset


def test_ruleset_can_be_passed_directly_to_belief_and_agents() -> None:
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=21)
    observation = env.reset(seed=21, turn=0)
    belief = ParticleBelief(ruleset, particle_count=24, seed=1).update(observation)
    belief.validate_particles(observation)
    agent = ProbabilisticAgent(ruleset, particle_count=24, seed=1)
    candidates = agent.candidate_actions(observation)
    assert candidates
    assert agent.choose_action(observation, candidates) in candidates


def test_resolved_half_suit_cards_have_no_owner_in_every_particle() -> None:
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=8)
    observation = env.observe(env.current_player)
    half_suit = observation.legal_claim_half_suits[0]
    # Any public-legal allocation resolves the set under the baseline, even when
    # wrong. The policy never receives the state used by this simulator test.
    claim = ClaimAction(observation.player, half_suit, (observation.player,) * 6)
    next_observation = env.step(claim).observation
    belief = ParticleBelief(ruleset, particle_count=24, seed=4).update(next_observation)
    for card in ruleset.half_suits[half_suit].cards:
        assert belief.probability(card, None) == 1.0


def test_baseline_claim_scoring_does_not_confuse_legality_with_correctness() -> None:
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=3)
    observation = env.reset(seed=3, turn=0)
    claim = ClaimAction(observation.player, 0, (observation.player,) * 6)
    agent = BasicHeuristicAgent(seed=2)
    assert agent.score_action(observation, claim) < 0


def test_compact_candidate_generation_avoids_enormous_claim_action_space() -> None:
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=5)
    observation = env.reset(seed=5, turn=0)
    random_agent = RandomAgent(seed=1, claim_probability=1.0)
    candidates = random_agent.candidate_actions(observation)
    assert len(candidates) <= len(observation.legal_asks) + 1
    assert any(isinstance(action, ClaimAction) for action in candidates)


def test_random_agents_finish_a_real_seeded_game_via_observations_only() -> None:
    env = FishEnv(Ruleset.standard_48(), seed=13)
    agents = [RandomAgent(seed=100 + player, claim_probability=0.12) for player in range(6)]
    for _ in range(1000):
        if env.done:
            break
        player = env.current_player
        observation = env.observe(player)
        action = agents[player].select_action(observation)
        env.step(action)
    assert env.done
    assert sum(env.scores) <= env.ruleset.num_half_suits


def test_search_uses_only_player_observation_on_real_core() -> None:
    ruleset = Ruleset.joker_54()
    env = FishEnv(ruleset, seed=144)
    observation = env.reset(seed=144, turn=0)
    left = SearchAgent(
        ruleset, particle_count=30, determinizations=20, depth=2, seed=10
    )
    right = SearchAgent(
        ruleset, particle_count=30, determinizations=20, depth=2, seed=10
    )
    assert left.select_action(observation) == right.select_action(observation)
