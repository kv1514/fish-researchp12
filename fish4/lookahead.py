"""Lookahead over the *belief*, not over sampled worlds.

WHY THIS IS THE ONE SEARCH DESIGN NOT YET TRIED
-----------------------------------------------
Every search this project has attempted - PIMC, Information-Set MCTS, the
value-network variants - evaluates a candidate move by sampling hidden layouts
and solving each one. v0.3 measured why they all failed: the standard deviation
of a position's value across possible layouts is about 2.4x the gap between the
best and the worst candidate move, so a search that scores different candidates
against different sampled worlds is ranking sampling noise. Common random
numbers removed the deficit and never produced a surplus.

The lookahead here never samples. Its state is the posterior marginal matrix
``M[card, player]``, and its transitions are exact local edits of that matrix.
Given a belief it is a deterministic function - run it twice, get the same
answer - so the variance that killed the previous attempts is structurally
absent rather than merely reduced.

WHAT IT COMPUTES: THE POSSESSION CHAIN
--------------------------------------
A Literature turn is a run of asks that ends the instant one misses. Greedy
scoring maximises the immediate P(success); what a possession is actually worth
is how many cards it banks before the turn flips. Those differ whenever taking
one card changes what else is askable::

    W(B, d) = max over legal asks a of  p_a * [1 + W(B | a succeeded, d-1)]

``W`` is in units of *cards expected to be banked in the rest of this
possession*. The failure branch contributes nothing to ``W`` because a miss
ends the possession, and what a miss costs positionally is already priced by
the incumbent objective's turn-risk and exposure terms.

HOW IT COMBINES WITH THE INCUMBENT OBJECTIVE
--------------------------------------------
It does not replace it. The paper's sharpest negative result is that replacing
P(success) with a learned half-suit value - correct units, calibrated model -
costs 7.4 sets per deal-pair. The lesson taken here is that P(success) is the
objective and everything else is a tie-break, so the lookahead enters as an
additive bonus::

    score(a) = incumbent_score(a) + w_lookahead * p_a * W(B | a succeeded, d-1)

At ``depth <= 1``, or at ``w_lookahead == 0``, the bonus is identically zero and
the policy reproduces the incumbent decision for decision. That is not a
convention, it is the ablation discipline this project enforces by test: a
weight of zero must reduce to the baseline exactly, or the cell is measuring two
changes at once.

A CAUTION, STATED UP FRONT
--------------------------
There is a scheduling argument that predicts this will do nothing. If the
candidate asks were independent and all remained available regardless of which
you took first, then ordering them by descending p_a already maximises the
expected number banked before the first miss, and greedy is optimal - no
lookahead can improve on it. The bonus can only pay where that argument breaks:

1. asks are *not* independent - taking a card edits the belief other asks are
   scored against;
2. asks *disappear* - a card taken cannot be asked for again, and a half-suit
   can be exhausted;
3. which opponent receives the turn on a miss depends on the ask.

So this module is built to test a specific hypothesis, and the scheduling
argument above is the null it is being tested against.

INFORMATION BOUNDARY
--------------------
Every input is observation-derived: the posterior marginals (an inference from
public events plus this seat's own hand), our own hand, public hand counts, and
which half-suits are resolved. ``GameState`` is not reachable from here, and the
hypothetical future states the search builds are edits of the *belief*, never
peeks at a layout.
"""

from __future__ import annotations

import numpy as np

from fish.cards import NUM_PLAYERS, half_suit_mask, mask_to_cards, team_of

#: Default plies of possession to look ahead. Depth 1 is the incumbent.
DEFAULT_DEPTH = 3
#: Default number of candidate asks expanded per ply, in the CONTINUATION only.
#: A real mid-game position offers a median of 45 legal asks (mean 45.0, p90 81,
#: max 102, measured over 615 decisions), so an unbeamed depth-3 tree would be
#: ~45^3 nodes for a quantity dominated by its best few branches.
#:
#: The root ply is deliberately not beamed: lookahead_bonus has to return a
#: bonus for every candidate the policy is ranking, so the cost is n(1 + b + b^2)
#: = 21n, about 945 expansions at the median n, not the 84 a uniformly-beamed
#: tree would give.
DEFAULT_BEAM = 4


class ChainState:
    """A hypothetical continuation of our own possession, held as a belief.

    Mutable by design and always restored: the search descends by applying an
    edit and ascends by undoing it, so one array is reused for the whole tree
    rather than copied per node.
    """

    __slots__ = ("M", "hand", "counts", "me", "live", "n_hs", "couple", "_undo")

    def __init__(self, M: np.ndarray, hand: int, counts, me: int, live,
                 n_hs: int, couple: bool = True):
        self.M = M.copy()
        self.hand = hand
        self.counts = list(counts)
        self.me = me
        self.live = list(live)
        self.n_hs = n_hs
        self.couple = couple
        self._undo: list = []

    # -- candidate generation -------------------------------------------------

    def legal_asks(self, allow_bluff: bool = False):
        """Mirror of ``Observation.legal_asks`` over the hypothetical hand.

        Same three conditions the engine enforces: the half-suit is unresolved,
        we hold at least one card of it, and (absent bluffing) we do not hold
        the card asked for. Targets are opponents who still have cards.
        """
        opps = [o for o in range(NUM_PLAYERS)
                if team_of(o) != team_of(self.me) and self.counts[o] > 0]
        if not opps:
            return []
        out = []
        for hs in range(self.n_hs):
            if not self.live[hs]:
                continue
            hs_mask = half_suit_mask(hs)
            if not self.hand & hs_mask:
                continue
            askable = hs_mask if allow_bluff else (hs_mask & ~self.hand)
            for card in mask_to_cards(askable):
                for o in opps:
                    out.append((o, card))
        return out

    # -- transitions ----------------------------------------------------------

    def apply_success(self, target: int, card: int) -> None:
        """The ask landed: the card is now provably ours.

        WHY THE QUOTA COUPLING IS NOT OPTIONAL
        --------------------------------------
        Collapsing the asked card's row to a point mass on us is the exact and
        obvious part. On its own it is also *inert*, and that is worth spelling
        out, because it determines whether this whole module can do anything at
        all.

        A success edits only the asked card's row, so if nothing else moved, the
        success probability of every other candidate would be unchanged for the
        rest of the possession. The search would then be maximising

            p_1 * (1 + p_2 * (1 + ...))

        over a *fixed* set of numbers, and an exchange argument makes descending
        p optimal: the lookahead would provably collapse to greedy, up to the
        two bookkeeping effects of a target running out of cards and of one card
        being askable from several targets. It would be a no-op by construction,
        and measuring it would be measuring nothing.

        What actually breaks that is the quota system. Learning that the target
        held this card makes it *less* likely they hold the others: they are now
        known to hold one card fewer, and that mass has to go somewhere. So we
        scale the target's column down to the count they now have and let each
        affected row renormalise across the remaining players - one step of the
        same proportional fitting the exact posterior does globally. It is this
        coupling, not the point mass, that lets a second ask be worth more after
        one ask than it was before, which is the only thing a possession-chain
        search can see that greedy cannot.

        ``couple=False`` disables it, and is retained precisely so the claim
        above can be measured rather than argued.
        """
        self._undo.append((card, target, self.M.copy(), self.hand))
        self.M[card] = 0.0
        self.M[card, self.me] = 1.0
        self.hand |= 1 << card
        self.counts[target] -= 1
        self.counts[self.me] += 1
        if self.couple:
            self._rebalance(target)

    def _rebalance(self, target: int) -> None:
        """Shrink ``target``'s column to their new count, then renormalise rows.

        Before the ask the target's expected holding over still-unlocated cards
        summed to their hand count; having given one up it must sum to one less.
        Rows that lose mass get it back spread over the other players in
        proportion to what they already had, which keeps every row a
        distribution and is exactly what a single proportional-fitting sweep
        does. Rows that are already certain carry no free mass and are left
        alone by the same arithmetic.
        """
        M = self.M
        mass = float(M[:, target].sum())
        want = float(self.counts[target])
        if mass <= 1e-12:
            return                      # we already knew where all of theirs was
        # want >= mass would mean inventing probability the counts do not
        # support, so the sweep only ever shrinks.
        M[:, target] *= max(0.0, min(1.0, want / mass))
        self._renormalise_rows()

    def _renormalise_rows(self) -> None:
        """Return each row to a distribution, keeping relative odds elsewhere.

        A row whose whole mass sat on the shrunk column would renormalise
        straight back to where it started, which is right: a publicly located
        card cannot be made less certain by a quota argument. A row left with no
        mass at all is impossible under the counts and is passed over rather
        than turned into a division by zero.
        """
        M = self.M
        tot = M.sum(axis=1)
        live = tot > 1e-12
        M[live] /= tot[live][:, None]

    def undo(self) -> None:
        card, target, M, hand = self._undo.pop()
        self.M[:] = M
        self.hand = hand
        self.counts[target] += 1
        self.counts[self.me] -= 1


def possession_value(state: ChainState, depth: int, beam: int,
                     allow_bluff: bool = False) -> float:
    """Expected cards banked in the remainder of this possession.

    Zero at ``depth <= 0`` and at a position with no legal ask, which is what
    makes the depth-1 policy identical to the incumbent: the bonus term it
    multiplies is this function at depth 0.
    """
    if depth <= 0:
        return 0.0
    asks = state.legal_asks(allow_bluff)
    if not asks:
        return 0.0

    M = state.M
    scored = sorted(asks, key=lambda a: -float(M[a[1], a[0]]))
    best = 0.0
    for target, card in scored[:beam]:
        p = float(M[card, target])
        if p <= 0.0:
            continue
        state.apply_success(target, card)
        try:
            cont = possession_value(state, depth - 1, beam, allow_bluff)
        finally:
            state.undo()
        # A miss ends the possession, so it contributes no cards. What it costs
        # positionally is priced by the incumbent objective, not here.
        q = p * (1.0 + cont)
        if q > best:
            best = q
    return best


def lookahead_bonus(ctx, asks, depth: int = DEFAULT_DEPTH,
                    beam: int = DEFAULT_BEAM, couple: bool = True) -> np.ndarray:
    """Per-ask lookahead bonus, in units of expected extra cards banked.

    ``ctx`` is an :class:`~fish4.askfeat.DecisionContext`. The returned vector
    is all zeros whenever ``depth <= 1``, so a caller that adds it to the
    incumbent score is guaranteed to reproduce the incumbent at depth 1.
    """
    n = len(asks)
    out = np.zeros(n)
    if depth <= 1 or n == 0:
        return out

    obs = ctx.obs
    live = [w is None for w in obs.set_winner]
    allow_bluff = bool(obs.rules.allow_bluff_asks)
    state = ChainState(ctx.M, obs.hand, obs.hand_counts, obs.player,
                       live, ctx.n_hs, couple=couple)

    for i, a in enumerate(asks):
        p = float(ctx.M[a.card, a.target])
        if p <= 0.0:
            continue
        state.apply_success(a.target, a.card)
        try:
            cont = possession_value(state, depth - 1, beam, allow_bluff)
        finally:
            state.undo()
        out[i] = p * cont
    return out
