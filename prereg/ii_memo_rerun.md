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

## Amendment, same day, before any run reached game 20

The budget changed from 60 seconds to 300,000 nodes, and all three runs were
restarted from zero. The reason is in the commit: the 21% timeout rate that
prediction 3 rests on was measured with three studies competing for four cores,
so it was a fact about the machine. Predictions 1, 2, 4 and 5 are unaffected.

Prediction 3 is restated: **`n_solved` still falls below 308**, and the
positions that fail to solve are those needing more than 300,000 nodes. What I
can no longer predict is the exact rate, because 300,000 nodes is a different
budget from 60 seconds and I have not measured how they compare on an unloaded
machine. Recording that I amended this rather than quietly leaving the old
sentence to be graded against a protocol it was not written for.

---

# Graded, after the run

    pinned control        344/344   (was 344/344)
    tree/rollout control  601/601   (new)
    solved                305       (was 308; 13 skipped, 3 over budget)
    mean optimum          +0.5084   (was +0.5129)
    mean champion         +0.0679   (was +0.0670)
    mean gain             +0.4405   (was +0.4459)
    negative gains        0/305

**1. Pinned control stays 344/344.** Hit.

**2. `mean_champion` within 0.02 of +0.0670.** Hit: +0.0679, and on the matched
positions it is identical to twelve decimal places, position for position,
which is the stronger statement.

**3. `n_solved` falls below 308.** Hit, but only just, and for a reason I did
not predict: 305, with three positions over the node budget rather than the
much larger loss the raw eighty-fold node increase implied. The exact cutoff
added after this was written paid the increase back. Coverage is 95%, against
the 96% of the broken run.

**4. `mean_optimum` and `mean_gain` come out HIGHER.** **Missed.** Both came
out lower. This is the one I flagged as argued rather than provable, from two
observed cases that both deflated the maximum, and I wrote that if the gain
came back lower I should say the deflation was a coincidence of two samples
rather than explain it away. It was a coincidence of two samples.
`scripts4/ii_memo_effect.py` says so directly: on the 304 positions both runs
solve, the fix RAISED the optimum in 24 and LOWERED it in 19. A stale value is
as likely to be too high as too low, which in hindsight is the only thing the
mechanism ever implied.

**5. Zero negative gains, controls agree everywhere.** Hit: 0/305 and 601/601.

## The clause that fired

> If `mean_gain` moves by less than 0.01 in either direction, then the memo bug
> had almost no effect on the aggregate at m = 1, and the interesting question
> becomes why m = 2 was so much more sensitive to it.

On the matched positions the gain moved **0.0011**. So the bug -- real,
reproducible, worth eighty-fold in nodes, and fatal at m = 2 -- changed the
m = 1 headline by about a thousandth of a set.

It was not harmless. It corrupted **43 of 304** individual positions, 14% of
them. The aggregate survived because the errors went both ways and cancelled,
which is luck, not soundness: nothing about the mechanism guaranteed it, and at
m = 2 the same fault produced values so wrong they violated a bound that cannot
be violated. Twelve live cards transpose far more than six, so there are more
merges and larger errors, and past some size the cancellation stops rescuing
the mean.

The general lesson is the uncomfortable one. If I had checked this bug by
looking at whether the headline moved, I would have concluded there was no bug.
The invariant found it because it is evaluated per position and does not care
about the mean.

## Score

Four of five, and the one that missed is the one whose mechanism was argued
rather than provable. That is now seven pre-data predictions in this project
with two hits, and both hits had a provable mechanism behind them.
