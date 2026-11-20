"""The regret estimator, checked on data whose truth is known.

``scripts4/ask_regret.py`` asks how much value the ask objective leaves on the
table, by rolling out every legal ask and comparing the objective's choice
against the best of them. The obvious estimator -- take the maximum -- does not
work, and the reason is the error this project has already made three times: a
maximum over a few dozen noisy estimates sits well above the truth, so a policy
that plays perfectly still measures a large positive regret.

These tests pin that down with synthetic rollouts, where the true values are
whatever the test says they are:

  * when every action is genuinely equal, the honest answer is zero, and the
    naive estimator must be caught reporting substantially more than zero;
  * when one action is genuinely better, the estimator must find it;
  * and the cross-fitted number must never be the larger of the two on average,
    since the whole point of splitting is to give up the inflation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from ask_regret import crossfit_regret                        # noqa: E402

N_ACTIONS = 25
N_WORLDS = 12
NOISE = 3.0
TRIALS = 400


def _synth(rng, true_values, n_worlds=N_WORLDS, noise=NOISE):
    """Per-world scores for each action, around its true value."""
    return {i: true_values[i] + rng.normal(0.0, noise, size=n_worlds)
            for i in range(len(true_values))}


def _run(true_values, trials=TRIALS, seed=20260823):
    rng = np.random.default_rng(seed)
    xf, naive = [], []
    for _ in range(trials):
        per = _synth(rng, true_values)
        _, nv, cf = crossfit_regret(per, 0)      # action 0 is the incumbent
        if cf is not None:
            xf.append(cf)
            naive.append(nv)
    return np.asarray(xf), np.asarray(naive)


def test_all_actions_equal_gives_zero_regret():
    """The estimator's null, and the claim the whole script rests on.

    Measured over five independent runs of 4000 trials the estimate is
    -0.004 with a spread of 0.012, so the tolerance here is set at 0.05 -- tight
    enough to catch a bias a tenth the size of the naive estimator's, loose
    enough not to fire on sampling noise at this trial count.
    """
    xf, _ = _run([0.0] * N_ACTIONS, trials=3000, seed=90210)
    se = xf.std(ddof=1) / np.sqrt(xf.size)
    assert abs(xf.mean()) < 0.05, (
        f"cross-fitted regret {xf.mean():+.4f} +/- {se:.4f} on a true null")


def test_the_naive_estimator_fails_that_null_badly():
    """Which is why the cross-fitting is there at all.

    On the same true null the naive maximum reports about +1.8 sets of regret
    that does not exist -- twice the standard error of a single action's
    estimate, which is exactly what a maximum over 25 of them buys.
    """
    xf, naive = _run([0.0] * N_ACTIONS, trials=3000, seed=90210)
    se = naive.std(ddof=1) / np.sqrt(naive.size)
    assert naive.mean() > 10 * se
    # the inflation should be on the order of a couple of standard errors of a
    # single action's estimate, which is what a max over 25 of them costs
    single_se = NOISE / np.sqrt(N_WORLDS)
    assert naive.mean() > 1.5 * single_se
    assert naive.mean() > xf.mean() + single_se


def test_a_real_edge_is_found():
    true = [0.0] * N_ACTIONS
    true[7] = 2.0                       # one genuinely better ask
    xf, _ = _run(true)
    se = xf.std(ddof=1) / np.sqrt(xf.size)
    assert xf.mean() > 4 * se, f"missed a +2.0 action ({xf.mean():+.3f})"
    # and does not claim more than is there
    assert xf.mean() < 2.0 + 3 * se


def test_the_estimate_is_a_lower_bound_not_an_upper_one():
    true = [0.0] * N_ACTIONS
    true[3] = 1.0
    xf, naive = _run(true)
    assert xf.mean() <= naive.mean()
    assert xf.mean() <= 1.0 + 3 * xf.std(ddof=1) / np.sqrt(xf.size)


def test_an_incumbent_that_is_already_best_measures_no_worse_than_zero():
    true = [0.0] * N_ACTIONS
    true[0] = 1.5                       # the incumbent IS the best action
    xf, _ = _run(true)
    se = xf.std(ddof=1) / np.sqrt(xf.size)
    assert xf.mean() < 3 * se, (
        f"found {xf.mean():+.4f} sets of improvement over the best action")


def test_more_worlds_shrinks_the_naive_bias_and_leaves_the_honest_one_alone():
    """The signature of a bias rather than a signal: it depends on the budget."""
    rng = np.random.default_rng(7)
    out = {}
    for nw in (8, 64):
        xf, naive = [], []
        for _ in range(TRIALS):
            per = _synth(rng, [0.0] * N_ACTIONS, n_worlds=nw)
            _, nv, cf = crossfit_regret(per, 0)
            if cf is not None:
                xf.append(cf)
                naive.append(nv)
        out[nw] = (float(np.mean(xf)), float(np.mean(naive)))
    assert out[64][1] < out[8][1] * 0.6, (
        f"naive bias did not fall with budget: {out}")
    assert abs(out[64][0]) < 0.2 and abs(out[8][0]) < 0.4


def test_too_few_worlds_to_split_declines_rather_than_guesses():
    rng = np.random.default_rng(11)
    per = _synth(rng, [0.0] * 5, n_worlds=2)
    _, naive, cf = crossfit_regret(per, 0)
    assert cf is None and not np.isnan(naive)
