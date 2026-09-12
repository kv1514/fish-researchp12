# Pre-registration: is a null recoverable by waiting?

Written 2026-08-25, before any of the data below exists.

## What the proof changed

`scripts4/closed_form_proof.py` establishes two rules-level facts:

* **A** a team holding no card of half-suit *h* can never acquire one;
* **B** every claim such a team can make on *h* awards *h* to the opponents.

`fish/engine.py::_apply_claim` awards NULL only when the whole half-suit is on
the claiming team and the declared split is wrong. So **every null in this
project's history is a mis-split of a half-suit the claiming team already
wholly owned** -- and by A and B that half-suit could not have been taken away.
Waiting was free. Each null therefore threw away exactly 1 of differential for
nothing, and at 0.274 nulls per game that is larger than the biggest engine
improvement this project has ever demonstrated (+0.340 per deal-PAIR, so
+0.170 per game).

That does not mean nulls are a lever -- `scripts4/null_lever.py` already
refuted the cross-arm correlation as a confound of policy quality. It means the
*mechanism* is now known exactly, which the correlation never established, and
a mechanism can be checked directly instead of correlated.

## The question

At the moment of each null, was the correct split knowable, and if not, did it
become knowable later while the half-suit was still live?

## What will be recorded

For every null in the games played, at the moment of the claim:

1. `forced` -- whether `must_claim` was true for the claimer. A forced claim
   cannot be deferred by any policy, so these bound what waiting could ever fix.
2. `p_true` -- the claimer's posterior probability of the TRUE split.
3. `argmax_correct` -- whether the claimer's most likely split was the true one.
   If it was, the null is a selection bug, not an information problem.
4. `rank_true` -- the rank of the true split in the claimer's posterior.

Then the game is replayed forward from the claim with the half-suit left
unclaimed, and at every subsequent decision of any member of the claiming team:

5. `recovered` -- whether that seat's argmax split becomes the true one at any
   later point while the half-suit is still live and the team still holds it.
6. `steps_to_recovery` -- how long that took, in that team's own decisions.

## The rule fixed in advance

Waiting is worth building as a policy change only if

> **at least 30%** of non-forced nulls are `recovered`

Below 30% the information does not arrive and deferring the claim would trade a
null for a later null; I will report that and drop the line rather than look for
a subgroup where it works. If `argmax_correct` is above 10% the finding is a
selection bug instead and takes priority over any waiting policy.

## What this is not

This is a descriptive study of a mechanism, not a duel. It cannot say what a
deferring policy scores; if the 30% bar is cleared, that requires a separate
pre-registered duel against the champion at the usual sizes. Nothing here
licenses a strength claim.
