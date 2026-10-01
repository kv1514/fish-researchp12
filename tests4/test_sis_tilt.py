"""The twisted proposal, and why it is off by default.

The sampler's proposal is quota-proportional and knows nothing about the
opponent choice model, so at ``gamma > 0`` the whole tilt of the target lands in
the importance weights. Measured on real positions, 160 draws are worth 99.9
effective samples at ``gamma = 0`` but only 83.7 at ``gamma = 0.35``.

Folding one step of the likelihood into the proposal is the textbook remedy and
it does exactly what the textbook says to the diagnostic: effective sample size
rises from 83.7 to 105.8, past even the untilted ``gamma = 0`` figure.

It also makes the estimate 3.4x worse.

That is the whole point of these tests. Kish ESS measures how *flat* the
importance weights are, and a proposal that covers part of the target very well
and the rest not at all has beautifully flat weights over the part it covers.
The one-step twist overshoots because the likelihood's depth-0 term is a
numerical floor of ``log(1e-9)``: the 0 -> 1 ratio is astronomical, so the
proposal treats "this slot is empty right now" as "this slot will end empty" and
drives nearly every draw into the same corner.

So ``sis_tilt`` stays in the tree at a default of 0, where it is bit-identical
to the untwisted sampler, and these tests pin the negative result in place so
that the next person to notice the ESS gap does not have to rediscover it.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                        # noqa: E402
from fish.observation import Observation                     # noqa: E402
from fish4.posterior import Posterior                        # noqa: E402
from fish4.registry4 import make_agent                       # noqa: E402
from fish4.sis import OpponentModel                          # noqa: E402

from tests4.test_leakage4 import collect_positions           # noqa: E402

GAMMA = 0.35
BASE = {"opponent_gamma": GAMMA}


def _obs_bel(pos):
    rules, hands, sw, turn, hist, seat = pos
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    return obs, bel


def _marginals(pos, tilt, seed, n_draws=160):
    obs, bel = _obs_bel(pos)
    post = Posterior(bel, random.Random(seed), n_draws=n_draws,
                     obs=obs, gamma=GAMMA, sis_tilt=tilt)
    return np.asarray(post.marginals(), dtype=np.float64)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

def test_zero_strength_builds_no_table_at_all():
    """Not a table of ones: the sampler must not even look."""
    om = OpponentModel([1.0, 0.5], [0, 2], tilt_strength=0.0)
    assert om.tilt is None


def test_a_zero_weight_slot_gets_no_row():
    om = OpponentModel([0.0, 0.5], [1, 1], tilt_strength=1.0)
    assert om.tilt[0] is None and om.tilt[1] is not None


def test_the_factor_decays_with_depth():
    """log is concave, so each extra card of a half-suit is worth less."""
    om = OpponentModel([1.0], [1], tilt_strength=1.0)
    row = om.tilt[0]
    assert all(a >= b for a, b in zip(row, row[1:]))


def test_the_empty_slot_spike_is_capped():
    """Uncapped it is 1e9**w, which would make the step deterministic."""
    om = OpponentModel([2.0], [0], tilt_strength=1.0)
    assert om.tilt[0][0] == pytest.approx(OpponentModel.TILT_CAP)
    assert all(f <= OpponentModel.TILT_CAP for f in om.tilt[0])


def test_strength_interpolates_the_exponent():
    full = OpponentModel([1.0], [2], tilt_strength=1.0).tilt[0]
    half = OpponentModel([1.0], [2], tilt_strength=0.5).tilt[0]
    assert half[1] == pytest.approx(full[1] ** 0.5)


# ---------------------------------------------------------------------------
# The default path
# ---------------------------------------------------------------------------

def test_the_default_is_off():
    from fish4.agent4 import FishBot4
    import inspect
    assert inspect.signature(FishBot4).parameters["sis_tilt"].default == 0.0


def test_zero_tilt_reproduces_the_baseline_decision_for_decision():
    for pos in collect_positions(3, 3, 18):
        rules, hands, sw, turn, hist, seat = pos
        obs, _ = _obs_bel(pos)
        acts = []
        for spec in (BASE, dict(BASE, sis_tilt=0.0)):
            a = make_agent(("fishbot4", spec))
            a.begin_game(seat, rules, 4242)
            acts.append(a.act(obs))
        assert acts[0] == acts[1]


def test_a_nonzero_tilt_actually_reaches_the_sampler():
    """Otherwise the negative result below would be a test of nothing."""
    differed = 0
    for i, pos in enumerate(collect_positions(4, 2, 12)):
        a = _marginals(pos, 0.0, 771 + i)
        b = _marginals(pos, 1.0, 771 + i)
        if not np.array_equal(a, b):
            differed += 1
    assert differed > 0


# ---------------------------------------------------------------------------
# The negative result, pinned
# ---------------------------------------------------------------------------

def test_the_twist_flattens_the_weights():
    """ESS is the metric that says the twist works. It says so here too."""
    ess = {}
    for tilt in (0.0, 1.0):
        vals = []
        for i, pos in enumerate(collect_positions(4, 2, 10)):
            obs, bel = _obs_bel(pos)
            post = Posterior(bel, random.Random(313 + i), n_draws=160,
                             obs=obs, gamma=GAMMA, sis_tilt=tilt)
            post.marginals()
            b = post._batch
            if b is not None and b.n:
                vals.append(b.ess)
        ess[tilt] = float(np.mean(vals))
    assert ess[1.0] > ess[0.0], (
        f"the twist no longer raises ESS ({ess}); if the sampler changed, the "
        "accuracy guard below is measuring something else now")


def test_and_makes_the_estimate_worse_anyway():
    """The reason ``sis_tilt`` defaults to 0 despite the ESS gain.

    The reference is deliberately untilted and large: the incumbent sampler is
    validated against exhaustive enumeration elsewhere, so at high n it is the
    truth to compare against. A tilted reference would compare each setting
    against itself.
    """
    positions = collect_positions(4, 2, 6)
    err = {0.0: [], 1.0: []}
    for i, pos in enumerate(positions):
        ref = _marginals(pos, 0.0, 990000 + i, n_draws=4000)
        for tilt in err:
            for rep in range(3):
                M = _marginals(pos, tilt, 400 + 61 * rep + 7919 * i)
                err[tilt].append(float(np.abs(M - ref).sum() / M.shape[0]))
    mean = {t: float(np.mean(v)) for t, v in err.items()}
    assert mean[1.0] > mean[0.0], (
        f"the twist no longer hurts accuracy ({mean}); if that is a real fix "
        "rather than a reference artefact, re-run scripts4/tilt_accuracy.py "
        "and change the default deliberately")
