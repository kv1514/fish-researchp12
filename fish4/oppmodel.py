"""Inferring hidden cards from what players CHOSE to ask, not just legality.

THE GAP THIS FILLS
------------------
v0.3's belief tracker extracts from an ask exactly three hard facts: the asker
held at least one card of that half-suit, the asker did not hold the asked card,
and the target did or did not have it. All three are consequences of the rules.
None of them uses the fact that the asker *chose* that half-suit out of the
several they could legally have asked in.

That choice is informative. Under the simplest defensible model of how a player
picks - proportional to how many cards of a half-suit they hold - the
probability of the observed choice is

    P(ask in H | hand) = depth_H(hand) / |hand|

and the denominator is public, so it is the same in every candidate world and
cancels. The likelihood of the whole observed ask sequence is therefore
proportional to a product of depths, one factor per ask, which turns "who asked
where" into a soft weight over worlds.

WHY THIS IS THE RIGHT PLACE TO PUT IT
-------------------------------------
The likelihood cannot go into the constraint propagator, because it is not a
constraint: it excludes nothing, it only re-weights. It fits naturally into the
importance sampler, which is already carrying a per-world weight, and costs one
integer increment per card during a draw.

HONESTY ABOUT WHAT THIS IS
--------------------------
This is a *model*, not a deduction, and the rest of the engine is deduction. If
the model is wrong the posterior gets worse, and against opponents who
deliberately vary their asks it could be exploited. So it is controlled by a
single parameter ``gamma``, with ``gamma = 0`` recovering the uninformative-
choice assumption exactly, and it is validated against ground truth (the true
hidden hands in simulation) rather than by whether it feels reasonable. See
``scripts4/posterior_accuracy.py``.

A known limitation, stated rather than hidden: depth is evaluated on the INITIAL
deal, not at the moment of the ask. Cards move, so late in a game the two
diverge. Modelling the depth at ask time would require replaying each candidate
world through the whole public history, which costs O(history) per draw instead
of O(1).
"""

from __future__ import annotations

import math

from fish.cards import NUM_PLAYERS, half_suit_of
from fish.engine import AskEvent

from .sis import OpponentModel


def build(bel, obs, gamma: float, include_self: bool = False,
          depth_mode: str = "initial", count_mode: str = "linear",
          opp_lambda: float = 0.0, order=None):
    """Build an ``(OpponentModel, card_slot)`` pair, or ``(None, None)``.

    ``card_slot`` maps ``(player, card)`` to the model slot for that player and
    that card's half-suit, which is the form the sampler's inner loop wants.

    ``depth_mode`` chooses what "depth" means for the already-located cards of a
    half-suit, which is the part of the count the sampler does not re-draw:

    ``"initial"``
        cards the propagator has pinned to that player in the INITIAL deal. This
        matches the constraint system, which is stated over the initial deal.
    ``"current"``
        cards the player publicly holds RIGHT NOW. Superficially closer to the
        quantity the choice model is about, and measured to be much worse (see
        the results): it mixes a present-tense count with free cards that are
        being drawn over the INITIAL deal, so the two halves of the depth are
        counted at different times.
    ``"attime"``
        cards publicly located with that player AT THE MOMENT THEY ASKED,
        averaged over their asks in that half-suit. This is the quantity the
        model actually wants, and it is consistent with the free half: a card
        that is still free now was never publicly located, so its holder at the
        time of the ask was whoever was dealt it.

    ``"attime"`` needs one replay of the public log per decision, not per
    candidate world, because only the already-located half of the count depends
    on time. It remains an approximation in one respect: several asks by the same
    player in the same half-suit are collapsed onto one slot, so their per-ask
    counts are averaged rather than kept separate.

    ``count_mode`` decides how repeated asks in the same half-suit accumulate.
    Under the choice model each ask is an independent draw, so the likelihood is
    the depth raised to the number of asks: that is ``"linear"``, and it is the
    principled reading. But asks in one half-suit are plainly *not* independent
    - a player keeps working a suit because they are working it - so the linear
    form over-counts correlated evidence. ``"sqrt"`` and ``"capped"`` are the
    two obvious hedges, and which is right is an empirical question.
    """
    if gamma <= 0.0 and opp_lambda <= 0.0:
        return None, None
    counts: dict[tuple[int, int], int] = {}
    me = obs.player
    for ev in obs.history:
        if not isinstance(ev, AskEvent):
            continue
        if not include_self and ev.asker == me:
            continue
        key = (ev.asker, half_suit_of(ev.card))
        counts[key] = counts.get(key, 0) + 1
    if not counts and opp_lambda <= 0.0:
        return None, None
    slots = {key: i for i, key in enumerate(counts)}
    weight = [0.0] * len(slots)
    base = [0] * len(slots)
    for key, i in slots.items():
        n = counts[key]
        if count_mode == "sqrt":
            n = math.sqrt(n)
        elif count_mode == "capped":
            n = 1.0
        weight[i] = gamma * n
    # base[i] = cards of that half-suit already pinned to that player by the
    # propagator, i.e. depth contributed by cards the sampler will not re-draw
    if depth_mode == "attime":
        _attime_base(bel, obs, slots, base, include_self, me)
    else:
      for (player, hs), i in slots.items():
        lo = hs * 6
        n = 0
        for c in range(lo, lo + 6):
            if depth_mode == "current":
                m = bel.current_holder_mask(c)
                if m and m & (m - 1) == 0 and m.bit_length() - 1 == player:
                    n += 1
            else:
                cand = bel.candidates[c]
                if cand & (cand - 1) == 0 and cand.bit_length() - 1 == player:
                    n += 1
        base[i] = n
    card_slot: dict[tuple[int, int], int] = {}
    for (player, hs), i in slots.items():
        lo = hs * 6
        for c in range(lo, lo + 6):
            card_slot[(player, c)] = i

    # ---- the "nobody declared it" signal -----------------------------------
    # A team that holds an entire half-suit and can place the split declares it.
    # So a world in which the OPPONENTS hold all six cards of a half-suit that
    # is still unresolved is less likely than the count constraints alone would
    # suggest. It is not impossible - they may hold it and not be able to place
    # it - so this is a soft weight, not a constraint, with its own parameter.
    # Only the opponents' side is used: our own team may well hold a set without
    # us being able to prove it, which is precisely the situation this engine
    # spends its time in.
    set_cols = []
    if opp_lambda > 0.0 and order is not None:
        col_of = {c: j for j, c in enumerate(order)}
        my_team = obs.player & 1
        for hs in range(len(obs.set_winner)):
            if obs.set_winner[hs] is not None:
                continue
            lo = hs * 6
            cols = []
            possible = True
            for c in range(lo, lo + 6):
                j = col_of.get(c)
                if j is not None:
                    cols.append(j)
                    continue
                m = bel.current_holder_mask(c)
                if m == 0 or (m & (m - 1) == 0
                              and (m.bit_length() - 1) & 1 == my_team):
                    possible = False       # a card of ours, or already resolved
                    break
            if possible and cols:
                set_cols.append(tuple(cols))
    return (OpponentModel(weight, base, set_cols=set_cols,
                          opp_lambda=opp_lambda, my_team=obs.player & 1),
            card_slot)


def _attime_base(bel, obs, slots, base, include_self, me) -> None:
    """Fill ``base`` with the located depth at the moment of each ask.

    "Located" has to mean *known to the propagator*, not merely *publicly
    transferred*. A first implementation counted only cards that had visibly
    changed hands, which silently omitted every card the propagator had DEDUCED
    to be someone's - the large majority - so depths came out far too small and
    the model was much worse than the initial-deal version on both instruments
    (posterior NLL 2.14 against 1.35, and -1.54 sets per deal-pair in play).
    That was a bug, not a finding.

    The correct bookkeeping: a card's holder at time t is its deduced initial
    owner unless a successful ask moved it before t, and a card the propagator
    has NOT pinned is exactly a card the sampler will draw, so it must not be
    counted here.
    """
    from fish.engine import ClaimEvent

    n_hs = len(obs.set_winner)
    holder: dict[int, int] = {}
    for c in range(bel.n):
        cand = bel.candidates[c]
        if cand & (cand - 1) == 0:
            holder[c] = cand.bit_length() - 1
    held = [[0] * n_hs for _ in range(NUM_PLAYERS)]
    for c, o in holder.items():
        held[o][c // 6] += 1
    sums = {k: 0 for k in slots}
    hits = {k: 0 for k in slots}
    for ev in obs.history:
        if isinstance(ev, AskEvent):
            hs = half_suit_of(ev.card)
            if (include_self or ev.asker != me) and (ev.asker, hs) in slots:
                key = (ev.asker, hs)
                sums[key] += held[ev.asker][hs]
                hits[key] += 1
            if ev.success:
                prev = holder.get(ev.card)
                if prev is not None:
                    held[prev][hs] -= 1
                holder[ev.card] = ev.asker
                held[ev.asker][hs] += 1
        elif isinstance(ev, ClaimEvent):
            hs = ev.half_suit
            for p in range(NUM_PLAYERS):
                held[p][hs] = 0
            for i in range(6):
                holder.pop(hs * 6 + i, None)
    for key, i in slots.items():
        base[i] = int(round(sums[key] / hits[key])) if hits[key] else 0
