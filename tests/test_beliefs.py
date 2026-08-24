"""Belief-engine soundness tests.

Gold standards:
1. TRUTH IN SUPPORT: at every step of real games, the true state must remain
   consistent with every tracked constraint, for all six observers AND an
   external spectator.
2. SAMPLES VALID: every sampled world must pass an INDEPENDENT replay
   validation of the full public history and match all public hand counts.
3. Specific textbook inferences must come out exactly right.
"""

import random

import pytest

from fish.agents import ProbabilisticAgent, RandomAgent
from fish.beliefs import BeliefState, validate_deal_against_history
from fish.cards import NUM_PLAYERS, card_id
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

from helpers import make_state


def cid(name):
    return card_id(name)


@pytest.mark.parametrize("seed", range(8))
def test_truth_always_in_support_and_samples_valid(seed):
    rules = RuleConfig()
    state = GameState.deal(rules, seed=seed, debug=True)
    initial_hands = list(state.hands)
    agents = [RandomAgent() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, rng.getrandbits(64))
    beliefs = {p: BeliefState(rules, observer=p) for p in range(6)}
    beliefs["ext"] = BeliefState(rules, observer=None)
    sample_rng = random.Random(seed * 7 + 1)
    step = 0
    while not state.is_terminal:
        actor = state.turn
        obs = Observation.from_state(state, actor)
        for key, bel in beliefs.items():
            seat = 0 if key == "ext" else key
            bel.update(Observation.from_state(state, seat))
            # --- truth in support ---
            for c in range(54):
                holder = state.holder_of(c)
                m = bel.current_holder_mask(c)
                if holder is None:
                    assert m == 0, (
                        f"step {step}: belief[{key}] places resolved card "
                        f"{c} with a player (mask={m:06b})")
                else:
                    assert m & (1 << holder), (
                        f"step {step}: belief[{key}] excludes true holder "
                        f"of card {c}")
            for p in range(6):
                known = bel.known_current_hands()[p]
                assert known & ~state.hands[p] == 0, (
                    f"step {step}: belief[{key}] 'knows' a wrong card at P{p}")
        # --- sampled worlds valid (spot-check to keep runtime sane) ---
        if step % 25 == 0:
            bel = beliefs[actor]
            for _ in range(5):
                deal = bel._sample_initial(sample_rng, max_restarts=200)
                sampled_initial = [0] * 6
                for c, p in enumerate(deal):
                    sampled_initial[p] |= 1 << c
                assert validate_deal_against_history(
                    rules, sampled_initial, tuple(state.history)), (
                    f"step {step}: sampled world fails history replay")
                hands_now = [0] * 6
                for c in range(54):
                    loc = bel.public_loc[c]
                    if loc == -2:
                        continue
                    hands_now[deal[c] if loc is None else loc] |= 1 << c
                assert hands_now[actor] == state.hands[actor]
                assert [h.bit_count() for h in hands_now] == \
                    list(state.hand_counts())
        state.apply(actor, agents[actor].act(obs))
        step += 1


def test_external_observer_tracks_public_only():
    rules = RuleConfig()
    for seed in (11, 12):
        state = GameState.deal(rules, seed=seed, debug=True)
        agents = [RandomAgent() for _ in range(6)]
        rng = random.Random(seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, rng.getrandbits(64))
        bel = BeliefState(rules, observer=None)
        while not state.is_terminal:
            actor = state.turn
            obs = Observation.from_state(state, actor)
            bel.update(obs)
            for c in range(54):
                holder = state.holder_of(c)
                if holder is not None:
                    assert bel.current_holder_mask(c) & (1 << holder)
            state.apply(actor, agents[actor].act(obs))


# ---------------------------------------------------------------------------
# Textbook inference scenarios
# ---------------------------------------------------------------------------

def _bel_after(state, observer=None):
    bel = BeliefState(state.rules, observer=observer)
    bel.update(Observation.from_state(
        state, observer if observer is not None else 0))
    return bel


def test_ask_reveals_asker_has_suit_and_lacks_card():
    s = make_state([["2C", "3C"], ["4C"], ["5C"], ["6C"], ["7C"], []], turn=0)
    s.apply(0, Ask(1, cid("6C")))  # P1 doesn't have 6C -> failed
    bel = _bel_after(s)
    m = bel.current_holder_mask(cid("6C"))
    assert not m & 0b000011      # neither P0 (asked) nor P1 (said no)
    assert any(p == 0 for _, p in bel.ors) or any(
        bel.pinned_owner(c) == 0 for c in range(6))


def test_successful_ask_pins_card_publicly():
    s = make_state([["2C", "3C"], ["4C"], ["5C"], ["6C"], ["7C"], []], turn=0)
    s.apply(0, Ask(1, cid("4C")))
    bel = _bel_after(s)
    assert bel.current_holder_mask(cid("4C")) == 1 << 0   # now with P0
    assert bel.pinned_owner(cid("4C")) == 1               # dealt to P1


def test_observer_knows_own_hand():
    rules = RuleConfig()
    s = GameState.deal(rules, seed=21, debug=True)
    bel = _bel_after(s, observer=0)
    for c in range(54):
        if s.hands[0] & (1 << c):
            assert bel.current_holder_mask(c) == 1
        else:
            assert not bel.current_holder_mask(c) & 1


def test_own_hand_is_known_exactly():
    rules = RuleConfig()
    state = GameState.deal(rules, seed=3, debug=True)
    bel = BeliefState(rules, observer=2)
    bel.update(Observation.from_state(state, 2))
    assert bel.known_current_hands()[2] == state.hands[2]


def test_marginals_are_probabilities():
    rules = RuleConfig()
    state = GameState.deal(rules, seed=4, debug=True)
    bel = BeliefState(rules, observer=1)
    bel.update(Observation.from_state(state, 1))
    rng = random.Random(0)
    marg = bel.marginals(rng, n_samples=32)
    for c in range(54):
        row = marg[c]
        assert abs(sum(row) - 1.0) < 1e-9   # every live card is somewhere
        assert row[state.holder_of(c)] > 0  # truth has positive probability
