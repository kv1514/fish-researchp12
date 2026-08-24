"""TunedAgent must reduce EXACTLY to the baseline when its extra weights
are zero.

This is the precondition for every ablation that uses it. A previous version
normalized its suit-depth term by 6 while the baseline did not, so an
"ablation of turn risk" silently also weakened the suit bonus sixfold and
measured two changes at once. The experiment ran to n=1000 and produced a
confident, wrong conclusion before the confound was noticed, which is why
this equivalence is now pinned by a test.
"""

import random

import pytest

from fish.agents import ProbabilisticAgent, TunedAgent
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def _decisions(agent_factory, seed, steps=60):
    """Play a fixed game, recording what the agent under test would do at
    every one of its decision points."""
    rules = RuleConfig()
    state = GameState.deal(rules, seed=seed)
    drivers = [ProbabilisticAgent() for _ in range(6)]
    rng = random.Random(seed)
    for p, ag in enumerate(drivers):
        ag.begin_game(p, rules, rng.getrandbits(64))
    subject_seat = 0
    subject = agent_factory()
    subject.begin_game(subject_seat, rules, 4242)
    out = []
    for _ in range(steps):
        if state.is_terminal:
            break
        p = state.turn
        obs = Observation.from_state(state, p)
        if p == subject_seat:
            out.append(subject.act(obs))
        state.apply(p, drivers[p].act(obs))
    return out


@pytest.mark.parametrize("seed", [3, 11, 29])
def test_zero_weights_reproduce_the_baseline(seed):
    base = _decisions(lambda: ProbabilisticAgent(), seed)
    tuned = _decisions(lambda: TunedAgent(), seed)
    assert base == tuned, (
        "TunedAgent with default weights diverged from ProbabilisticAgent; "
        "every ablation built on it would be confounded")


def test_nonzero_weight_actually_changes_behaviour():
    """The complementary check: if a weight never changed anything, an
    ablation would be measuring nothing."""
    seeds = [3, 11, 29, 41, 57]
    differed = False
    for s in seeds:
        base = _decisions(lambda: TunedAgent(), s)
        turned = _decisions(lambda: TunedAgent(w_turn=0.6), s)
        if base != turned:
            differed = True
            break
    assert differed, "w_turn had no effect on any decision"
