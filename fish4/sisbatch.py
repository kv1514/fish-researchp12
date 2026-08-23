"""Vectorised batch drawing for the sequential importance sampler.

WHY
---
Profiling the v0.4 policy showed a single function, ``SISSampler._attempt``,
taking 67% of total runtime (24.9s of 37.4s over three games). That is
unsurprising: it is a tight Python loop over roughly 26 cards, run 128 times per
decision and roughly 110 times per game, so it executes several hundred thousand
times per game.

The loop is sequential *within* a draw but completely independent *across*
draws, so the whole batch can advance one card at a time with every draw
progressing in lockstep. Each card then costs a handful of numpy operations on
``(N, 6)`` arrays instead of ``N`` passes of scalar Python. The proposal
distribution is unchanged - this is the same algorithm, executed differently -
and ``tests4/test_sisbatch.py`` asserts that by comparing the realised
distribution against the analytic path density that the scalar implementation is
already validated against.

DEAD ENDS
---------
A draw can paint itself into a corner (a card with no candidate that still has
quota, or two clauses demanding the same card for different players). In the
scalar sampler that triggers a restart. Here such draws are simply marked dead
and dropped from the batch; the caller may top up. Both are the same
conditioning-on-success, which multiplies every density by the same constant and
so leaves self-normalised weights unaffected. The measured dead-end rate on real
positions is zero in 10,050 draws, so this path is a safety net rather than a
hot one.
"""

from __future__ import annotations

import numpy as np

from fish.cards import NUM_PLAYERS


def _plan(sampler):
    """Per-card constants, precomputed once and cached on the sampler.

    Everything here was previously recomputed inside the per-card loop of every
    batch: candidate arrays, the column each clause's player occupies, and the
    opponent-model slot per candidate column. Hoisting them out is most of the
    difference between the batch path being 1.4x and 5.6x faster than the scalar
    one.
    """
    cached = sampler._batch_plan
    if cached is not None:
        return cached
    plan = []
    for i in range(sampler._n):
        cand = np.asarray(sampler._ocand[i], dtype=np.int64)
        clauses = sampler._oclause[i]
        cps = sampler._oc_player[i]
        cols = []
        for j, ci in enumerate(clauses):
            k = int(np.searchsorted(cand, cps[j]))
            cols.append(k if k < cand.size and cand[k] == cps[j] else -1)
        slots = (np.asarray(sampler._otilt[i], dtype=np.int64)
                 if sampler._otilt is not None else None)
        plan.append((cand, tuple(clauses), tuple(cps), tuple(cols), slots))
    sampler._batch_plan = plan
    return plan


def draw_batch(sampler, rng, n: int):
    """Draw ``n`` worlds at once.

    Returns ``(picks, logq, logl, alive)`` where ``picks`` is an ``(n, n_free)``
    integer array of owners in ``sampler.order`` column order.
    """
    n_free = sampler._n
    if n_free == 0 or n <= 0:
        return (np.zeros((0, 0), dtype=np.int64), np.zeros(0),
                np.zeros(0), np.zeros(0, dtype=bool))
    n_or = len(sampler.ors)
    # numpy's Generator is seeded from the caller's Random so the batch stays a
    # deterministic function of the agent's own RNG stream.
    gen = np.random.default_rng(rng.getrandbits(63))
    plan = _plan(sampler)

    quota = np.tile(np.asarray(sampler.quotas, dtype=np.float64), (n, 1))
    picks = np.zeros((n, n_free), dtype=np.int64)
    logq = np.zeros(n, dtype=np.float64)
    alive = np.ones(n, dtype=bool)
    if n_or:
        live_left = np.tile(
            np.asarray([len(live) for live, _ in sampler.ors], dtype=np.int64),
            (n, 1))
        satisfied = np.zeros((n, n_or), dtype=bool)
    else:
        live_left = satisfied = None
    n_slots = sampler._n_slots
    depth = np.zeros((n, n_slots), dtype=np.int64) if n_slots else None
    boost = sampler.boost
    rows = np.arange(n)
    randoms = gen.random((n_free, n))

    # Proposal twist (see OpponentModel._build_tilt). One row per slot plus a
    # trailing all-ones row, so a candidate with no slot indexes a no-op instead
    # of needing a mask in the inner loop.
    om0 = sampler.opponent_model
    tiltT = None
    if om0 is not None and getattr(om0, "tilt", None) is not None and n_slots:
        maxd = om0.TILT_MAX_DEPTH
        tiltT = np.ones((n_slots + 1, maxd), dtype=np.float64)
        for si, row in enumerate(om0.tilt):
            if row is not None:
                tiltT[si, :len(row)] = row

    for i in range(n_free):
        cand, clauses, cps, cols, slots = plan[i]
        m = cand.size
        W = quota[:, cand].copy()
        np.maximum(W, 0.0, out=W)
        if tiltT is not None and slots is not None:
            have = slots >= 0
            dcol = depth[:, np.where(have, slots, 0)]
            np.clip(dcol, 0, tiltT.shape[1] - 1, out=dcol)
            W *= tiltT[np.where(have, slots, n_slots)[None, :], dcol]

        forced = None
        if clauses:
            boosted = np.zeros((n, m), dtype=bool)
            for j, ci in enumerate(clauses):
                unsat = ~satisfied[:, ci]
                k = cols[j]
                if k >= 0:
                    col = unsat & (~boosted[:, k])
                    if col.any():
                        W[col, k] *= boost
                        boosted[col, k] = True
                need = unsat & (live_left[:, ci] == 1)
                if need.any():
                    want = cps[j]
                    if forced is None:
                        forced = np.full(n, -1, dtype=np.int64)
                    conflict = need & (forced >= 0) & (forced != want)
                    if conflict.any():
                        alive &= ~conflict
                    forced[need & (forced < 0)] = want

        total = W.sum(axis=1)
        if forced is None:
            free_mask = alive
        else:
            free_mask = alive & (forced < 0)
        dead = free_mask & (total <= 0.0)
        if dead.any():
            alive &= ~dead
            free_mask &= ~dead

        r = randoms[i] * np.maximum(total, 1e-300)
        csum = np.cumsum(W, axis=1)
        sel = (csum < r[:, None]).sum(axis=1)
        np.clip(sel, 0, m - 1, out=sel)
        bad = free_mask & (W[rows, sel] <= 0.0)
        if bad.any():
            sel[bad] = np.argmax(W[bad], axis=1)
            alive &= ~(free_mask & (W[rows, sel] <= 0.0))
        chosen = W[rows, sel]
        np.add(logq, np.where(free_mask,
                              np.log(np.where(chosen > 0.0, chosen, 1.0)
                                     / np.where(total > 0.0, total, 1.0)),
                              0.0), out=logq)

        if forced is None:
            idx = sel
            pick = cand[sel]
        else:
            fmask = alive & (forced >= 0)
            fpos = np.zeros(n, dtype=np.int64)
            if fmask.any():
                fp = np.searchsorted(cand, np.where(fmask, forced, cand[0]))
                np.clip(fp, 0, m - 1, out=fp)
                alive &= ~(fmask & (cand[fp] != forced))
                alive &= ~(fmask & (quota[rows, np.clip(forced, 0, 5)] <= 0.0))
                fpos = fp
            idx = np.where(forced >= 0, fpos, sel)
            pick = cand[idx]

        upd = alive
        quota[rows[upd], pick[upd]] -= 1.0
        picks[:, i] = np.where(upd, pick, 0)
        if depth is not None and slots is not None:
            sidx = slots[idx]
            take = upd & (sidx >= 0)
            if take.any():
                # each row appears at most once here, so the indices are unique
                # and a direct scatter is safe (and much faster than np.add.at)
                depth[rows[take], sidx[take]] += 1
        if clauses:
            for j, ci in enumerate(clauses):
                live_left[upd, ci] -= 1
                satisfied[:, ci] |= upd & (pick == cps[j])

    alive &= (quota == 0.0).all(axis=1)
    if n_or:
        alive &= satisfied.all(axis=1)

    logl = np.zeros(n, dtype=np.float64)
    om = sampler.opponent_model
    if om is not None and om.opp_lambda and om.set_cols:
        # "If the opponents held this whole half-suit, one of them would very
        # likely have declared it by now." Not a constraint - they may hold it
        # and be unable to place the split - so it enters as a soft weight.
        for cols in om.set_cols:
            if not cols:
                continue
            idxc = np.asarray(cols, dtype=np.int64)
            all_opp = ((picks[:, idxc] & 1) != om.my_team).all(axis=1)
            logl -= om.opp_lambda * all_opp
    if om is not None and depth is not None:
        w = np.asarray(om.weight, dtype=np.float64)
        base = np.asarray(om.base, dtype=np.int64)
        d = depth + base[None, :]
        logl = (np.log(np.where(d > 0, d, 1e-9)) * w[None, :]).sum(axis=1)
    return picks, logq, logl, alive


def batch_to_deals(sampler, picks, alive):
    """Turn the ``(n, n_free)`` owner matrix into the dict form callers expect."""
    order = sampler.order
    out = []
    for i in range(picks.shape[0]):
        if not alive[i]:
            continue
        row = picks[i]
        out.append({c: int(row[j]) for j, c in enumerate(order)})
    return out
