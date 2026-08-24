"""The vectorised batch sampler must realise the same distribution as the
scalar reference, which is itself validated against exhaustive enumeration.

A fast rewrite of a sampler is exactly the kind of change that produces subtly
wrong probabilities while looking fine, so this compares against the analytic
path density rather than against "it runs".
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# pytest may collect this file with a different sys.path than a direct run, so
# make the sibling module importable either way.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from fish4.sis import SISSampler, sample_batch
from tests4.test_sis import (enumerate_worlds, path_probability,
                             random_system)

NUM_PLAYERS = 6


def test_batch_matches_analytic_density():
    rng = random.Random(31337)
    checked = 0
    worst = 0.0
    for _ in range(500):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (2 <= len(worlds) <= 80):
            continue
        s = SISSampler(free, masks, quotas, ors)
        analytic = [path_probability(s, w) for w in worlds]
        tot = sum(analytic)
        if tot <= 0:
            continue
        batch = sample_batch(s, rng, 20000, vectorised=True)
        if len(batch) < 5000:
            continue
        counts: dict = {}
        for d in batch.deals:
            k = tuple(d[c] for c in free)
            counts[k] = counts.get(k, 0) + 1
        n = len(batch)
        gap = 0.0
        for w, a in zip(worlds, analytic):
            k = tuple(w[c] for c in free)
            gap = max(gap, abs(counts.get(k, 0) / n - a / tot))
        # unseen worlds would be a support failure, which the scalar tests
        # already rule out analytically; here we only need the densities
        assert set(counts).issubset({tuple(w[c] for c in free) for w in worlds}), (
            "batch sampler produced an inconsistent world")
        worst = max(worst, gap)
        assert gap < 0.02, (
            "batch and analytic path densities differ by {0:.4f}; masks={1} "
            "quotas={2} ors={3}".format(gap, masks, quotas, ors))
        checked += 1
        if checked >= 20:
            break
    assert checked >= 10
    print("batch density: {0} systems, worst gap {1:.4f}".format(checked, worst))


def test_batch_and_scalar_agree_on_weighted_marginals():
    rng = random.Random(4)
    checked = 0
    worst = 0.0
    for _ in range(500):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (4 <= len(worlds) <= 20000):
            continue
        s = SISSampler(free, masks, quotas, ors)
        truth = np.zeros((len(free), NUM_PLAYERS))
        for w in worlds:
            for i, c in enumerate(free):
                truth[i, w[c]] += 1
        truth /= len(worlds)
        b = sample_batch(s, rng, 20000, vectorised=True)
        if len(b) < 5000:
            continue
        est = np.zeros((len(free), NUM_PLAYERS))
        for wt, d in zip(b.w, b.deals):
            for i, c in enumerate(free):
                est[i, d[c]] += wt
        err = float(np.abs(est - truth).max())
        worst = max(worst, err)
        assert err < 0.04, (
            "batch weighted marginals off by {0:.4f}; masks={1} quotas={2} "
            "ors={3}".format(err, masks, quotas, ors))
        checked += 1
        if checked >= 15:
            break
    assert checked >= 8
    print("batch marginals: {0} systems, worst error {1:.4f}".format(
        checked, worst))


def test_batch_is_actually_faster():
    """The whole point is speed, so measure it rather than assume it.

    Timed as a benchmark rather than as one sample, because the first version
    was neither and went red on a loaded machine at 1.9x against a 2.0x bar.
    Two things were wrong with it and only one was the machine.

    It timed the FIRST EVER vectorised call, which carries numpy's one-time
    setup: measured over seven repetitions the first takes 10.9 ms and the rest
    take 3.1--3.5 ms, so repetition one scores 0.88x and every other scores
    about 3.1x. A warm-up call is not a concession, it is the difference
    between measuring setup and measuring the thing.

    And it took a single sample of a wall clock on a box that also runs duel
    workers. The minimum over repetitions is the standard estimator there: the
    fastest run is the one least interrupted, so it is the closest to the
    quantity being claimed.

    With both fixed the real speedup is about 3.1x, so the bar goes UP to 2.5x
    rather than down.
    """
    free = list(range(26))
    masks = {c: (0b111110 if c % 3 else 0b011110) for c in free}
    quotas = [0, 6, 5, 5, 5, 5]
    ors = [((0, 1, 2), 1), ((3, 4, 5), 2), ((6, 7, 8, 9), 3)]
    s = SISSampler(free, masks, quotas, ors)

    # Warm-up, untimed: both paths, so neither is charged for its own setup.
    sample_batch(s, random.Random(11), 64, vectorised=False)
    sample_batch(s, random.Random(11), 64, vectorised=True)

    scalar, batch = [], []
    for _ in range(5):
        rng = random.Random(11)
        t0 = time.perf_counter()
        a = sample_batch(s, rng, 256, vectorised=False)
        scalar.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        b = sample_batch(s, rng, 256, vectorised=True)
        batch.append(time.perf_counter() - t0)
    assert len(a) > 200 and len(b) > 200

    t_scalar, t_batch = min(scalar), min(batch)
    speedup = t_scalar / max(t_batch, 1e-9)
    print("256 draws, best of 5: scalar {0:.1f} ms, batch {1:.1f} ms, "
          "speedup {2:.1f}x".format(t_scalar * 1e3, t_batch * 1e3, speedup))
    assert speedup > 2.5, "vectorising bought only {0:.2f}x".format(speedup)


if __name__ == "__main__":
    test_batch_matches_analytic_density()
    test_batch_and_scalar_agree_on_weighted_marginals()
    test_batch_is_actually_faster()
    print("all batch sampler tests passed")
