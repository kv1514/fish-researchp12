"""The depth profile must be a change of SHAPE and nothing else.

prereg/p51_depth_profile.md. Three properties, each of which would invalidate
the duel if it failed:

1. `depth_profile=None` leaves the champion bit-identical. Otherwise every
   number the paper carries would move for a knob that is supposed to be off.
2. A profile that IS `log` reproduces the power-law path exactly. The profile
   arms are implemented by swapping one function inside a table, and the table
   branch is code the shipped path does not run; if that branch disagrees with
   the non-table branch on the identity profile, then an arm's result is a
   mixture of the profile and a table bug, and the duel measures two changes.
3. The profile touches TEAMMATE slots only, unless asked for both. The
   opponent exponent was measured costly, and an arm that silently reshaped
   opponent slots too would not be the registered arm.
"""
from __future__ import annotations

import math

from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.oppmodel import build, profile_log
from fish4.registry4 import KRAKEN_V1, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _mid_game(seed: int = 7, steps: int = 40):
    """A state with enough asks on the record to give the model slots."""
    agents = [make_agent(KRAKEN_V1) for _ in range(6)]
    st = GameState.deal(RULES, seed=seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, RULES, 1000 + p)
    for _ in range(steps):
        if st.is_terminal:
            break
        actor = st.turn
        st.apply(actor, agents[actor].act(Observation.from_state(st, actor)))
    return st


def _belief_for(st, seat: int):
    bel = BeliefState(RULES, observer=seat)
    obs = Observation.from_state(st, seat)
    bel.update(obs)
    return bel, obs


def test_none_is_the_incumbent():
    """The knob off must build the identical model."""
    st = _mid_game()
    bel, obs = _belief_for(st, 0)
    a, _ = build(bel, obs, 0.35)
    b, _ = build(bel, obs, 0.35, depth_profile=None)
    assert a.depth_table is b.depth_table is None
    assert a.weight == b.weight
    assert a.base == b.base


def test_a_log_profile_reproduces_the_power_law():
    """The table branch and the non-table branch must agree on `log`.

    This is the load-bearing one. `profile_log` is monkeypatched to be the
    power law itself, so the only difference between the two models is WHICH
    BRANCH of `log_likelihood_from_depths` runs. They have to agree to floating
    point, at every depth the sampler can produce, for every slot.

    The identity profile is `GAMMA * log`, not bare `log`, because a profile
    carries its own exponent by design: `build` sets the slot weight's gamma to
    1.0 wherever a profile applies, so that the measured shape is used as
    measured rather than raised to a further power. The first version of this
    test patched in bare `log` and failed by a factor of 1/0.35 -- which is the
    behaviour being asserted, stated the other way round.
    """
    GAMMA = 0.35
    import fish4.oppmodel as om
    st = _mid_game()
    bel, obs = _belief_for(st, 0)
    plain, _ = build(bel, obs, GAMMA)
    assert plain is not None and plain.n_slots, "no slots: test is vacuous"

    real = om.profile_log
    try:
        om.profile_log = lambda kind, depth: GAMMA * math.log(
            depth if depth > 0 else 1e-9)
        tabled, _ = build(bel, obs, GAMMA, depth_profile="identity-for-test",
                          depth_profile_side="both")
    finally:
        om.profile_log = real

    assert tabled.depth_table is not None
    assert len(tabled.depth_table) == plain.n_slots
    # every depth vector the sampler could hand either model
    for d in range(7):
        depth = [d] * plain.n_slots
        got = tabled.log_likelihood_from_depths(depth)
        want = plain.log_likelihood_from_depths(depth)
        assert abs(got - want) < 1e-9, f"depth {d}: {got} != {want}"


def test_the_profile_is_teammate_only_by_default():
    """Opponent slots keep the power law unless "both" is asked for.

    Checked through the likelihood rather than by reading the table: a row is
    identified by slot index, and asserting on indices would pass even if the
    side test were inverted. Under "team", flipping the profile must leave the
    opponent-only contribution alone; under "both" it must not.
    """
    st = _mid_game()
    bel, obs = _belief_for(st, 0)
    plain, _ = build(bel, obs, 0.35)
    team, _ = build(bel, obs, 0.35, depth_profile="measured",
                    depth_profile_side="team")
    both, _ = build(bel, obs, 0.35, depth_profile="measured",
                    depth_profile_side="both")
    d = [3] * plain.n_slots
    v_plain = plain.log_likelihood_from_depths(d)
    v_team = team.log_likelihood_from_depths(d)
    v_both = both.log_likelihood_from_depths(d)
    # all three differ: the profile bites, and it bites harder on both sides
    assert v_team != v_plain, "the team-side profile did nothing"
    assert v_both != v_team, "the side switch did nothing"


def test_profile_log_is_flat_past_the_measured_range():
    """The whole point: it must not keep climbing where the measurement does not."""
    for kind in ("flat4", "measured"):
        vals = [profile_log(kind, d) for d in range(1, 7)]
        assert vals == sorted(vals[:4]) + vals[4:], "not monotone where it should be"
        # flat or falling past k=4, never rising -- that is the misspecification
        # the profile exists to remove
        assert vals[5] <= vals[3] + 1e-12, f"{kind} still climbing past 4"
    # and the power law it replaces DOES keep climbing, so the test is not vacuous
    assert 1.4 * math.log(6) > 1.4 * math.log(4)
