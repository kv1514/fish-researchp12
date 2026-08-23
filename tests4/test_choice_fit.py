"""The conditional-logit fit, checked against data it cannot cheat on.

``scripts4/choice_curve.py`` claims to measure the exponent in

    P(ask in H) proportional to depth_H ** alpha

from self-play logs, and the whole point of measuring it is that the shipped
value of 1 was assumed rather than established. A fit that cannot recover an
exponent it is shown would be no better than the assumption, so it is shown
several, on synthetic choices generated with the answer known.

The padding matters and is tested separately: real decisions offer between two
and five legal half-suits, and they are packed into one rectangular array with
the unused slots masked to -inf. A masking bug would silently add phantom
alternatives to short choice sets, which biases every fit toward zero without
raising anything.
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

from choice_curve import fit_alpha, propensity                   # noqa: E402


def synth(alpha, n=6000, seed=4, min_alts=2, max_alts=5, max_depth=5):
    rng = np.random.default_rng(seed)
    recs = []
    for _ in range(n):
        m = int(rng.integers(min_alts, max_alts + 1))
        d = rng.integers(1, max_depth + 1, size=m)
        w = d.astype(float) ** alpha
        j = int(rng.choice(m, p=w / w.sum()))
        recs.append({"alts": [{"hs": i, "depth0": int(d[i])} for i in range(m)],
                     "picked": j, "resolved": 0, "n_hs": 9})
    return recs


@pytest.mark.parametrize("truth", [0.0, 1.0, 2.0])
def test_it_recovers_the_exponent_it_was_shown(truth):
    f = fit_alpha(synth(truth))
    assert abs(f["alpha"] - truth) < 4 * f["se"], (
        f"fitted {f['alpha']:+.3f} +/- {f['se']:.3f} for a true {truth}")


def test_it_can_tell_the_shipped_model_from_a_flat_one():
    """If alpha = 1 and alpha = 0 were not separable there is nothing to fit."""
    one = fit_alpha(synth(1.0))
    flat = fit_alpha(synth(0.0))
    assert one["alpha"] - flat["alpha"] > 6 * max(one["se"], flat["se"])
    # and the likelihood prefers the truth in each case
    assert one["nll"] < one["nll_at_0"]
    assert flat["nll"] < flat["nll_at_1"]


def test_uneven_choice_sets_are_not_biased_by_the_padding():
    """Short choice sets are padded to the widest; the mask must hide them.

    A padding slot that leaks in acts as an extra always-available alternative
    of depth 1, which drags every estimate toward zero. Fitting the same true
    exponent on ragged and on fixed-width choice sets must agree.
    """
    ragged = fit_alpha(synth(1.5, min_alts=2, max_alts=5))
    square = fit_alpha(synth(1.5, min_alts=4, max_alts=4))
    gap = abs(ragged["alpha"] - square["alpha"])
    assert gap < 4 * (ragged["se"] ** 2 + square["se"] ** 2) ** 0.5, (
        f"ragged {ragged['alpha']:+.3f} vs fixed-width {square['alpha']:+.3f}")


def test_the_propensity_ratio_is_one_everywhere_under_indifference():
    """O/E is normalised against chance, so a coin-flipper must read flat."""
    curve = propensity(synth(0.0, n=8000), "depth0")
    for v, c in curve.items():
        if c["expected"] < 50:
            continue
        assert abs(c["relative"] - 1.0) < 4 * c["se"], (
            f"depth {v} reads {c['relative']:.3f} under indifference")


def test_the_propensity_ratio_rises_with_depth_when_the_truth_does():
    curve = propensity(synth(1.0, n=8000), "depth0")
    vals = [c["relative"] for v, c in sorted(curve.items())
            if c["expected"] >= 50]
    assert len(vals) >= 3
    assert vals[-1] > vals[0] * 1.5
