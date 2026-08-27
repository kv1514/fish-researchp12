# Pre-registration: does the endgame ask correction still pay on top of what ships?

Written before any pair of this run.

## Why this is a separate question

`endgame_m = 2, endgame_d_info = +2.0` gains **+0.0907 sets**, 95% CI
[+0.0555, +0.1260], over 4000 pre-registered pairs — against the **champion**,
`("fishbot4", {"opponent_gamma": 0.35})`.

What the site plays is `V04_COMBINED`: 480 posterior draws and a depth-3
belief-space lookahead. That lookahead searches forward from the current
position, and near the end of a hand the positions it searches are exactly the
ones this correction is about. It may already be finding some of these asks, in
which case the correction has less left to add — or nothing.

This project has asked "does it still pay on top of X" before and had the
answer come back smaller. An effect measured against a weaker base does not
transfer by assumption, and shipping it into `V04_COMBINED` on the strength of
a champion-relative number would be assuming exactly that.

## The arm

`x = V04_COMBINED`, `y = V04_COMBINED + {endgame_m: 2, endgame_d_info: 2.0}`.
Nothing else differs. 8 blocks of 250 pairs, base seeds 991000..991750, agent
seeds 9910..9917 — disjoint from 771000-772999, 881000-882999 and the
99000-99199 the weights were fitted on.

2000 pairs, not 4000. The champion-relative effect is already replicated; what
is unknown here is whether it survives, and a run that can see +0.09 can see
whether it is still there.

## What each outcome means

1. **CI entirely above 0** — it stacks. Ship into `V04_COMBINED` and into
   `api/_engine.py`'s `WEB_SPEC`, and report this interval, not the
   champion-relative one, as what the site gained.
2. **CI straddles 0 with a positive point estimate** — cannot resolve. Do
   **not** ship: the champion-relative result does not license a default change
   on a base where the effect was not demonstrated. Report both intervals and
   say plainly that the stack is unresolved.
3. **Point estimate at or below 0** — the lookahead already does this work, or
   the two interfere. Do not ship, and say which of those two the data can and
   cannot tell apart (it cannot).

The `V04_COMBINED` default and `WEB_SPEC` move only under outcome 1. No second
run under outcomes 2 or 3 — that would be running until the answer changes.

## What this cannot tell us

If the effect shrinks, that is consistent both with the lookahead already
finding these asks and with the correction being worth less when the rest of
the policy is stronger. Nothing here separates those, and neither will be
claimed.

## Amendments

None yet.
