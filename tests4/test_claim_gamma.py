"""A different action model for the declaration than for the ask.

WHY THIS PARAMETER EXISTS
-------------------------
results/split_why.json, 1,619 frozen (decision, half-suit) pairs re-scored on
the SAME belief through FishBot4.build_posterior: the engine's
P(split right | ours) is under-confident by 0.219 in the half-suits our team
owns outright -- the population every allocation error comes from -- and that
bias is FLAT in the draw count and MONOTONE in gamma. It is the action model.

Raising gamma globally is already refuted (prereg/gamma_split.md, teammate
top-1). The reason the two can differ is that the decisions are scored
differently: an ask reads the argmax, a declaration is compared against 0.97.

Everything here runs at claim_gamma = 0.0 in the shipped configuration, and the
first test asserts the champion is bit-identical there.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _play(seed, extra, limit=500):
    agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1], **extra)))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 5_500 + seed * 13 + p)
    moves = []
    for _ in range(limit):
        if st.is_terminal:
            break
        act = agents[st.turn].act(Observation.from_state(st, st.turn))
        moves.append((st.turn, repr(act)))
        st.apply(st.turn, act)
    return (moves, list(st.set_winner)), agents


def test_the_champion_is_bit_identical_at_zero():
    assert V06_DEPLOYED[1].get("claim_gamma", 0.0) == 0.0
    for seed in (5_201, 5_202):
        a, ag_a = _play(seed, {})
        b, ag_b = _play(seed, {"claim_gamma": 0.0})
        assert a == b
        assert len(a[0]) > 20
        assert sum(x.claim_posteriors for x in ag_a) == 0
        assert sum(x.claim_posteriors for x in ag_b) == 0, (
            "a zero weight must not pay for a posterior it will not read")


def test_it_changes_play_above_zero():
    seen = []
    for seed in (5_201, 5_202):
        base, _ = _play(seed, {})
        live, agents = _play(seed, {"claim_gamma": 1.4})
        seen.append(base != live)
        assert sum(a.claim_posteriors for a in agents) > 0
    assert any(seen), "the parameter is inert at a weight where it must not be"


def test_the_cost_gate_skips_most_decisions():
    """A second posterior at every decision would double inference.

    It is built only when `p_team_all` says something is near ClaimEvaluator's
    own screen, because below that tier 3 never runs and the posterior would be
    discarded unread. This asserts the gate actually bites -- if it ever stops
    biting, the parameter has quietly become a 2x cost rather than a targeted
    one.
    """
    (moves, _), agents = _play(5_203, {"claim_gamma": 0.7})
    built = sum(a.claim_posteriors for a in agents)
    assert 0 < built < len(moves), (
        f"{built} extra posteriors over {len(moves)} decisions: the gate is "
        f"either dead or not gating")


def test_build_posterior_gamma_override_is_the_only_difference():
    """The instrument's contract: two calls differ by the named argument.

    scripts4/split_why.py's whole conclusion rests on this -- if the override
    silently did nothing, a flat-in-gamma result would have been read as
    'not the action model' when it meant 'the knob is broken'. That is exactly
    the failure this project has hit twice with dead code paths.
    """
    agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=5_204)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 4_242 + p)
    for _ in range(14):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    bot = agents[0]
    obs = Observation.from_state(st, 0)
    bot.bel.update(obs)
    lo = bot.build_posterior(obs, gamma=0.0).marginals()
    hi = bot.build_posterior(obs, gamma=2.0).marginals()
    assert not (lo == hi).all(), "the gamma override changed nothing"


def test_gamma_none_reproduces_the_configured_weight():
    agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=5_205)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 909 + p)
    bot = agents[0]
    obs = Observation.from_state(st, 0)
    bot.bel.update(obs)
    a = bot.build_posterior(obs)
    b = bot.build_posterior(obs, gamma=None)
    assert a.gamma == b.gamma == pytest.approx(bot.opponent_gamma)
