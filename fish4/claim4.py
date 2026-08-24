"""Claim policy for FishBot v0.4.

WHAT v0.3 ESTABLISHED, AND WHY THE ANSWER IS WHAT IT IS
------------------------------------------------------
A direct sweep found that claiming eagerly is a real, measurable mistake
(threshold 0.70 costs 0.45 sets per deal-pair against 0.97) and that anything
from 0.85 to near-certainty plays identically: over 150 duplicate deals,
thresholds 0.97 and 0.999 never once diverged. An expected-value model built in
v0.3 had predicted an optimum near 0.70 and was falsified.

The mechanism is worth stating because it justifies the design here rather than
leaving 0.97 as a magic number. Suppose our team genuinely holds all six cards
of a half-suit but we cannot place them within the team. What is the cost of
waiting? An opponent cannot take the set from us by claiming it: a claim by a
player whose team does not hold all six *gives* the set to us. So the only cost
of waiting is running out of opportunity, and the benefit is that continued play
localises teammate holdings. Waiting is close to free, which is exactly what the
sweep measured and what the EV model missed by treating the resolution of a
split as a coin flip.

The corollary is that the leverage in claiming is NOT the threshold. It is:

  1. **Getting the declared distribution right.** Nulls cost roughly 0.6 sets
     per deal-pair at v0.3's strength, and a null is a bookkeeping failure, not
     an unlucky gamble. v0.3 chose the modal distribution over 32 sampled
     worlds, which is a noisy estimator of the mode. v0.4 computes the exact
     posterior probability of a candidate distribution, so the declared split
     is the true MAP rather than a sample mode.
  2. **Playing the forced claims well.** When no legal ask exists the agent
     must claim something, and which half-suit it picks and how it declares it
     is pure expected value, with no threshold involved at all.

STRATEGY FUSION WARNING (from the literature survey): a claim must never be
selected by determinized search. Inside any determinization the searcher knows
the true layout, so every claim evaluates as a certain gain and the declared
assignment differs between sampled worlds. Claims are therefore always decided
here, from the posterior, and never by a search procedure.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product as iproduct

import numpy as np

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of, teammates
from fish.engine import Claim


@dataclass(frozen=True)
class ClaimConfig:
    threshold: float = 0.97
    #: how many candidate distributions to confirm with an exact posterior
    #: query (each costs one DP; the shortlist comes from the marginals)
    exact_candidates: int = 3
    #: cap on the enumeration of team assignments for unpinned cards
    max_enumerate: int = 4096
    #: use exact joint probabilities at all (ablation handle).
    #:
    #: Read the ablation carefully. With this False every half-suit takes the
    #: tier-2 path, so `threshold` -- 0.97 -- is compared against an
    #: INDEPENDENCE PRODUCT rather than against a joint probability, and the
    #: two are not the same bar. Measured over 11687 screened half-suits
    #: (results/claim_screen_check.json), the product sits ABOVE the joint on
    #: average, by a mean of 0.007 and by as much as 0.255 on individual
    #: half-suits, so switching it off makes the engine claim MORE eagerly and
    #: not merely less precisely. The ablation therefore moves two things at
    #: once, and "disabling exact joints changes nothing" is a statement about
    #: their sum. The shipped default is True and the screen (0.35) sits far
    #: below the threshold, so on the shipped path the threshold is only ever
    #: compared against a joint or against a deduced 1.0.
    use_exact: bool = True
    #: skip the exact joint query when the independence screen is already far
    #: below anything claimable. Measured motivation: evaluating every claimable
    #: half-suit exactly at every decision was the dominant cost of a v0.4 turn,
    #: and most half-suits are nowhere near claimable.
    screen: float = 0.35


class ClaimEvaluator:
    """Builds and scores claim candidates for one decision."""

    def __init__(self, ctx, cfg: ClaimConfig):
        self.ctx = ctx
        self.cfg = cfg
        self.obs = ctx.obs
        self.post = ctx.post
        self.bel = ctx.bel
        self.me = ctx.me
        self.my_team = ctx.my_team
        self.team = [p for p in range(NUM_PLAYERS) if team_of(p) == self.my_team]
        self._cands = None

    # -- candidate construction ----------------------------------------------

    def best_for_half_suit(self, hs: int):
        """(p_exact, p_team_holds_all, Claim) for the MAP team distribution.

        The MAP is found by shortlisting on the per-card marginals and then
        scoring the shortlist with the joint posterior, because the product of
        marginals is not the joint: cards compete for the same quota slots, so
        per-card modes can be jointly impossible.

        Three tiers, cheapest first. If beliefs already pin all six cards to our
        team the answer is 1.0 by deduction and nothing needs computing. If the
        independence screen says the half-suit is nowhere near claimable, the
        screen value is returned and the joint query is skipped. Only in the
        remaining band is the posterior actually asked.
        """
        M = self.ctx.M
        bel = self.bel
        cards = list(half_suit_cards(hs))

        # Tier 1: fully deduced. current_holder_mask is a singleton for every
        # card and every holder is a teammate.
        assign = []
        for c in cards:
            m = bel.current_holder_mask(c)
            if m == 0 or m & (m - 1):
                assign = None
                break
            holder = m.bit_length() - 1
            if team_of(holder) != self.my_team:
                assign = None
                break
            assign.append(holder)
        if assign is not None:
            return (1.0, 1.0, Claim(hs, tuple(assign)))

        per_card = []
        for c in cards:
            row = M[c]
            opts = [(float(row[p]), p) for p in self.team if row[p] > 0.0]
            if not opts:
                return None
            opts.sort(reverse=True)
            per_card.append(opts)
        p_team_all = float(np.prod([sum(x[0] for x in opts)
                                    for opts in per_card]))
        map_assign = tuple(opts[0][1] for opts in per_card)
        approx = float(np.prod([opts[0][0] for opts in per_card]))

        # Tier 2: screened out.
        if not self.cfg.use_exact or approx < self.cfg.screen:
            return (approx, p_team_all, Claim(hs, map_assign))

        # Tier 3: ask the posterior. Shortlist on the marginals first, because
        # the joint query costs a pass over the weighted draws.
        trimmed = [opts[:2] if len(opts) > 1 else opts for opts in per_card]
        total = 1
        for k in trimmed:
            total *= len(k)
        if total > self.cfg.max_enumerate:
            trimmed = [[k[0]] for k in trimmed]
        cands = []
        for combo in iproduct(*trimmed):
            score = 1.0
            for pr, _ in combo:
                score *= pr
            cands.append((score, tuple(p for _, p in combo)))
        cands.sort(reverse=True)
        best = None
        for _, cand_assign in cands[:max(1, self.cfg.exact_candidates)]:
            pr = self.post.prob_assignment(cards, cand_assign)
            if best is None or pr > best[0]:
                best = (pr, cand_assign)
        # Both numbers from the same joint. This used to return the joint for
        # the split and the INDEPENDENCE PRODUCT for "ours at all", which
        # forced_claim then subtracted one from the other to get "ours but
        # wrongly split" -- a difference between two different distributions,
        # capable of coming out negative and clamped rather than caught. The
        # product is what the tier-2 screen returns and is fine there, because
        # there both numbers are products and the pair stays internally
        # consistent.
        p_team_joint = self.post.prob_all_with(cards, self.team,
                                               self.cfg.max_enumerate)
        return (best[0], p_team_joint, Claim(hs, best[1]))

    def candidates(self):
        if self._cands is None:
            out = []
            for hs in self.obs.claimable_half_suits():
                r = self.best_for_half_suit(hs)
                if r is not None:
                    out.append(r)
            self._cands = out
        return self._cands

    # -- decisions -------------------------------------------------------------

    def best_candidate(self):
        """The most likely-correct claim available, or None."""
        cands = self.candidates()
        if not cands:
            return None
        return max(cands, key=lambda t: t[0])

    def voluntary_claim(self):
        """A claim worth making right now, or None.

        The bar is deliberately high (see module docstring): waiting is nearly
        free while our team holds the set, so the only claims worth making
        unprompted are the ones we are essentially sure of.
        """
        best = self.best_candidate()
        if best is not None and best[0] >= self.cfg.threshold:
            return best[2]
        return None

    def forced_claim(self):
        """The best claim available when we have no legal ask.

        Pure expected value in sets: an exactly-right declaration scores +1, a
        declaration where any card sits with the opponents scores -1 for us, and
        an all-ours-but-wrongly-split declaration nulls at 0 under the baseline
        rule. So maximise ``p_exact - p_opponent_holds_one``.
        """
        cands = self.candidates()
        if not cands:
            # No half-suit has any team-only distribution with positive
            # probability, so whatever we declare loses the set. Pick the one we
            # know most about and declare every card we can actually place,
            # which at least avoids compounding the loss with a nonsense split.
            live = self.obs.claimable_half_suits()
            if not live:
                return None
            best = None
            for hs in live:
                assign, known = [], 0
                for c in half_suit_cards(hs):
                    m = self.bel.current_holder_mask(c)
                    if m and m & (m - 1) == 0 and team_of(
                            m.bit_length() - 1) == self.my_team:
                        assign.append(m.bit_length() - 1)
                        known += 1
                    else:
                        assign.append(self.me if self.obs.hand & (1 << c)
                                      else self.team[0])
                if best is None or known > best[0]:
                    best = (known, hs, tuple(assign))
            return Claim(best[1], best[2])
        wrong_gives_opponent = (
            self.obs.rules.wrong_distribution_outcome == "opponent")

        def ev(t):
            p_exact, p_team, claim = t
            p_opp = max(0.0, 1.0 - p_team)
            p_split = max(0.0, p_team - p_exact)
            loss_split = -1.0 if wrong_gives_opponent else 0.0
            return p_exact - p_opp + p_split * loss_split

        return max(cands, key=ev)[2]


def choose_pass(ctx, passes):
    """Which teammate receives the turn when we are out of cards.

    v0.3 handed it to whoever held the most cards. Hand size is a proxy for how
    much a player can do with the turn, but what actually converts a turn into
    cards is *knowing where a card is*, so we add the number of steals that are
    certain from public information alone. Both components are public.
    """
    from fish.beliefs import RESOLVED
    obs, bel, M = ctx.obs, ctx.bel, ctx.M
    my_team = ctx.my_team
    best, best_key = None, None
    for pa in passes:
        t = pa.teammate
        certain = 0.0
        for hs in range(ctx.n_hs):
            if not ctx.hs_live[hs]:
                continue
            lo = hs * 6
            # does the teammate hold a card of this half-suit (publicly)?
            holds_public = any(
                bel.public_loc[lo + i] == t for i in range(6))
            if not holds_public:
                # fall back to our posterior estimate
                if float(M[lo:lo + 6, t].sum()) < 0.5:
                    continue
            for i in range(6):
                loc = bel.public_loc[lo + i]
                if (loc is not None and loc != RESOLVED
                        and team_of(loc) != my_team):
                    certain += 1.0
        key = (obs.hand_counts[t] + 0.5 * certain, obs.hand_counts[t])
        if best_key is None or key > best_key:
            best, best_key = pa, key
    return best
