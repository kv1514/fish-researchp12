"""Posterior over hidden hands: exact where possible, unbiased everywhere.

This is the v0.4 replacement for v0.3's sampled beliefs. It sits on top of the
v0.3 constraint propagator (``fish.beliefs.BeliefState``), which is sound and
well tested, and replaces the *inference* layer:

  v0.3                                v0.4
  ----                                ----
  heuristic sampler, non-uniform      exact DP when no OR clause is active,
                                      unbiased importance sampling otherwise
  marginals from 32 draws             closed form, or weighted draws with a
                                      reported effective sample size
  claim probability from 32 draws     exact whenever the clause set is empty,
                                      and exactly 0/1 whenever deduction
                                      settles it either way
  bias never quantified               bias eliminated; every approximation is
                                      counted in ``PosteriorStats``

THE SPLIT, AND WHY IT IS WHERE IT IS
------------------------------------
The constraint system has two parts. Candidate masks plus exact per-player deal
counts are solved *exactly* by the dynamic program in ``counting.py``. The OR
clauses ("the asker held at least one card of that half-suit at the time") are
not absorbed by that DP, and three measurements decided how to handle them:

* Ignoring them is not an option: on 40 real positions the OR-free exact
  marginals were off by a mean L1 of 0.127 per card against the OR-conditioned
  truth, worse than v0.3's biased sampler at 0.074.
* Rejection is not an option: measured acceptance was mean 0.30, median 0.18,
  and below 0.05 on 16% of positions.
* Folding them into the DP exactly needs the mask groups refined by OR
  membership, whose state space has a bad tail (median 5,760, p99 27,000,000).

So: exact DP when no clause is active, and the importance sampler of ``sis.py``
when one is - which is unbiased, has a measured ESS/N around 0.8, and reaches
every consistent world (all three properties are checked against exhaustive
enumeration in ``tests4/test_sis.py``).
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np

from fish.beliefs import RESOLVED, BeliefContradiction, BeliefState
from fish.cards import NUM_PLAYERS

from .counting import GroupSystem, Infeasible
from .sis import SISFailure, SISSampler, sample_batch


class PosteriorStats:
    """Counters, so approximations are reported rather than hidden."""

    __slots__ = ("decisions", "exact_decisions", "sis_decisions", "draws",
                 "ess_sum", "failures", "infeasible")

    def __init__(self) -> None:
        self.decisions = 0
        self.exact_decisions = 0
        self.sis_decisions = 0
        self.draws = 0
        self.ess_sum = 0.0
        self.failures = 0
        self.infeasible = 0

    def to_dict(self) -> dict:
        d = {s: getattr(self, s) for s in self.__slots__}
        if self.sis_decisions:
            d["mean_ess"] = self.ess_sum / self.sis_decisions
        return d


class Posterior:
    """Posterior queries for one seat at one decision point.

    Construct once per decision from a propagated ``BeliefState``; all queries
    share the same DP tables and the same batch of weighted draws.
    """

    __slots__ = ("bel", "obs", "rng", "n_draws", "n_worlds", "mode", "gamma",
                 "stats", "n", "_sys", "_card_group", "_free", "_marg",
                 "_worlds", "_batch", "_sampler", "_exact_ok", "_idx",
                 "_free_pos", "depth_mode", "count_mode", "opp_lambda")

    def __init__(self, belief: BeliefState, rng: random.Random,
                 n_draws: int = 128, n_worlds: int = 32,
                 mode: str = "auto", obs=None, gamma: float = 0.0,
                 depth_mode: str = "initial", count_mode: str = "linear",
                 opp_lambda: float = 0.0,
                 stats: Optional[PosteriorStats] = None):
        self.bel = belief
        self.obs = obs
        self.gamma = gamma if obs is not None else 0.0
        self.depth_mode = depth_mode
        self.count_mode = count_mode
        self.opp_lambda = opp_lambda
        self.rng = rng
        self.n_draws = n_draws
        self.n_worlds = n_worlds
        self.mode = mode
        self.stats = stats if stats is not None else PosteriorStats()
        self.stats.decisions += 1
        self.n = belief.n
        self._sys: Optional[GroupSystem] = None
        self._card_group: dict[int, int] = {}
        self._free: list[int] = []
        self._marg: Optional[np.ndarray] = None
        self._worlds: Optional[list[list[int]]] = None
        self._batch = None
        self._sampler: Optional[SISSampler] = None
        self._exact_ok = False
        self._idx = None
        self._free_pos: dict[int, int] = {}
        self._build()

    # -- construction --------------------------------------------------------

    def _build(self) -> None:
        bel = self.bel
        quotas = [bel.per] * NUM_PLAYERS
        free: list[int] = []
        for c in range(self.n):
            cand = bel.candidates[c]
            if cand & (cand - 1) == 0:
                quotas[cand.bit_length() - 1] -= 1
            else:
                free.append(c)
        self._free = free
        if not free:
            self._exact_ok = True
            return
        index: dict[int, int] = {}
        masks: list[int] = []
        sizes: list[int] = []
        for c in free:
            m = bel.candidates[c]
            gi = index.get(m)
            if gi is None:
                gi = index[m] = len(masks)
                masks.append(m)
                sizes.append(0)
            sizes[gi] += 1
            self._card_group[c] = gi
        try:
            self._sys = GroupSystem(masks, sizes, quotas)
        except Infeasible:
            self._sys = None
            self.stats.infeasible += 1
        active = self._active_clauses()
        opp = slot = None
        if self.gamma > 0.0 or self.opp_lambda > 0.0:
            from .oppmodel import build as build_opponent
            opp, slot = build_opponent(bel, self.obs, self.gamma,
                                       depth_mode=self.depth_mode,
                                       count_mode=self.count_mode,
                                       opp_lambda=self.opp_lambda,
                                       order=free)
        # The exact DP answers the uniform-target question only. An opponent
        # model changes the target, so it forces the sampling path even when no
        # clause is active.
        use_exact = ((self.mode == "exact"
                      or (self.mode == "auto" and not active))
                     and opp is None)
        if use_exact and self._sys is not None:
            self._exact_ok = True
            self.stats.exact_decisions += 1
        else:
            self._exact_ok = False
            card_masks = {c: bel.candidates[c] for c in free}
            self._sampler = SISSampler(free, card_masks, quotas, active,
                                       opponent_model=opp, card_slot=slot)
            self.stats.sis_decisions += 1

    def _active_clauses(self):
        """Clauses that still constrain a free card.

        The propagator already drops clauses satisfied with certainty and
        unit-propagates the rest, so what is left here genuinely bites.
        """
        free = set(self._free)
        out = []
        for cards, p in self.bel.ors:
            live = tuple(c for c in cards
                         if c in free and (self.bel.candidates[c] >> p & 1))
            if live:
                out.append((live, p))
        return out

    # -- draws ---------------------------------------------------------------

    def _get_batch(self):
        if self._batch is None and self._sampler is not None:
            try:
                self._batch = sample_batch(self._sampler, self.rng, self.n_draws)
            except SISFailure:
                self.stats.failures += 1
                self._batch = None
            if self._batch is not None and len(self._batch):
                self.stats.draws += len(self._batch)
                self.stats.ess_sum += self._batch.ess
                # One integer matrix of owners, draws x free cards. Every
                # downstream query is then a vectorised operation instead of a
                # Python double loop.
                if self._batch.picks is not None:
                    self._free_pos = {c: j for j, c in enumerate(self._batch.order)}
                    self._idx = self._batch.picks
                else:
                    free = self._free
                    self._free_pos = {c: j for j, c in enumerate(free)}
                    self._idx = np.empty((len(self._batch), len(free)),
                                         dtype=np.int64)
                    for i, deal in enumerate(self._batch.deals):
                        row = self._idx[i]
                        for j, c in enumerate(free):
                            row[j] = deal[c]
        return self._batch

    # -- marginals -----------------------------------------------------------

    def initial_marginals(self) -> np.ndarray:
        """``P(card c was dealt to player p)``."""
        M = np.zeros((self.n, NUM_PLAYERS), dtype=np.float64)
        for c in range(self.n):
            cand = self.bel.candidates[c]
            if cand & (cand - 1) == 0:
                M[c, cand.bit_length() - 1] = 1.0
        if not self._free:
            return M
        if self._exact_ok and self._sys is not None:
            try:
                E = self._sys.expected_counts()
                sizes = self._sys.sizes
                for c in self._free:
                    g = self._card_group[c]
                    M[c] = E[g] / sizes[g]
                return M
            except Infeasible:
                self.stats.infeasible += 1
        batch = self._get_batch()
        if batch is None or not len(batch):
            # Last resort: fall back to the v0.3 sampler so a decision is still
            # possible. Counted, never silent.
            self.stats.failures += 1
            hands = [self.bel.sample_current_hands(self.rng)
                     for _ in range(max(8, self.n_worlds))]
            for c in self._free:
                row = np.zeros(NUM_PLAYERS)
                for h in hands:
                    for p in range(NUM_PLAYERS):
                        if h[p] >> c & 1:
                            row[p] += 1
                            break
                M[c] = row / len(hands)
            return M
        free = self._free
        for c in free:
            M[c] = 0.0
        idx = self._idx
        if idx is None:
            for w, deal in zip(batch.w, batch.deals):
                for c in free:
                    M[c, deal[c]] += w
            return M
        cols = batch.order if batch.order is not None else free
        nf = idx.shape[1]
        flat = (idx + NUM_PLAYERS * np.arange(nf, dtype=np.int64)[None, :]).ravel()
        wts = np.repeat(batch.w, nf)
        acc = np.bincount(flat, weights=wts, minlength=NUM_PLAYERS * nf)
        acc = acc.reshape(nf, NUM_PLAYERS)
        for j, c in enumerate(cols):
            M[c] = acc[j]
        return M

    def marginals(self) -> np.ndarray:
        """``P(player p currently holds card c)``.

        Resolved cards give an all-zero row; publicly located cards give a
        one-hot row; everything else inherits the initial-deal marginal, because
        an unmoved card still sits with whoever was dealt it.
        """
        if self._marg is not None:
            return self._marg
        M = self.initial_marginals()
        for c in range(self.n):
            loc = self.bel.public_loc[c]
            if loc == RESOLVED:
                M[c] = 0.0
            elif loc is not None:
                M[c] = 0.0
                M[c, loc] = 1.0
        self._marg = M
        return M

    # -- worlds --------------------------------------------------------------

    def worlds(self) -> list[list[int]]:
        """``n_worlds`` current-hand samples, as 6-element bitmask lists.

        Under the exact path these are drawn exactly uniformly; under the
        sampling path they are the weighted draws resampled to unit weight, so
        they are asymptotically uniform rather than exactly so.
        """
        if self._worlds is not None:
            return self._worlds
        out: list[list[int]] = []
        if not self._free:
            out = [self._materialize({}) for _ in range(self.n_worlds)]
        elif self._exact_ok and self._sys is not None:
            try:
                for _ in range(self.n_worlds):
                    out.append(self._materialize(self._exact_draw()))
            except Infeasible:
                self.stats.infeasible += 1
        else:
            batch = self._get_batch()
            if batch is not None and len(batch):
                sel = self.rng.choices(range(len(batch)), weights=list(batch.w),
                                       k=self.n_worlds)
                if batch.picks is not None:
                    order = batch.order
                    out = [self._materialize_row(batch.picks[i], order)
                           for i in sel]
                else:
                    out = [self._materialize(batch.deals[i]) for i in sel]
        if not out:
            self.stats.failures += 1
            try:
                out = [self.bel.sample_current_hands(self.rng)
                       for _ in range(self.n_worlds)]
            except BeliefContradiction:
                out = []
        self._worlds = out
        return out

    def _exact_draw(self) -> dict:
        k = self._sys.sample_counts(self.rng)
        by_group: dict[int, list[int]] = {}
        for c in self._free:
            by_group.setdefault(self._card_group[c], []).append(c)
        deal: dict[int, int] = {}
        for g, cards in by_group.items():
            cards = list(cards)
            self.rng.shuffle(cards)
            i = 0
            for p in range(NUM_PLAYERS):
                for _ in range(int(k[g, p])):
                    deal[cards[i]] = p
                    i += 1
        return deal

    def _materialize_row(self, row, order) -> list[int]:
        hands = [0] * NUM_PLAYERS
        bel = self.bel
        owner_of = {}
        for j, c in enumerate(order):
            owner_of[c] = int(row[j])
        for c in range(self.n):
            loc = bel.public_loc[c]
            if loc == RESOLVED:
                continue
            if loc is not None:
                hands[loc] |= 1 << c
                continue
            owner = owner_of.get(c)
            if owner is None:
                cand = bel.candidates[c]
                owner = cand.bit_length() - 1
            hands[owner] |= 1 << c
        return hands

    def _materialize(self, deal: dict) -> list[int]:
        hands = [0] * NUM_PLAYERS
        bel = self.bel
        for c in range(self.n):
            loc = bel.public_loc[c]
            if loc == RESOLVED:
                continue
            if loc is not None:
                hands[loc] |= 1 << c
                continue
            owner = deal.get(c)
            if owner is None:
                cand = bel.candidates[c]
                owner = cand.bit_length() - 1
            hands[owner] |= 1 << c
        return hands

    # -- joint queries --------------------------------------------------------

    def prob_assignment(self, cards, owners) -> float:
        """``P(card_i is currently held by owner_i for all i)``.

        Exact when the clause set is empty. When it is not, deduction still
        settles the extremes exactly - a zero under the OR-free system implies a
        zero under the (smaller) OR-constrained one, and likewise for one - and
        only the genuine middle is estimated from the weighted draws.
        """
        bel = self.bel
        pins: list[tuple[int, int]] = []
        free_pins: list[tuple[int, int]] = []
        for c, want in zip(cards, owners):
            loc = bel.public_loc[c]
            if loc == RESOLVED:
                return 0.0
            if loc is not None:
                if loc != want:
                    return 0.0
                continue
            cand = bel.candidates[c]
            if cand & (cand - 1) == 0:
                if cand.bit_length() - 1 != want:
                    return 0.0
                continue
            if not cand >> want & 1:
                return 0.0
            pins.append((self._card_group[c], want))
            free_pins.append((c, want))
        if not pins:
            return 1.0
        if self._sys is None:
            return 0.0
        if self._exact_ok:
            Z = self._sys.partition()
            if not (Z > 0):
                return 0.0
            return self._sys.pinned_partition(pins) / Z
        # With clauses active the exact DP would answer a different question
        # (it ignores them) at the cost of a full extra dynamic program per
        # query. Measured, that was the dominant cost of a decision: up to nine
        # claimable half-suits times three candidate distributions each. The
        # weighted draws answer the right question for the price of one pass.
        batch = self._get_batch()
        if batch is None or not len(batch):
            return 0.0
        idx = self._idx
        if idx is None:
            tot = 0.0
            for w, deal in zip(batch.w, batch.deals):
                if all(deal[c] == want for c, want in free_pins):
                    tot += w
            return float(tot)
        mask = np.ones(idx.shape[0], dtype=bool)
        for c, want in free_pins:
            mask &= idx[:, self._free_pos[c]] == want
        return float(batch.w[mask].sum())

    def prob_holds(self, player: int, card: int) -> float:
        return float(self.marginals()[card, player])

    @property
    def exact(self) -> bool:
        return self._exact_ok
