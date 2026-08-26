# Pre-registration: what the corrected solver should do to the m = 1 numbers

Written 2026-08-26, with all three re-runs in flight and none of them past
game 20 of 200. Registered because I have made six pre-data predictions in this
project and hit one, and the one I hit was the only one where the mechanism was
provable rather than argued. This one is argued.

## What changed

`fish4/exact_ii.ExactII`'s memo key omitted the history. The champion opponents'
policy is a function of their whole observation, so two nodes with identical
hands, turn, winners and weights but different histories are different nodes.
Merging them returned one branch's value for the other, and the maximisation
read those values.

## The numbers on the table

`results/ii_endgame.json`, 200 games, computed by the broken search:

    pinned control        344/344
    solved                308  (13 skipped, 0 timed out)
    mean optimum          +0.5129
    mean champion         +0.0670
    mean gain             +0.4459
    negative gains        0/308

## Predictions

1. **The pinned control stays 344/344.** Where the support is one deal there is
   nothing hidden, and the control already passed on both solvers.

2. **`mean_champion` lands within 0.02 of +0.0670.** `champion_value` is a
   rollout and never touched the memo, so this figure was never corrupt. It can
   still move a little, because it is averaged over the positions that got
   *solved*, and which positions those are will change (see 4).

3. **`n_solved` falls below 308.** The corrected search visits roughly eighty
   times more nodes -- 12,086 against 154 on the position I diagnosed -- and the
   per-position deadline is unchanged at 60s. Positions that used to finish
   will now time out. At m = 2 this is already visible: a support-19 position
   the broken search "solved" in seconds now exceeds 45s.

4. **`mean_optimum` and `mean_gain` come out HIGHER than +0.5129 and +0.4459.**
   This is the weak one and the one to watch. Both corruptions I actually
   observed deflated the maximum -- +0.2500 against a true +0.7500, and +0.0000
   against a true +0.5000 -- because a stale value that is too low drags the max
   down while a stale value that is too high would raise it. I have two cases,
   both in the same direction, at m = 2, and no argument that the direction is
   systematic. If the corrected gain comes back *lower*, the deflation was a
   coincidence of two samples and I should say so rather than explain it away.

5. **Zero negative gains, and the tree/rollout control agrees everywhere.**
   These are now hard failures, so the alternative is that no results file is
   written at all.

## What would make me wrong in an interesting way

If `mean_gain` moves by less than 0.01 in either direction, then the memo bug
-- which is real, reproducible, and worth eighty-fold in nodes -- had almost no
effect on the aggregate at m = 1, and the interesting question becomes why m = 2
was so much more sensitive to it than m = 1. The obvious answer would be that
twelve live cards transpose far more than six.
