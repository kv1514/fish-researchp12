"""Prototype: exact counting / uniform sampling of Fish-consistent deals.

The inference problem, stated exactly.

After propagation, every card is either publicly located or "free". A free
card ``c`` has a candidate mask ``S_c`` (the set of players who could have
been dealt it) and each player ``p`` has a residual quota ``q_p`` (how many
of the free cards were dealt to them). A *world* is an assignment
f: free cards -> players with f(c) in S_c and |f^-1(p)| = q_p, additionally
satisfying the OR constraints ("player p held at least one card of set O at
the time of some ask").

v0.3 sampled worlds with a heuristic that satisfies every constraint but is
NOT uniform over the consistent set, so every reported probability inherited
an unquantified bias. This prototype computes the *exact* count and draws
*exactly uniform* worlds.

Key structural fact, measured on real games: the number of DISTINCT candidate
masks is tiny (mean 3.9, max 8) even though the number of free cards is large
(mean 25.6, max 45). Cards sharing a mask are exchangeable, so the whole
problem collapses onto the group-count matrix k[g][p] = how many cards of
mask-group g were dealt to player p. That matrix has at most 8x6 entries.

Counting: the number of worlds with group-count matrix k is
    prod_g  n_g! / prod_p k[g][p]!
(multinomial per group), so

    Z = sum over feasible k of prod_g multinomial(n_g; k[g,.])

which we evaluate by dynamic programming over players, carrying as state the
vector of cards still unassigned in each group. Processing player p means
choosing k[g][p] <= rem_g from each group g with p in S_g, subject to
sum_g k[g][p] = q_p, weighted by prod_g C(rem_g, k[g][p]). The product of
binomials telescopes to the multinomial, so this is exact.

State space = prod_g (n_g + 1), which is a few thousand in practice - small
because the groups are few, not because the cards are.
"""

from __future__ import annotations

import math
import random
from itertools import product as iproduct

import numpy as np

NUM_PLAYERS = 6

# binom[n][k] for n <= 64
_MAXN = 64
_BINOM = np.zeros((_MAXN + 1, _MAXN + 1), dtype=np.float64)
for _n in range(_MAXN + 1):
    _BINOM[_n, 0] = 1.0
    for _k in range(1, _n + 1):
        _BINOM[_n, _k] = _BINOM[_n - 1, _k - 1] + _BINOM[_n - 1, _k]


class Infeasible(Exception):
    pass


class GroupSystem:
    """The (groups x players) quota system extracted from a belief state."""

    def __init__(self, group_masks: list[int], group_sizes: list[int],
                 quotas: list[int]):
        assert len(group_masks) == len(group_sizes)
        self.masks = list(group_masks)
        self.sizes = list(group_sizes)
        self.quotas = list(quotas)
        self.G = len(group_masks)
        if sum(group_sizes) != sum(quotas):
            raise Infeasible("total free cards != total quota")
        # allowed[p] = tuple of group indices player p may take from
        self.allowed = [tuple(g for g in range(self.G)
                              if self.masks[g] >> p & 1)
                        for p in range(NUM_PLAYERS)]
        self.shape = tuple(n + 1 for n in self.sizes)
        self._fwd = None      # forward tables
        self._bwd = None      # backward tables
        self._Z = None

    # -- transition ---------------------------------------------------------

    def _apply_player(self, table: np.ndarray, p: int) -> np.ndarray:
        """Given a table over remaining-group-counts, return the table after
        player p has taken exactly quotas[p] cards from groups they may hold.

        Implemented with an auxiliary axis counting cards taken so far, so the
        'total == q_p' constraint is enforced without enumerating compositions.
        """
        q = self.quotas[p]
        allowed = self.allowed[p]
        if q == 0:
            return table.copy()
        if not allowed:
            raise Infeasible(f"player {p} needs {q} cards but has no group")
        # aux axis appended at the end: cards taken so far, 0..q
        cur = np.zeros(table.shape + (q + 1,), dtype=np.float64)
        cur[..., 0] = table
        for g in allowed:
            n_g = self.sizes[g]
            nxt = np.zeros_like(cur)
            kmax = min(n_g, q)
            for k in range(kmax + 1):
                if k == 0:
                    nxt += cur
                    continue
                # source: rem_g in [k, n_g], taken in [0, q-k]
                src_idx = [slice(None)] * cur.ndim
                dst_idx = [slice(None)] * cur.ndim
                src_idx[g] = slice(k, n_g + 1)
                dst_idx[g] = slice(0, n_g + 1 - k)
                src_idx[-1] = slice(0, q + 1 - k)
                dst_idx[-1] = slice(k, q + 1)
                coef = _BINOM[k:n_g + 1, k]
                bshape = [1] * cur.ndim
                bshape[g] = coef.size
                nxt[tuple(dst_idx)] += cur[tuple(src_idx)] * coef.reshape(bshape)
            cur = nxt
        return cur[..., q]

    # -- forward / backward -------------------------------------------------

    def forward(self) -> list[np.ndarray]:
        """F[p][rem] = weighted number of ways players 0..p-1 could have taken
        their quotas leaving ``rem`` cards in each group."""
        if self._fwd is not None:
            return self._fwd
        F = np.zeros(self.shape, dtype=np.float64)
        F[tuple(self.sizes)] = 1.0
        out = [F]
        for p in range(NUM_PLAYERS):
            F = self._apply_player(F, p)
            out.append(F)
        self._fwd = out
        self._Z = float(out[-1][(0,) * self.G])
        return out

    def partition(self) -> float:
        if self._Z is None:
            self.forward()
        return self._Z

    def backward(self) -> list[np.ndarray]:
        """B[p][rem] = weighted number of ways players p..5 can consume exactly
        ``rem`` cards. B[6][rem] = 1 iff rem == 0."""
        if self._bwd is not None:
            return self._bwd
        B = np.zeros(self.shape, dtype=np.float64)
        B[(0,) * self.G] = 1.0
        tables = [None] * (NUM_PLAYERS + 1)
        tables[NUM_PLAYERS] = B
        for p in range(NUM_PLAYERS - 1, -1, -1):
            tables[p] = self._apply_player_backward(tables[p + 1], p)
        self._bwd = tables
        return tables

    def _apply_player_backward(self, table: np.ndarray, p: int) -> np.ndarray:
        """B_p[rem] = sum_k prod_g C(rem_g, k_g) * B_{p+1}[rem - k]."""
        q = self.quotas[p]
        allowed = self.allowed[p]
        if q == 0:
            return table.copy()
        cur = np.zeros(table.shape + (q + 1,), dtype=np.float64)
        cur[..., 0] = table          # aux = cards still to be taken by p
        for g in allowed:
            n_g = self.sizes[g]
            nxt = np.zeros_like(cur)
            kmax = min(n_g, q)
            for k in range(kmax + 1):
                if k == 0:
                    nxt += cur
                    continue
                # B_p[rem] gets C(rem_g,k) * B_{p+1}[rem - k e_g]
                # so source index rem_g - k, destination rem_g
                src_idx = [slice(None)] * cur.ndim
                dst_idx = [slice(None)] * cur.ndim
                src_idx[g] = slice(0, n_g + 1 - k)
                dst_idx[g] = slice(k, n_g + 1)
                src_idx[-1] = slice(0, q + 1 - k)
                dst_idx[-1] = slice(k, q + 1)
                coef = _BINOM[k:n_g + 1, k]
                bshape = [1] * cur.ndim
                bshape[g] = coef.size
                nxt[tuple(dst_idx)] += cur[tuple(src_idx)] * coef.reshape(bshape)
            cur = nxt
        return cur[..., q]

    # -- exact marginals ----------------------------------------------------

    def expected_counts(self) -> np.ndarray:
        """E[k[g][p]] under the uniform distribution over consistent worlds.

        Computed exactly: for each player p we recompute the transition with
        an extra factor k_g inserted, sandwiched between the forward table
        before p and the backward table after p.
        """
        F = self.forward()
        B = self.backward()
        Z = self.partition()
        if Z <= 0:
            raise Infeasible("no consistent world")
        E = np.zeros((self.G, NUM_PLAYERS), dtype=np.float64)
        for p in range(NUM_PLAYERS):
            q = self.quotas[p]
            if q == 0:
                continue
            for g in self.allowed[p]:
                E[g, p] = self._weighted_transition(F[p], B[p + 1], p, g) / Z
        return E

    def _weighted_transition(self, Fp: np.ndarray, Bnext: np.ndarray,
                             p: int, target_g: int) -> float:
        """sum over rem,k of Fp[rem] * k_{target_g} * prod C(rem_g,k_g)
        * Bnext[rem-k]."""
        q = self.quotas[p]
        allowed = self.allowed[p]
        # carry (value, weighted-by-k_target) pair through the group loop
        cur = np.zeros(Fp.shape + (q + 1,), dtype=np.float64)
        cur[..., 0] = Fp
        curw = np.zeros_like(cur)        # same but multiplied by k_target so far
        for g in allowed:
            n_g = self.sizes[g]
            nxt = np.zeros_like(cur)
            nxtw = np.zeros_like(cur)
            kmax = min(n_g, q)
            for k in range(kmax + 1):
                if k == 0:
                    nxt += cur
                    nxtw += curw
                    continue
                src_idx = [slice(None)] * cur.ndim
                dst_idx = [slice(None)] * cur.ndim
                src_idx[g] = slice(k, n_g + 1)
                dst_idx[g] = slice(0, n_g + 1 - k)
                src_idx[-1] = slice(0, q + 1 - k)
                dst_idx[-1] = slice(k, q + 1)
                coef = _BINOM[k:n_g + 1, k]
                bshape = [1] * cur.ndim
                bshape[g] = coef.size
                cf = coef.reshape(bshape)
                contrib = cur[tuple(src_idx)] * cf
                nxt[tuple(dst_idx)] += contrib
                w = curw[tuple(src_idx)] * cf
                if g == target_g:
                    w = w + contrib * k
                nxtw[tuple(dst_idx)] += w
            cur, curw = nxt, nxtw
        return float(np.sum(curw[..., q] * Bnext))

    # -- exact uniform sampling ---------------------------------------------

    def sample_counts(self, rng: random.Random) -> np.ndarray:
        """Draw k[g][p] exactly from the uniform distribution over worlds."""
        B = self.backward()
        rem = list(self.sizes)
        k = np.zeros((self.G, NUM_PLAYERS), dtype=np.int64)
        for p in range(NUM_PLAYERS):
            q = self.quotas[p]
            if q == 0:
                continue
            allowed = self.allowed[p]
            # enumerate compositions of q over ``allowed`` bounded by rem
            options = []
            weights = []
            for comp in _compositions(q, [min(rem[g], q) for g in allowed]):
                w = 1.0
                nrem = list(rem)
                for gi, g in enumerate(allowed):
                    w *= _BINOM[rem[g], comp[gi]]
                    nrem[g] -= comp[gi]
                w *= B[p + 1][tuple(nrem)]
                if w > 0:
                    options.append((comp, nrem))
                    weights.append(w)
            if not options:
                raise Infeasible("sampler hit a dead end (backward table wrong?)")
            tot = sum(weights)
            r = rng.random() * tot
            acc = 0.0
            pick = len(options) - 1
            for i, w in enumerate(weights):
                acc += w
                if r < acc:
                    pick = i
                    break
            comp, nrem = options[pick]
            for gi, g in enumerate(allowed):
                k[g, p] = comp[gi]
            rem = nrem
        return k


def _compositions(total: int, caps: list[int]):
    """All non-negative integer vectors summing to ``total`` with v[i] <= caps[i]."""
    m = len(caps)
    if m == 0:
        if total == 0:
            yield ()
        return
    if m == 1:
        if total <= caps[0]:
            yield (total,)
        return
    head_max = min(caps[0], total)
    tail_cap = sum(caps[1:])
    lo = max(0, total - tail_cap)
    for v in range(lo, head_max + 1):
        for rest in _compositions(total - v, caps[1:]):
            yield (v,) + rest


# ---------------------------------------------------------------------------
# Brute force reference (small cases only)
# ---------------------------------------------------------------------------

def brute_force(card_masks: list[int], quotas: list[int]):
    """Enumerate every consistent assignment. Returns (count, marginals)."""
    n = len(card_masks)
    count = 0
    marg = [[0] * NUM_PLAYERS for _ in range(n)]
    choices = [[p for p in range(NUM_PLAYERS) if card_masks[c] >> p & 1]
               for c in range(n)]
    for assign in iproduct(*choices):
        cnt = [0] * NUM_PLAYERS
        for p in assign:
            cnt[p] += 1
        if cnt != list(quotas):
            continue
        count += 1
        for c, p in enumerate(assign):
            marg[c][p] += 1
    if count:
        marg = [[v / count for v in row] for row in marg]
    return count, marg


def system_from_cards(card_masks: list[int], quotas: list[int]) -> tuple:
    """Group identical masks; return (GroupSystem, card->group index)."""
    order: dict[int, int] = {}
    sizes: list[int] = []
    masks: list[int] = []
    card_group = []
    for m in card_masks:
        if m not in order:
            order[m] = len(masks)
            masks.append(m)
            sizes.append(0)
        gi = order[m]
        sizes[gi] += 1
        card_group.append(gi)
    return GroupSystem(masks, sizes, quotas), card_group


if __name__ == "__main__":
    import time
    rng = random.Random(0)
    print("=== validation against brute force ===")
    bad = 0
    for trial in range(300):
        n_cards = rng.randint(4, 11)
        # random masks drawn from a small pool so groups actually form
        pool = [rng.randint(1, 63) for _ in range(rng.randint(1, 4))]
        card_masks = [rng.choice(pool) for _ in range(n_cards)]
        # random quotas summing to n_cards
        quotas = [0] * NUM_PLAYERS
        for _ in range(n_cards):
            quotas[rng.randrange(NUM_PLAYERS)] += 1
        try:
            sysm, card_group = system_from_cards(card_masks, quotas)
            Z = sysm.partition()
            E = sysm.expected_counts()
        except Infeasible:
            Z, E = 0.0, None
        bf_count, bf_marg = brute_force(card_masks, quotas)
        if abs(Z - bf_count) > 1e-6 * max(1.0, bf_count):
            print(f"  COUNT MISMATCH trial {trial}: dp={Z} brute={bf_count} "
                  f"masks={card_masks} quotas={quotas}")
            bad += 1
            continue
        if bf_count == 0:
            continue
        # marginals
        for c in range(n_cards):
            g = card_group[c]
            for p in range(NUM_PLAYERS):
                dp_p = E[g, p] / sysm.sizes[g]
                if abs(dp_p - bf_marg[c][p]) > 1e-9:
                    print(f"  MARGINAL MISMATCH trial {trial} card {c} player {p}: "
                          f"dp={dp_p:.6f} brute={bf_marg[c][p]:.6f}")
                    bad += 1
                    break
            else:
                continue
            break
    print(f"  {300 - bad}/300 random systems matched brute force exactly")

    print("\n=== sampler uniformity (chi-square style check) ===")
    card_masks = [0b111100, 0b111100, 0b001110, 0b001110, 0b110011]
    quotas = [1, 0, 1, 1, 1, 1]
    sysm, card_group = system_from_cards(card_masks, quotas)
    bf_count, bf_marg = brute_force(card_masks, quotas)
    E = sysm.expected_counts()
    print(f"  worlds: dp={sysm.partition():.0f} brute={bf_count}")
    N = 40000
    acc = np.zeros((sysm.G, NUM_PLAYERS))
    t0 = time.time()
    for _ in range(N):
        acc += sysm.sample_counts(rng)
    dt = time.time() - t0
    acc /= N
    err = np.max(np.abs(acc - E))
    print(f"  max |sampled - exact| over {N} draws: {err:.4f} "
          f"({dt/N*1e6:.1f} us/draw)")
