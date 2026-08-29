"""A pre-play agreement that makes an ask say how deep the asker is.

WHAT THIS IS. Literature forbids communication during play. It does not forbid
agreement before it, which is exactly the licence a bridge bidding convention
runs on, and \\S\\ref{sec:limitations} names TMECor -- equilibrium with pre-play
correlation and no in-play channel -- as the right solution concept for this
game while recording that nothing in this project approximates it. This module
is the smallest concrete thing that does.

THE CHANNEL IT USES. The rules force an asker to name a *specific* card, and
within the half-suit they have chosen that pick is free. Measured over 3,883
asks in 40 self-play games (`results/convention_cost.json`): a mean of 3.57
legal cards to choose between, so 1.72 bits per ask, spent entirely on expected
value today. The cost of using the channel is wildly skewed -- median 0.022
probability, p90 0.616 -- and at a best-to-worst spread of 0.02 there are 19.3
bits per game going spare. Locating one card among six players is about 2.6
bits, so that is roughly seven cards' worth of free location information per
game.

WHAT IT SAYS. The asker's *depth* in the half-suit they are asking in. That
quantity is the entire content of the shipped opponent model, which guesses it
from a fitted exponent and is worth 6,055 held-out nats for doing so
(`results/choice_basis.json`). Saying it outright is strictly more than any
exponent can infer.

    encode:  among the cards of H this seat does NOT hold, sorted by index,
             name the one at position (held - 1) mod k, where k = 6 - held.

The receiver cannot invert that directly, because k depends on `held` which is
what it is trying to learn. It does not need to. For each candidate world it
knows the hypothesised hand, so it can ask the forward question -- "under this
world, is the card actually named the one the convention would have chosen?" --
and weight the world accordingly.

WHY THE WEIGHT IS SOFT, WHICH IS THE LOAD-BEARING DECISION. A hard decode would
be a catastrophe. The sender only encodes when the channel is cheap, and
cheapness is computed from the sender's *own* belief, which the receiver cannot
reproduce; so the receiver never knows for certain whether a given ask was
carrying a message or being played for value. Under a hard decode, every
unencoded ask would inject a false constraint into the belief and the
propagator would happily eliminate the true world. Under a soft weight, an
unencoded ask merely tilts the posterior slightly the wrong way, which is the
same failure mode the existing choice model already has and survives.

That asymmetry -- a constraint can be fatally wrong, a likelihood can only be
mildly wrong -- is why this ships as a weight in the importance sampler rather
than as a rule in the propagator.

EVERY PARAMETER HERE IS ZERO BY DEFAULT and the engine is bit-identical with
them unset.
"""

from __future__ import annotations

from fish.cards import half_suit_cards  # noqa: F401  (re-exported)


def legal_cards(hand: int, half_suit: int) -> list[int]:
    """Cards of the half-suit this hand does NOT hold, in index order.

    These are exactly the cards the holder could legally ask for in that
    half-suit, which is what makes the position of the named card a symbol
    both sides can agree on.
    """
    return [c for c in half_suit_cards(half_suit) if not (hand >> c & 1)]


def depth_in(hand: int, half_suit: int) -> int:
    return sum(1 for c in half_suit_cards(half_suit) if hand >> c & 1)


def encoded_card(hand: int, half_suit: int) -> int | None:
    """The card the convention names, given this hand and half-suit.

    ``None`` when the seat holds every card of the half-suit, where no ask is
    legal and there is nothing to say.
    """
    free = legal_cards(hand, half_suit)
    if not free:
        return None
    held = 6 - len(free)
    # (held - 1) so that a seat holding one card names the first free card,
    # which is the commonest case and keeps the modal message on the modal
    # choice: it makes the convention agree with unconstrained play more often
    # than an arbitrary offset would, and every agreement is a free message.
    return free[(held - 1) % len(free)]


def is_encoded(hand: int, half_suit: int, card: int) -> bool:
    """Would this hand, under the convention, have named this card?

    This is the receiver's forward test. It never needs to invert the
    encoding: for each candidate world it has a hypothesised hand, so it can
    simply ask what that hand would have said.
    """
    enc = encoded_card(hand, half_suit)
    return enc is not None and enc == card


def encode_cost(marginals, hand: int, half_suit: int, opponents) -> float:
    """Probability of success given up by naming the convention card.

    The sender's gate. ``marginals[c][p]`` is P(player p holds card c), which
    is what the engine's posterior already provides. Returns the drop from the
    best legal (card, target) pair to the convention's, so zero means the
    convention card was the best one anyway and the message is free.
    """
    free = legal_cards(hand, half_suit)
    if not free:
        return 0.0
    best = max(max(marginals[c][q] for q in opponents) for c in free)
    enc = encoded_card(hand, half_suit)
    got = max(marginals[enc][q] for q in opponents)
    return best - got


def encoded_position_table() -> tuple[int, ...]:
    """``table[mask]`` = position in the half-suit the convention would name.

    ``mask`` is a six-bit holding of one half-suit, bit ``i`` set when the seat
    holds the card at position ``i``. The value is that same kind of position,
    or ``-1`` when the seat holds all six and no ask is legal.

    The encoding depends on a holding's SHAPE and not on which half-suit it is
    in, so one 64-entry table serves every half-suit. This exists so the
    vectorised sampler can apply the convention with a gather instead of a
    Python loop over drawn worlds, and it is built by calling ``encoded_card``
    itself -- half-suit 0's cards are exactly positions 0..5 -- so the two paths
    cannot drift apart. ``tests4/test_convention.py`` pins that.
    """
    return tuple(-1 if (e := encoded_card(mask, 0)) is None else e
                 for mask in range(64))


# ---------------------------------------------------------------------------
# The mixture likelihood
# ---------------------------------------------------------------------------
#
# The flat weight above -- add `beta` when the named card is the convention's
# card, add nothing otherwise -- is a heuristic, and it is mis-specified in a
# way that shows up in exactly the statistic this project cares most about.
#
# Write the likelihood of the observed card `c`, given the half-suit is already
# chosen and given a candidate world `w`:
#
#     P(c | w) = q * 1[c == enc(w)] + (1 - q) * u(c | w)
#
# `q` is the probability this ask carried a message at all -- the SENDER'S CARRY
# RATE, which is measurable (0.53 to 0.68 across the gates in
# prereg/convention.md) and is not a free parameter. `u` is how the sender picks
# a card when not encoding; modelling it as uniform over the k(w) legal cards is
# the same cheap surrogate the depth model already makes one level up, at the
# half-suit rather than the card.
#
# TWO THINGS THE FLAT WEIGHT GETS WRONG, both of them about k(w) = 6 - held(w):
#
#   1. A match is weaker evidence when the asker has few legal cards, because a
#      coincidence is likelier. The log-odds of a match against a non-match is
#
#          log(1 + q*k/(1-q))
#
#      which GROWS with k. The flat weight scores every match at `beta`
#      regardless, so it over-credits matches in the low-k worlds -- the worlds
#      where the asker is DEEP. That is a systematic push of posterior mass
#      towards deep teammate holdings, and the allocation decision reads the
#      argmax.
#   2. A non-match is not uninformative. `log((1-q)/k)` still varies with k, so
#      failing to name the convention card is evidence about depth too. The flat
#      weight gives every non-match exactly zero.
#
# `convention_q = 0` means NO AGREEMENT EXISTS and the term is skipped entirely.
# That is not the q -> 0 limit of the formula, and deliberately so: with no
# agreement the card choice is the objective's, not uniform, so neither branch
# of the mixture describes it.


def mixture_logp(k: int, match: bool, q: float) -> float:
    """log P(named card | world), under the mixture. ``k`` is 6 - held."""
    import math
    if k <= 0:
        return 0.0
    p = (q if match else 0.0) + (1.0 - q) / k
    return math.log(p) if p > 0.0 else -30.0


# ---------------------------------------------------------------------------
# Aiming the channel
# ---------------------------------------------------------------------------
#
# The code book above says the asker's depth in the half-suit THEY JUST ASKED
# IN. That is the half-suit the receiver already knows most about: the no-bluff
# rule constrains it, the choice model scores it, and the propagator has usually
# pinned it outright. Measured over 176 (position, asker) pairs, the sampler's
# entropy over the asker's depth is
#
#     0.2124 nats in H, the half-suit asked in     -- already certain 72.2%
#     0.8556 nats in G, the most-unlocated one     -- already certain  9.7%
#
# a factor of 4.03. So the convention spends 1.72 bits an ask saying something
# the receiver already knows three times in four, which is the most likely
# reason its measured effect on the belief is real but small.
#
# A code book can say anything both sides agreed on in advance; it does not have
# to be about the half-suit the ask is in. Aiming costs nothing extra -- the same
# card, the same turn, the same legality -- and points the same 1.72 bits at a
# quantity with four times the entropy.
#
# THE TARGET HAS TO BE COMMON KNOWLEDGE, or the two sides would not agree on
# what is being talked about. `unlocated` -- how many cards of a half-suit the
# public record cannot place -- is exactly that, and is the covariate worth
# +6,736 held-out nats on its own in prereg/choice_basis.md. G is the half-suit
# with the most unlocated cards, ties to the lower index.
#
# AND IT HAS TO BE THE TARGET AS OF THE ASK. The public record moves, so a
# receiver decoding later must reconstruct the G the sender was looking at, the
# same way it reconstructs the holding the sender had. oppmodel.build snapshots
# both as it walks the log.


def encoded_position(payload: int, k: int) -> int:
    """Which of the ``k`` legal cards, in index order, carries ``payload``.

    The single point where a code book becomes a position. The unaimed
    convention passes ``held - 1``; the aimed one passes the asker's depth in
    the target half-suit.
    """
    return payload % k if k > 0 else 0


def aimed_position_table():
    """``table[mask][payload]`` = position named, for every holding and payload.

    ``mask`` is the six-bit holding of the half-suit being ASKED in, ``payload``
    is 0..6 (a depth). ``-1`` where the seat holds all six and no ask is legal.
    Shape (64, 7), so the vectorised sampler applies an aimed code book with the
    same single gather the unaimed one uses.
    """
    out = []
    for mask in range(64):
        free = [i for i in range(6) if not (mask >> i & 1)]
        if not free:
            out.append([-1] * 7)
        else:
            out.append([free[encoded_position(pl, len(free))]
                        for pl in range(7)])
    return out
