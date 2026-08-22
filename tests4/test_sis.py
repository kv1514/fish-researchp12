"""Correctness of the importance sampler against exhaustive enumeration.

The whole claim of ``fish4/sis.py`` is that its self-normalised weights make it
*consistent* for the uniform distribution over fully-consistent worlds,
including the OR clauses that the exact DP cannot cheaply absorb. That claim is
worth nothing unless it is checked against ground truth, so these tests
enumerate every consistent world on small systems and compare three ways:
support, proposal density, and marginals - plus a control showing that dropping
the weights visibly breaks the estimate, so the other tests are known to be
discriminating rather than vacuous.
"""

from __future__ import annotations

import random
import sys
from itertools import product as iproduct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish4.sis import (SISFailure, SISSampler, sample_batch,
                       weighted_marginals)

NUM_PLAYERS = 6


# ---------------------------------------------------------------------------
# Ground truth by enumeration
# ---------------------------------------------------------------------------

def enumerate_worlds(free, masks, quotas, ors):
    choices = [[p for p in range(NUM_PLAYERS) if masks[c] >> p & 1] for c in free]
    out = []
    for assign in iproduct(*choices):
        cnt = [0] * NUM_PLAYERS
        for p in assign:
            cnt[p] += 1
        if cnt != list(quotas):
            continue
        pos = {c: assign[i] for i, c in enumerate(free)}
        if all(any(pos.get(c) == p for c in cards) for cards, p in ors):
            out.append(pos)
    return out


def truth_marginals(free, worlds):
    marg = np.zeros((len(free), NUM_PLAYERS))
    for w in worlds:
        for i, c in enumerate(free):
            marg[i, w[c]] += 1
    if worlds:
        marg /= len(worlds)
    return marg


def random_system(rng):
    n = rng.randint(4, 8)
    free = list(range(n))
    pool = [rng.randint(1, 63) for _ in range(rng.randint(2, 4))]
    masks = {c: rng.choice(pool) for c in free}
    quotas = [0] * NUM_PLAYERS
    for _ in range(n):
        quotas[rng.randrange(NUM_PLAYERS)] += 1
    ors = []
    for _ in range(rng.randint(0, 3)):
        k = rng.randint(2, min(4, n))
        cards = tuple(rng.sample(free, k))
        p = rng.randrange(NUM_PLAYERS)
        ors.append((cards, p))
    return free, masks, quotas, ors


def path_probability(sampler, world):
    """Probability the sampler's fixed-order path produces exactly ``world``.

    Returns 0.0 if the world is unreachable. This is an ANALYTIC support check:
    random hit-testing cannot tell "unreachable" from "rare", and consistency of
    self-normalised importance sampling depends on the former never happening.
    """
    quota = list(sampler.quotas)
    live_left = [len(live) for live, _ in sampler.ors]
    satisfied = [False] * len(sampler.ors)
    prob = 1.0
    for c in sampler.order:
        truth = world[c]
        clauses = sampler._by_card.get(c, ())
        forced = -1
        for i in clauses:
            if not satisfied[i] and live_left[i] == 1:
                pl = sampler.ors[i][1]
                if forced >= 0 and forced != pl:
                    return 0.0
                forced = pl
        if forced >= 0:
            if forced != truth or quota[forced] <= 0:
                return 0.0
        else:
            total = 0.0
            chosen = 0.0
            for pl in sampler._cand[c]:
                if quota[pl] <= 0:
                    continue
                w = float(quota[pl])
                for i in clauses:
                    if not satisfied[i] and sampler.ors[i][1] == pl:
                        w *= sampler.boost
                        break
                total += w
                if pl == truth:
                    chosen = w
            if chosen <= 0.0 or total <= 0.0:
                return 0.0
            prob *= chosen / total
        quota[truth] -= 1
        for i in clauses:
            live_left[i] -= 1
            if sampler.ors[i][1] == truth:
                satisfied[i] = True
    if any(q != 0 for q in quota) or not all(satisfied):
        return 0.0
    return prob


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sis_support_is_complete():
    """Every consistent world must have strictly positive proposal density."""
    rng = random.Random(99)
    tested = 0
    total_worlds = 0
    for _ in range(500):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (2 <= len(worlds) <= 400):
            continue
        sampler = SISSampler(free, masks, quotas, ors)
        for w in worlds:
            assert path_probability(sampler, w) > 0.0, (
                "world {0} is unreachable; masks={1} quotas={2} ors={3}".format(
                    [w[c] for c in free], masks, quotas, ors))
        total_worlds += len(worlds)
        tested += 1
        if tested >= 120:
            break
    assert tested >= 50, "only {0} systems exercised".format(tested)
    print("support: {0} systems, {1} worlds, all reachable".format(
        tested, total_worlds))


def test_proposal_density_is_what_the_weights_assume():
    """Analytic and empirical proposal densities must agree.

    This is where an importance sampler silently goes wrong: if the density used
    to build the weights is not the density the sampler actually realises, the
    estimator is biased in a way no amount of sampling fixes.
    """
    rng = random.Random(1234)
    checked = 0
    worst_overall = 0.0
    for _ in range(500):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (2 <= len(worlds) <= 120):
            continue
        sampler = SISSampler(free, masks, quotas, ors)
        analytic = [path_probability(sampler, w) for w in worlds]
        total = sum(analytic)
        assert 0.0 < total <= 1.0 + 1e-9, "densities sum to {0}".format(total)
        counts: dict = {}
        got = 0
        for _ in range(8000):
            try:
                deal, _, _ = sampler.draw(rng)
            except SISFailure:
                continue
            got += 1
            key = tuple(deal[c] for c in free)
            counts[key] = counts.get(key, 0) + 1
        worst = 0.0
        for w, a in zip(worlds, analytic):
            key = tuple(w[c] for c in free)
            worst = max(worst, abs(counts.get(key, 0) / max(1, got) - a / total))
        worst_overall = max(worst_overall, worst)
        assert worst < 0.03, (
            "empirical and analytic path densities differ by {0:.4f}; the "
            "importance weights would be wrong. masks={1} quotas={2} ors={3}"
            .format(worst, masks, quotas, ors))
        checked += 1
        if checked >= 20:
            break
    assert checked >= 10
    print("density: {0} systems agree, worst gap {1:.4f}".format(
        checked, worst_overall))


def test_weighted_marginals_match_enumeration():
    rng = random.Random(20260821)
    checked = 0
    worst = 0.0
    for _ in range(900):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (4 <= len(worlds) <= 40000):
            continue
        truth = truth_marginals(free, worlds)
        sampler = SISSampler(free, masks, quotas, ors)
        batch = sample_batch(sampler, rng, 4000)
        if len(batch) < 2000:
            continue
        est = weighted_marginals(batch, free, len(free))
        err = float(np.abs(est[:len(free)] - truth).max())
        worst = max(worst, err)
        checked += 1
        assert err < 0.06, (
            "SIS marginal off by {0:.4f} on a system with {1} worlds; "
            "masks={2} quotas={3} ors={4}".format(
                err, len(worlds), masks, quotas, ors))
    assert checked >= 30, "only {0} systems exercised".format(checked)
    print("marginals: {0} systems, worst error {1:.4f}".format(checked, worst))


def test_unweighted_marginals_would_be_biased():
    """Control: dropping the weights must visibly break the estimate.

    Without this, a suite that only checks the weighted estimator cannot tell a
    correct weighting from a proposal that happened to be uniform anyway.
    """
    rng = random.Random(7)
    biased_seen = 0
    tried = 0
    for _ in range(900):
        free, masks, quotas, ors = random_system(rng)
        if not ors:
            continue
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if not (6 <= len(worlds) <= 40000):
            continue
        truth = truth_marginals(free, worlds)
        sampler = SISSampler(free, masks, quotas, ors)
        batch = sample_batch(sampler, rng, 4000)
        if len(batch) < 2000:
            continue
        tried += 1
        flat = np.zeros((len(free), NUM_PLAYERS))
        for deal in batch.deals:
            for i, c in enumerate(free):
                flat[i, deal[c]] += 1
        flat /= len(batch)
        if float(np.abs(flat - truth).max()) > 0.06:
            biased_seen += 1
        if biased_seen >= 5:
            break
    assert biased_seen >= 5, (
        "the unweighted estimator showed bias on only {0} of {1} systems, so "
        "the weighted test is not discriminating".format(biased_seen, tried))
    print("control: unweighted estimator is measurably biased, as expected")


def test_effective_sample_size_is_usable():
    rng = random.Random(5)
    ratios = []
    for _ in range(300):
        free, masks, quotas, ors = random_system(rng)
        worlds = enumerate_worlds(free, masks, quotas, ors)
        if len(worlds) < 8:
            continue
        sampler = SISSampler(free, masks, quotas, ors)
        batch = sample_batch(sampler, rng, 500)
        if len(batch) < 250:
            continue
        ratios.append(batch.ess / len(batch))
        if len(ratios) >= 60:
            break
    assert ratios, "no systems exercised"
    mean_ratio = sum(ratios) / len(ratios)
    print("ESS/N over {0} systems: mean {1:.3f}, min {2:.3f}".format(
        len(ratios), mean_ratio, min(ratios)))
    assert mean_ratio > 0.35, "effective sample size collapsed: {0:.3f}".format(
        mean_ratio)


if __name__ == "__main__":
    test_sis_support_is_complete()
    test_proposal_density_is_what_the_weights_assume()
    test_weighted_marginals_match_enumeration()
    test_unweighted_marginals_would_be_biased()
    test_effective_sample_size_is_usable()
    print("all sis tests passed")
