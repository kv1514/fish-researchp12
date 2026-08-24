"""Agent sanity: every agent plays full, legal, terminating games from the
observation boundary alone."""

import pytest

from fish.agents import (HeuristicAgent, MemoryAgent, PairedSearchAgent,
                         ProbabilisticAgent, RandomAgent)
from fish.cards import team_of
from fish.engine import ClaimEvent
from fish.rules import RuleConfig
from fish.runner import GameTimeout, play_game


@pytest.mark.parametrize("agent_cls,n_games", [
    (HeuristicAgent, 15), (MemoryAgent, 10), (ProbabilisticAgent, 4),
])
def test_homogeneous_tables_terminate(agent_cls, n_games):
    rules = RuleConfig()
    for seed in range(n_games):
        state = play_game([agent_cls() for _ in range(6)], rules,
                          seed=seed, debug=True, agent_seed=seed * 13 + 1)
        assert state.is_terminal


def test_mixed_table_terminates():
    rules = RuleConfig()
    for seed in range(4):
        agents = [RandomAgent(), HeuristicAgent(), MemoryAgent(),
                  HeuristicAgent(), MemoryAgent(), RandomAgent()]
        state = play_game(agents, rules, seed=seed, debug=True,
                          agent_seed=seed + 5)
        assert state.is_terminal


def test_paired_search_plays_legal_games():
    rules = RuleConfig()
    agents = [PairedSearchAgent(n_worlds=4, n_candidates=3, rollout_depth=16,
                                n_samples=12) if p % 2 == 0 else HeuristicAgent()
              for p in range(6)]
    state = play_game(agents, rules, seed=0, debug=True, agent_seed=2)
    assert state.is_terminal


@pytest.mark.parametrize("agent_cls", [RandomAgent, HeuristicAgent, MemoryAgent])
def test_termination_across_varied_agent_seeds(agent_cls):
    """Regression: games must terminate for ANY agent randomness, not just
    the seeds that happened to work. A livelock (cards shuttling between two
    opponents with successful asks) once slipped past the stall detector."""
    rules = RuleConfig()
    for i in range(20):
        try:
            st = play_game([agent_cls() for _ in range(6)], rules,
                           seed=i, agent_seed=i * 7919 + 31, max_actions=6000)
        except GameTimeout:
            raise AssertionError(f"{agent_cls.__name__} livelocked on deal {i}")
        assert st.is_terminal


def test_memory_agent_claims_mostly_correctly():
    """Memory agents claim only on certainty except when forced, so their
    claims must usually score for their own team."""
    rules = RuleConfig()
    bad = total = 0
    for seed in range(10):
        state = play_game([MemoryAgent() for _ in range(6)], rules, seed=seed,
                          agent_seed=seed * 3 + 1)
        for ev in state.history:
            if isinstance(ev, ClaimEvent):
                total += 1
                if ev.winner != team_of(ev.claimer):
                    bad += 1
    assert total > 0
    assert bad / total < 0.35, f"{bad}/{total} claims misfired"


def test_48_variant_agents():
    rules = RuleConfig(variant="48")
    state = play_game([MemoryAgent() for _ in range(6)], rules, seed=1,
                      debug=True, agent_seed=9)
    assert state.is_terminal
