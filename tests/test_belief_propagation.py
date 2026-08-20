"""Targeted tests for constraint propagation strength AND safety.

New inference power is exactly where unsoundness hides, so every rule gets
both a "does it actually deduce this?" test and a broad soundness fuzz.
"""

import random

import pytest

from fish.agents import MemoryAgent, ProbabilisticAgent, RandomAgent
from fish.beliefs import (BeliefContradiction, BeliefState,
                          validate_deal_against_history)
from fish.cards import cards_per_player
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("agent_cls", [RandomAgent, MemoryAgent])
def test_propagation_never_pins_a_falsehood(seed, agent_cls):
    """Soundness fuzz across agent styles: every 'certain' fact the belief
    engine asserts must be true, for every seat, at every step."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=seed * 31 + 5, debug=False)
    agents = [agent_cls() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    beliefs = [BeliefState(rules, observer=p) for p in range(6)]
    ext = BeliefState(rules, observer=None)
    while not state.is_terminal:
        actor = state.turn
        for p in range(6):
            beliefs[p].update(Observation.from_state(state, p))
        ext.update(Observation.from_state(state, 0))
        for bel in beliefs + [ext]:
            for p in range(6):
                known = bel.known_current_hands()[p]
                assert known & ~state.hands[p] == 0, "pinned a card wrongly"
            for c in range(54):
                holder = state.holder_of(c)
                if holder is not None:
                    assert bel.current_holder_mask(c) & (1 << holder)
        state.apply(actor, agents[actor].act(
            Observation.from_state(state, actor)))


def test_or_pigeonhole_deduces_exclusion():
    """If a player's every remaining unknown slot is consumed by disjoint
    'must hold one of these' requirements, no other card can be theirs."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=17, debug=False)
    bel = BeliefState(rules, observer=None)
    bel.update(Observation.from_state(state, 0))
    per = cards_per_player(rules.variant)
    groups = [tuple(range(i * 2, i * 2 + 2)) for i in range(per)]
    bel.ors = [(g, 1) for g in groups]
    covered = {c for g in groups for c in g}
    bel._propagate()
    for c in range(54):
        if c not in covered and not bel.is_pinned(c):
            assert not bel.candidates[c] & (1 << 1), (
                f"pigeonhole failed to exclude card {c} from player 1")


def test_or_pigeonhole_detects_contradiction():
    rules = RuleConfig()
    state = GameState.deal(rules, seed=19, debug=False)
    bel = BeliefState(rules, observer=None)
    bel.update(Observation.from_state(state, 0))
    per = cards_per_player(rules.variant)
    groups = [tuple(range(i * 2, i * 2 + 2)) for i in range(per + 2)]
    bel.ors = [(g, 2) for g in groups]
    with pytest.raises(BeliefContradiction):
        bel._propagate()


def test_sampled_worlds_always_replay_validate():
    """Every sampled world must survive an INDEPENDENT replay of the entire
    public history (a different code path from the constraint store)."""
    rules = RuleConfig()
    for seed in (2, 8):
        state = GameState.deal(rules, seed=seed, debug=False)
        agents = [ProbabilisticAgent(n_samples=8) for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        step = 0
        while not state.is_terminal:
            actor = state.turn
            obs = Observation.from_state(state, actor)
            if step % 12 == 0:
                bel = agents[actor].bel
                bel.update(obs)
                for _ in range(4):
                    deal = bel._sample_initial(rng, max_restarts=200)
                    initial = [0] * 6
                    for c, p in enumerate(deal):
                        initial[p] |= 1 << c
                    assert [h.bit_count() for h in initial] == [9] * 6
                    assert validate_deal_against_history(
                        rules, initial, tuple(state.history))
            state.apply(actor, agents[actor].act(obs))
            step += 1


def test_belief_rejects_midgame_attachment():
    """Attaching to a truncated transcript must fail loudly, not silently
    produce wrong beliefs."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=3, debug=False)
    agents = [MemoryAgent() for _ in range(6)]
    rng = random.Random(3)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(40):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
    stripped = GameState.from_components(rules, list(state.hands), state.turn,
                                         list(state.set_winner))
    fresh = BeliefState(rules, observer=stripped.turn)
    with pytest.raises(BeliefContradiction):
        fresh.update(Observation.from_state(stripped, stripped.turn))
