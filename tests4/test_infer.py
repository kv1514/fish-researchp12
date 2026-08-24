"""Correctness tests for the fish4 inference backends.

Every claim here is checked against **full enumeration of the consistent set**,
ORs included, on synthetic belief states small enough to enumerate. That is the
only reference that does not share code with the thing being tested: the
enumerator in ``FreeSystem.enumerate_worlds`` is a plain depth-first search over
per-card owners with a quota check and an OR check, structurally unrelated to
the DP, the rejection sampler and the Markov chain.

Statistical tests state the tolerance they use and where it comes from. The
sampling backends cannot be asserted exact, so each is asserted (a) within a
tolerance derived from its own Monte Carlo error and (b) *improving* when its
knob is turned up -- an unbiased estimator has to do both, a biased one fails
the second even when it passes the first at small sample sizes.

Runtime target: under 2 minutes. Note this machine is slow (a bare Python loop
iteration measures 324 ns), so the sample counts below are modest.
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

from fish.beliefs import RESOLVED, BeliefState
from fish.cards import NUM_PLAYERS, cards_per_player, deck_size, half_suit_cards
from fish.rules import RuleConfig
from fish4.counting import GroupSystem, brute_force, group_cards
from fish4.infer import (ExactOrBackend, FreeSystem, FastGroupSystem,
                         MCMCBackend, UniformRejectBackend, V03Backend,
                         restore_belief, snapshot_belief)
from fish4.infer.mcmc import autocorrelation, chain_coverage, integrated_act


# ---------------------------------------------------------------------------
# synthetic belief states
# ---------------------------------------------------------------------------

def build_belief(free_masks, quotas, ors=(), variant="54", free_cards=None,
                 resolved_half_suit=None):
    """A propagated-looking BeliefState with exactly the given free structure.

    ``free_masks[i]`` is the candidate mask of free card i, ``quotas[p]`` how
    many free cards player p was dealt, ``ors`` a list of ``(free indices,
    player)``. Every other card is pinned so the per-player deal size comes out
    right. Returns None if the request is inconsistent.
    """
    n = deck_size(variant)
    per = cards_per_player(variant)
    n_free = len(free_masks)
    if sum(quotas) != n_free:
        return None
    need = [per - q for q in quotas]
    if min(need) < 0:
        return None
    if free_cards is None:
        free_cards = list(range(n_free))
    freeset = set(free_cards)
    bel = BeliefState(RuleConfig(variant=variant), observer=None)
    cand = [0] * n
    rest = [c for c in range(n) if c not in freeset]
    i = 0
    for p in range(NUM_PLAYERS):
        for _ in range(need[p]):
            cand[rest[i]] = 1 << p
            i += 1
    for j, c in enumerate(free_cards):
        cand[c] = free_masks[j]
    bel.candidates = cand
    bel.public_loc = [None] * n
    if resolved_half_suit is not None:
        for c in half_suit_cards(resolved_half_suit):
            if c in freeset:
                return None
            bel.public_loc[c] = RESOLVED
    bel.ors = [(tuple(free_cards[i] for i in live), p) for live, p in ors]
    bel._observer_initialized = True
    bel._version += 1
    return bel


def random_belief(rng, n_free=None, n_ors=None):
    n_free = n_free if n_free is not None else rng.randint(3, 6)
    n_ors = n_ors if n_ors is not None else rng.randint(0, 2)
    masks = []
    for _ in range(n_free):
        while True:
            m = rng.randrange(1, 64)
            if m & (m - 1):
                break
        masks.append(m)
    quotas = [0] * NUM_PLAYERS
    for _ in range(n_free):
        quotas[rng.randrange(NUM_PLAYERS)] += 1
    ors = []
    for _ in range(n_ors):
        p = rng.randrange(NUM_PLAYERS)
        pool = [i for i in range(n_free) if masks[i] >> p & 1]
        if len(pool) < 2:
            continue
        k = rng.randint(2, min(4, len(pool)))
        ors.append((tuple(sorted(rng.sample(pool, k))), p))
    return build_belief(masks, quotas, ors)


def _systems(n, seed=17, require_ors=False, **kw):
    """Feasible synthetic systems with their enumerated truth."""
    rng = random.Random(seed)
    out = []
    guard = 0
    while len(out) < n and guard < 200 * n:
        guard += 1
        bel = random_belief(rng, **kw)
        if bel is None:
            continue
        fs = FreeSystem(bel)
        if not fs.feasible or fs.n_free == 0:
            continue
        if require_ors and not fs.ors:
            continue
        worlds = fs.enumerate_worlds()
        if len(worlds) < 2:
            continue
        if require_ors:
            # an OR that excludes nothing is not an OR-active position
            free_fs = FreeSystem(bel)
            free_fs.ors = []
            if len(free_fs.enumerate_worlds()) == len(worlds):
                continue
        out.append((bel, fs, worlds, fs.brute_force_marginals()))
    return out


SYSTEMS = _systems(24)
# Positions where the ORs actually bind. Kept separate because on an OR-free
# position every sampling backend short-circuits to the exact closed form, so
# convergence tests run there measure nothing.
OR_SYSTEMS = _systems(10, seed=31, require_ors=True, n_ors=2)


def test_enumerator_and_systems_are_sane():
    assert len(SYSTEMS) == 24
    assert len(OR_SYSTEMS) == 10
    assert all(fs.ors for _b, fs, _w, _t in OR_SYSTEMS)
    for bel, fs, worlds, truth in SYSTEMS:
        assert all(fs.valid_world(w) for w in worlds)
        assert len(set(worlds)) == len(worlds)
        assert np.allclose(truth.sum(axis=1), 1.0)


# ---------------------------------------------------------------------------
# backend C: exact
# ---------------------------------------------------------------------------

def test_exact_or_is_exact():
    """No tolerance: this backend either equals the enumeration or is wrong."""
    for bel, fs, worlds, truth in SYSTEMS:
        eo = ExactOrBackend(bel, random.Random(1), work_budget=10 ** 12)
        assert eo.ok, eo.reason
        assert np.abs(eo.free_marginals() - truth).max() < 1e-12
        assert abs(eo.Z - len(worlds)) < 1e-6 * max(1.0, len(worlds))


def test_exact_or_refuses_over_budget_instead_of_lying():
    bel, fs, worlds, truth = SYSTEMS[0]
    eo = ExactOrBackend(bel, random.Random(1), work_budget=1)
    assert not eo.ok
    assert "budget" in eo.reason
    with pytest.raises(RuntimeError):
        eo.free_marginals()


def test_exact_or_handles_no_free_cards():
    quotas = [0] * NUM_PLAYERS
    bel = build_belief([], quotas)
    eo = ExactOrBackend(bel, random.Random(1))
    assert eo.ok
    assert eo.free_marginals().shape == (0, NUM_PLAYERS)
    w = eo.worlds(3)
    assert len(w) == 3


# ---------------------------------------------------------------------------
# backend B: exactly-uniform draws with OR rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cv", [True, False])
def test_uniform_reject_converges(cv):
    """Tolerance: 4000 accepted draws give a per-entry standard error of at
    most 0.5/sqrt(4000) = 0.0079; 0.05 is over six of those, and the measured
    maximum across these systems is 0.014."""
    worst = 0.0
    for bel, fs, worlds, truth in SYSTEMS + OR_SYSTEMS:
        ur = UniformRejectBackend(bel, random.Random(2), n_accepted=4000,
                                  max_draw_factor=400, control_variate=cv)
        worst = max(worst, float(np.abs(ur.free_marginals() - truth).max()))
    assert worst < 0.05, worst


def test_uniform_reject_error_falls_with_more_draws():
    """An unbiased estimator has to improve; a biased one plateaus."""
    small, big = [], []
    for bel, fs, worlds, truth in OR_SYSTEMS:
        for n, bucket in ((32, small), (4096, big)):
            ur = UniformRejectBackend(bel, random.Random(5), n_accepted=n,
                                      max_draw_factor=400)
            bucket.append(float(np.abs(ur.free_marginals() - truth)
                                .sum(axis=1).mean()))
    assert np.mean(big) < 0.5 * np.mean(small), (np.mean(small), np.mean(big))


def test_uniform_reject_is_exact_without_ors():
    """With no live OR the closed form IS the posterior, so no sampling noise
    is acceptable here at all."""
    rng = random.Random(3)
    n = 0
    for _ in range(200):
        bel = random_belief(rng, n_ors=0)
        if bel is None:
            continue
        fs = FreeSystem(bel)
        if not fs.feasible or fs.n_free == 0 or not fs.enumerate_worlds():
            continue
        truth = fs.brute_force_marginals()
        ur = UniformRejectBackend(bel, random.Random(4), n_accepted=8)
        assert np.abs(ur.free_marginals() - truth).max() < 1e-9
        assert ur.exact
        n += 1
        if n >= 12:
            break
    assert n >= 12


def test_closed_form_agrees_with_counting_expected_counts():
    """The control variate is computed by the flat DP, not by
    ``counting.expected_counts``, because the DP is 12x cheaper. They must give
    the same numbers to floating-point identity, or the control variate is
    silently biased."""
    from fish4.infer.uniform_reject import closed_form_marginals
    for bel, fs, worlds, truth in SYSTEMS[:10] + OR_SYSTEMS[:6]:
        E = GroupSystem(fs.masks, fs.sizes, fs.quotas).expected_counts()
        ref = np.zeros((fs.n_free, NUM_PLAYERS))
        for i in range(fs.n_free):
            g = fs.group_of[i]
            ref[i] = E[g] / fs.sizes[g]
        assert np.abs(closed_form_marginals(fs) - ref).max() < 1e-12


# ---------------------------------------------------------------------------
# backend D: MCMC
# ---------------------------------------------------------------------------

def test_mcmc_converges():
    """Tolerance: with 4000 sweeps the measured maximum error across these
    systems is 0.086; 0.20 leaves headroom for chain-to-chain variation without
    admitting a biased sampler (v0.3 reaches 0.27 on the same systems)."""
    worst = 0.0
    for bel, fs, worlds, truth in SYSTEMS + OR_SYSTEMS:
        mc = MCMCBackend(bel, random.Random(3), n_sweeps=4000, burn_sweeps=100)
        worst = max(worst, float(np.abs(mc.free_marginals() - truth).max()))
    assert worst < 0.20, worst


def test_mcmc_error_falls_with_more_sweeps():
    short, long = [], []
    for bel, fs, worlds, truth in SYSTEMS[:6] + OR_SYSTEMS[:6]:
        for n, bucket in ((200, short), (20000, long)):
            mc = MCMCBackend(bel, random.Random(7), n_sweeps=n,
                             burn_sweeps=max(2, n // 10))
            bucket.append(float(np.abs(mc.free_marginals() - truth)
                                .sum(axis=1).mean()))
    assert np.mean(long) < 0.5 * np.mean(short), (np.mean(short), np.mean(long))


def test_two_swaps_alone_are_reducible():
    """The smallest counterexample, and the reason 3-cycles exist.

    Cards with candidate masks {0,1}, {1,2}, {0,2} and one card each for
    players 0, 1, 2. The consistent worlds are (0,1,2) and (1,2,0), and no
    single 2-swap turns one into the other: every exchange is blocked by a
    candidate mask. A 3-cycle does it in one move.
    """
    bel = build_belief([0b000011, 0b000110, 0b000101], [1, 1, 1, 0, 0, 0])
    fs = FreeSystem(bel)
    worlds = set(fs.enumerate_worlds())
    assert worlds == {(0, 1, 2), (1, 2, 0)}
    seen2, _ = chain_coverage(fs, random.Random(1), 3000, p_three=0.0)
    assert len(seen2) == 1, "2-swaps unexpectedly connected this space"
    seen3, _ = chain_coverage(fs, random.Random(1), 3000, p_three=0.5)
    assert seen3 == worlds


def test_three_cycles_reach_every_world():
    """Empirical irreducibility check on random small systems, against full
    enumeration -- not an argument, a measurement."""
    incomplete_2 = 0
    for bel, fs, worlds, truth in SYSTEMS + OR_SYSTEMS:
        W = set(worlds)
        steps = max(4000, 80 * len(W))
        seen2, _ = chain_coverage(fs, random.Random(5), steps, p_three=0.0)
        seen3, _ = chain_coverage(fs, random.Random(5), steps, p_three=0.5)
        assert seen3 == W, (len(seen3), len(W), fs.ors)
        if seen2 != W:
            incomplete_2 += 1
    # 2-swaps alone are demonstrably not enough on this sample
    assert incomplete_2 > 0


def test_autocorrelation_helpers():
    rho = autocorrelation(np.array([1.0, 0.0] * 64), 4)
    assert abs(rho[0] - 1.0) < 1e-12
    assert rho[1] < 0
    assert integrated_act(np.array([1.0, 0.5, 0.25, -0.1])) == pytest.approx(
        1.0 + 2 * 0.5 + 2 * 0.25)


# ---------------------------------------------------------------------------
# backend A: the incumbent, and its measured bias
# ---------------------------------------------------------------------------

def test_v03_worlds_are_valid_but_marginals_are_biased():
    """A clean negative result, kept as a test so it cannot quietly change.

    v0.3's sampler satisfies every constraint -- that is asserted here -- but
    it is not uniform, so its marginals do not converge to the truth. 20000
    draws give a per-entry standard error under 0.004, and the error it leaves
    is an order of magnitude larger than that, so this is bias, not noise.
    """
    worst = 0.0
    for bel, fs, worlds, truth in SYSTEMS[:6]:
        v3 = V03Backend(bel, random.Random(4), n_samples=20000)
        err = float(np.abs(v3.free_marginals() - truth).max())
        worst = max(worst, err)
    assert worst > 0.05, ("v0.3 looks unbiased now; if the sampler was fixed, "
                          "this test should be rewritten, not deleted")


# ---------------------------------------------------------------------------
# worlds() from every backend
# ---------------------------------------------------------------------------

def _owners_from_hands(fs, hands):
    owners = []
    for c in fs.free:
        who = -1
        for p in range(NUM_PLAYERS):
            if hands[p] >> c & 1:
                who = p
        owners.append(who)
    return owners


def test_every_backend_produces_valid_worlds():
    for bel, fs, worlds, truth in SYSTEMS[:6] + OR_SYSTEMS[:4]:
        backends = [
            V03Backend(bel, random.Random(1)),
            UniformRejectBackend(bel, random.Random(2), n_accepted=16),
            ExactOrBackend(bel, random.Random(3), work_budget=10 ** 12),
            MCMCBackend(bel, random.Random(4), n_sweeps=20, burn_sweeps=5),
        ]
        for b in backends:
            got = b.worlds(8)
            assert got, b.name
            for hands in got:
                assert fs.valid_world(_owners_from_hands(fs, hands)), b.name
                live = sum(1 for c in range(bel.n)
                           if bel.public_loc[c] != RESOLVED)
                assert sum(int(h).bit_count() for h in hands) == live, b.name


def test_exact_or_worlds_are_uniform():
    """The DP-driven sampler must reproduce its own exact marginals."""
    bel, fs, worlds, truth = SYSTEMS[1]
    eo = ExactOrBackend(bel, random.Random(11), work_budget=10 ** 12)
    n = 20000
    acc = np.zeros((fs.n_free, NUM_PLAYERS))
    for hands in eo.worlds(n):
        for i, p in enumerate(_owners_from_hands(fs, hands)):
            acc[i, p] += 1
    acc /= n
    assert np.abs(acc - truth).max() < 0.02


# ---------------------------------------------------------------------------
# marginals() over the whole deck, and the snapshot round trip
# ---------------------------------------------------------------------------

def test_full_deck_marginals_shape_and_public_rows():
    bel = build_belief([0b000011, 0b000110, 0b000101], [1, 1, 1, 0, 0, 0],
                       resolved_half_suit=8)
    fs = FreeSystem(bel)
    eo = ExactOrBackend(bel, random.Random(1), work_budget=10 ** 12)
    M = eo.marginals()
    assert M.shape == (bel.n, NUM_PLAYERS)
    for c in half_suit_cards(8):
        assert M[c].sum() == 0.0            # resolved cards belong to nobody
    for c in range(bel.n):
        if bel.public_loc[c] == RESOLVED:
            continue
        assert abs(M[c].sum() - 1.0) < 1e-9
        if c not in fs.pos:
            assert M[c].max() == 1.0        # pinned: one-hot


def test_snapshot_round_trip_preserves_every_backend_answer():
    for bel, fs, worlds, truth in SYSTEMS[:8]:
        bel2 = restore_belief(snapshot_belief(bel))
        a = ExactOrBackend(bel, random.Random(1), work_budget=10 ** 12)
        b = ExactOrBackend(bel2, random.Random(1), work_budget=10 ** 12)
        assert np.array_equal(a.free_marginals(), b.free_marginals())


# ---------------------------------------------------------------------------
# the fast sampler must not change counting.py's law or its API
# ---------------------------------------------------------------------------

def test_fast_sampler_matches_the_exact_expected_counts():
    """The fast draw is only allowed to be faster, not different."""
    rng = random.Random(7)
    checked = 0
    while checked < 12:
        n_cards = rng.randint(4, 10)
        pool = [rng.randint(1, 63) for _ in range(rng.randint(2, 4))]
        card_masks = [rng.choice(pool) for _ in range(n_cards)]
        quotas = [0] * NUM_PLAYERS
        for _ in range(n_cards):
            quotas[rng.randrange(NUM_PLAYERS)] += 1
        masks, sizes, _cg = group_cards(card_masks)
        try:
            sysm = FastGroupSystem(masks, sizes, quotas)
            if sysm.partition() <= 0:
                continue
        except Exception:
            continue
        E = sysm.expected_counts()
        N = 8000
        acc = np.zeros((sysm.G, NUM_PLAYERS))
        r = random.Random(checked)
        for _ in range(N):
            k = sysm.sample_counts_fast(r)
            for g in range(sysm.G):
                row = k[g]
                for p in range(NUM_PLAYERS):
                    if row[p]:
                        acc[g, p] += row[p]
        acc /= N
        # per-entry SE of a mean count is at most size_g/(2*sqrt(N)) = 0.056*size
        tol = 0.06 * np.maximum(1.0, np.array(sizes, dtype=float))[:, None]
        assert (np.abs(acc - E) <= tol).all(), (acc, E, sizes, quotas)
        checked += 1


def test_counting_module_still_agrees_with_brute_force():
    """Regression guard: fish4/counting.py was extended, never modified."""
    rng = random.Random(21)
    checked = 0
    while checked < 25:
        n_cards = rng.randint(3, 8)
        pool = [rng.randint(1, 63) for _ in range(rng.randint(1, 3))]
        card_masks = [rng.choice(pool) for _ in range(n_cards)]
        quotas = [0] * NUM_PLAYERS
        for _ in range(n_cards):
            quotas[rng.randrange(NUM_PLAYERS)] += 1
        masks, sizes, cg = group_cards(card_masks)
        try:
            sysm = GroupSystem(masks, sizes, quotas)
            Z = sysm.partition()
        except Exception:
            continue
        count, marg = brute_force(card_masks, quotas)
        assert abs(Z - count) < 1e-6 * max(1.0, count)
        if count == 0:
            continue
        E = sysm.expected_counts()
        for c in range(n_cards):
            g = cg[c]
            for p in range(NUM_PLAYERS):
                assert abs(E[g, p] / sizes[g] - marg[c][p]) < 1e-9
        checked += 1
