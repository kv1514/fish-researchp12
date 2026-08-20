"""Phase-1 fuzzing: random games with invariant checks after every action."""

import random

import pytest

from fish.agents import RandomAgent
from fish.rules import RuleConfig
from fish.runner import play_game


@pytest.mark.parametrize("variant,n_games", [("54", 100), ("48", 60)])
def test_random_games_terminate_with_valid_scores(variant, n_games):
    rules = RuleConfig(variant=variant)
    total_hs = 9 if variant == "54" else 8
    for seed in range(n_games):
        agents = [RandomAgent() for _ in range(6)]
        state = play_game(agents, rules, seed=seed, debug=True,
                          agent_seed=seed * 31 + 7)
        assert state.is_terminal
        a, b, n = state.scores()
        assert a + b + n == total_hs
        assert all(h == 0 for h in state.hands)


def test_deterministic_replay():
    """Same deal seed AND same agent seed reproduces exactly; changing
    either changes the game."""
    rules = RuleConfig()
    h1 = play_game([RandomAgent() for _ in range(6)], rules, seed=42,
                   agent_seed=1).history
    h2 = play_game([RandomAgent() for _ in range(6)], rules, seed=42,
                   agent_seed=1).history
    assert h1 == h2
    h3 = play_game([RandomAgent() for _ in range(6)], rules, seed=43,
                   agent_seed=1).history
    assert h1 != h3


@pytest.mark.parametrize("kwargs", [
    dict(wrong_distribution_outcome="opponent"),
    dict(allow_bluff_asks=True),
    dict(starting_player=3),
    dict(variant="48", wrong_distribution_outcome="opponent"),
])
def test_rule_variants_fuzz(kwargs):
    rules = RuleConfig(**kwargs)
    for seed in range(30):
        state = play_game([RandomAgent() for _ in range(6)], rules,
                          seed=seed, debug=True, agent_seed=seed + 100)
        assert state.is_terminal


def test_transfer_conservation_deep():
    """Track every card's location across full games and verify each ask
    moves exactly the named card and nothing else."""
    from fish.engine import AskEvent, ClaimEvent, GameState
    from fish.observation import Observation

    rules = RuleConfig()
    for seed in (1, 2, 3, 4, 5):
        state = GameState.deal(rules, seed=seed, debug=True)
        loc = {}
        for p in range(6):
            for c in range(54):
                if state.hands[p] & (1 << c):
                    loc[c] = p
        agents = [RandomAgent() for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        while not state.is_terminal:
            p = state.turn
            ev = state.apply(p, agents[p].act(Observation.from_state(state, p)))
            if isinstance(ev, AskEvent) and ev.success:
                assert loc[ev.card] == ev.target
                loc[ev.card] = ev.asker
            elif isinstance(ev, ClaimEvent):
                base = ev.half_suit * 6
                for i, holder in enumerate(ev.revealed):
                    assert loc[base + i] == holder
                    loc[base + i] = "resolved"
            for c, holder in loc.items():
                if holder == "resolved":
                    assert all(not state.hands[q] & (1 << c) for q in range(6))
                else:
                    assert state.hands[holder] & (1 << c)
