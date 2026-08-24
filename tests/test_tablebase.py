"""Exact endgame ("tablebase") tests.

The safety property that matters: the tablebase may fire ONLY when the
agent's own beliefs already determine every live card. If it ever fired on
an ambiguous position it would be reconstructing hidden state it has not
legitimately deduced, which is exactly the leak this project forbids.
"""

import random

import pytest

from fish.agents import (MemoryAgent, PairedSearchAgent, ProbabilisticAgent)
from fish.agents.tablebase import pinned_state
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.exact import ExactSolver, live_card_count
from fish.observation import Observation
from fish.rules import RuleConfig
from fish.runner import play_game


def _play_to(seed, steps, cls=ProbabilisticAgent):
    rules = RuleConfig()
    state = GameState.deal(rules, seed=seed)
    agents = [cls() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(steps):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    return rules, state, agents


def test_pinned_state_returns_none_at_game_start():
    """A fresh deal is maximally ambiguous; nothing may be reconstructed."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=4)
    bel = BeliefState(rules, observer=0)
    obs = Observation.from_state(state, 0)
    bel.update(obs)
    assert pinned_state(obs, bel) is None


def test_pinned_state_matches_truth_when_it_fires():
    """Whenever the reconstruction succeeds it must equal the real position.
    Checked across many steps of many games."""
    fired = 0
    for seed in range(6):
        rules = RuleConfig()
        state = GameState.deal(rules, seed=seed)
        agents = [ProbabilisticAgent(use_tablebase=False) for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        while not state.is_terminal:
            p = state.turn
            obs = Observation.from_state(state, p)
            agents[p].bel.update(obs)
            recon = pinned_state(obs, agents[p].bel)
            if recon is not None:
                fired += 1
                assert recon.hands == state.hands, (
                    "tablebase reconstruction disagreed with reality")
                assert recon.turn == state.turn
            state.apply(p, agents[p].act(obs))
    assert fired > 0, "tablebase never fired; test is vacuous"


def test_tablebase_never_fires_on_ambiguous_positions():
    """Direct safety check: if ANY live card has more than one candidate
    holder, reconstruction must refuse."""
    rules = RuleConfig()
    for seed in (11, 12, 13):
        state = GameState.deal(rules, seed=seed)
        agents = [ProbabilisticAgent(use_tablebase=False) for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        while not state.is_terminal:
            p = state.turn
            obs = Observation.from_state(state, p)
            bel = agents[p].bel
            bel.update(obs)
            ambiguous = any(
                (m := bel.current_holder_mask(c)) and m & (m - 1)
                for c in range(bel.n))
            if ambiguous:
                assert pinned_state(obs, bel) is None
            state.apply(p, agents[p].act(obs))


def test_tablebase_action_is_exactly_optimal_when_it_fires():
    """When the tablebase returns a move, it must be an exact optimum."""
    rules = RuleConfig()
    checked = 0
    for seed in range(8):
        state = GameState.deal(rules, seed=seed)
        agents = [ProbabilisticAgent() for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        while not state.is_terminal:
            p = state.turn
            obs = Observation.from_state(state, p)
            ag = agents[p]
            ag.bel.update(obs)
            act = ag.tablebase_action(obs)
            if act is not None and live_card_count(state) <= 7:
                solver = ExactSolver(rules)
                try:
                    opts = solver.optimal_actions(state)
                except Exception:
                    opts = None
                if opts:
                    checked += 1
                    assert any(act == o for o in opts), (
                        "tablebase returned a non-optimal action")
            state.apply(p, agents[p].act(obs))
    assert checked > 0, "never exercised; test is vacuous"


@pytest.mark.parametrize("cls", [MemoryAgent, ProbabilisticAgent,
                                 PairedSearchAgent])
def test_agents_still_play_legal_games_with_tablebase(cls):
    rules = RuleConfig()
    for seed in range(3):
        st = play_game([cls() for _ in range(6)], rules, seed=seed,
                       agent_seed=seed * 5 + 1, debug=True)
        assert st.is_terminal


def test_tablebase_can_be_ablated():
    rules = RuleConfig()
    a = ProbabilisticAgent(use_tablebase=False)
    assert a.use_tablebase is False
    st = play_game([ProbabilisticAgent(use_tablebase=False) for _ in range(6)],
                   rules, seed=1, agent_seed=2, debug=True)
    assert st.is_terminal
