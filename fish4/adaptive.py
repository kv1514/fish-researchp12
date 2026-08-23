"""Playing style that responds to the match, rather than one fixed objective.

Every objective term in v0.4 is a function of a candidate ask and the posterior.
None of them knows the score, and none of them knows that the last four moves
were the same two players passing one card back and forth. Two ideas here, both
ablatable to zero, both measurable on their own.

1. THE DUEL, AND WHETHER TO BREAK IT
------------------------------------
``perpetual.py`` establishes that the state graph is cyclic precisely because two
opponents can trade a card back and forth forever. It treats that as a fact about
the rules. What it does not ask is whether a *player* should enter such a trade.

The greedy answer is obviously yes: a card you just watched an opponent take from
you is a card you know they hold, so asking for it back is a certain ask, and a
certain ask keeps your turn. Descending probability is how you bank the most
cards before a miss, and re-taking is the top of that order by construction.

The case against is not about this turn. It is that the exchange is *public*, and
repeating it tells the table that this half-suit is contested and that both of
you are still in it - while gaining neither side a net card across the cycle. A
player who breaks the pattern spends a certain ask now in exchange for the
opponents learning less about where the suit lives.

``w_retake`` prices that. It is a penalty on an ask that would take back a card
this seat lost to that same opponent inside a recent window. Set it to zero and
the policy is the incumbent, exactly.

We expect this to lose. The scheduling argument says the certain ask should come
first, and v0.4 already reports its two information terms (``reveal``,
``signal``) as nulls. It is worth measuring anyway, because those two terms are
*static* per-ask features while this one is a fact about the recent history, and
because "hold the card back" is a thing strong human players describe doing and
the engine currently cannot express at all.

2. THE SCORE
------------
The champion plays a 5-1 lead exactly as it plays a 1-5 deficit. That is unlikely
to be right. A team that is behind needs variance and should prefer the ask that
resolves the most uncertainty even at a lower success probability; a team that is
ahead wants the game to end and should prefer certainty and early claims.

``w_behind`` scales the tie-breakers by the score differential: positive values
make a losing team play for information and a winning team play safe. At zero the
weights are the incumbent's constants and nothing changes.

Both quantities are computed from the public record and this seat's own hand.
Nothing here reads a layout.
"""

from __future__ import annotations

import numpy as np

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import AskEvent

#: How far back an exchange still counts as part of the same duel. Eight plies is
#: a little over one full circuit of the table, so a trade that survives it is
#: recurring rather than incidental.
DEFAULT_WINDOW = 8


def recent_losses(obs, window: int = DEFAULT_WINDOW) -> set:
    """``(opponent, card)`` pairs this seat lost to that opponent, recently.

    A successful ask whose target was us is a card leaving our hand, and the
    whole table saw it. Asking for it back is the re-take this module is about.
    """
    me = obs.player
    out = set()
    hist = obs.history
    for ev in hist[-window:] if window else hist:
        if isinstance(ev, AskEvent) and ev.success and ev.target == me:
            out.add((ev.asker, ev.card))
    return out


def retake_flags(obs, asks, window: int = DEFAULT_WINDOW) -> np.ndarray:
    """1.0 for each candidate ask that would take back a recently lost card."""
    lost = recent_losses(obs, window)
    if not lost:
        return np.zeros(len(asks))
    return np.array([1.0 if (a.target, a.card) in lost else 0.0 for a in asks])


def duel_depth(obs, window: int = DEFAULT_WINDOW) -> int:
    """How many times a card has changed hands between us and one opponent.

    Counts successful asks inside the window that moved a card either way
    between this seat and a single opponent. Two or more is a duel rather than
    an exchange.
    """
    me = obs.player
    seen: dict = {}
    hist = obs.history
    for ev in hist[-window:] if window else hist:
        if not (isinstance(ev, AskEvent) and ev.success):
            continue
        if ev.target == me:
            seen[ev.asker] = seen.get(ev.asker, 0) + 1
        elif ev.asker == me and team_of(ev.target) != team_of(me):
            seen[ev.target] = seen.get(ev.target, 0) + 1
    return max(seen.values()) if seen else 0


def score_pressure(obs) -> float:
    """How far behind this seat's team is, as a share of the sets decided.

    ``+1`` when every decided set went to the opponents, ``-1`` when they all
    came to us, ``0`` at level or before anything is decided. Nulled sets count
    for neither side, which is what the rules say they do.
    """
    mine = team_of(obs.player)
    ours = theirs = 0
    for w in obs.set_winner:
        if w is None or w not in (0, 1):
            continue
        if w == mine:
            ours += 1
        else:
            theirs += 1
    decided = ours + theirs
    return 0.0 if decided == 0 else (theirs - ours) / decided


def adjust_weights(weights, obs, w_behind: float):
    """Scale the tie-breakers by how far behind we are.

    A losing team should want the ask that resolves the most, even at a lower
    chance of landing; a winning team should want the game over. Both are
    expressed by scaling the *tie-breakers* rather than by touching
    P(success), because the paper's sharpest result is that P(success) is the
    objective and everything else is a tie-break - so this changes how the
    tie-breaks are weighed and leaves the objective alone.

    Returns ``weights`` unchanged when ``w_behind`` is zero, which is what makes
    the option ablate exactly.
    """
    if not w_behind:
        return weights
    k = 1.0 + w_behind * score_pressure(obs)
    # Never invert a term's sign: at that point it is a different idea, not a
    # scaled one, and the ablation would no longer be measuring one thing.
    k = max(0.0, k)
    return weights.__class__(
        **{f: getattr(weights, f) * k for f in weights.__dataclass_fields__})
