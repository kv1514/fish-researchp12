# Pre-registration: does each side of the table deserve its own gamma?

**Registered 2026-08-29, before the paired instrument was read.** The
unpaired grid had already been run and is described under "What is already
known" below; nothing past that point had been looked at when these conditions
were fixed.

## The claim

The opponent choice model weights every other seat's asks by one exponent,
`gamma = 0.35`. That single number does two different jobs:

* on the **opponents'** side it sharpens the read that picks our next ask;
* on **our own** side it sharpens the read that places an *allocation* --- which
  of our seats holds which card of a half-suit our team already owns outright.

Two v1.0 results say those jobs should not be priced identically.

1. **95.3% of our residual errors are allocation errors** --- 0.1676 a game
   against 0.0083 ownership errors (`results/declarer_holding_self.json`).
2. **Teammate cards are worth 2.6x opponent cards.** Handed the true deal one
   side at a time, the teammate arm gains +3.41 [+3.16, +3.66] sets and the
   opponent arm +1.31 [+1.01, +1.61], at 40.7 against 40.4 cards pinned a game
   (`prereg/information_ceiling_split.md`, `results/ceiling_split.json`).

The choice model itself is *not* claimed to differ by side. It is a property of
the asker's policy, and in self-play every seat runs the same policy. What is
claimed is that `gamma` is not the model --- it is how sharply the model is
*believed as a likelihood weight* --- and that one number cannot be right for
two jobs with returns this different.

## What is already known before this registration

`scripts4/gamma_split.py` was run once, unpaired, over 60 games and 1,557
decisions. Read only as a grid of levels, it showed:

| | team NLL | team top-1 |
|---|---|---|
| incumbent (0.35, 0.35) | 1.3416 | 0.3928 |
| best team NLL (0.35, 0.70) | 1.3328 | 0.3818 |
| (0.35, 0.00) | 1.3603 | 0.3977 |

**NLL and top-1 move in opposite directions.** Raising `gamma_team` improves the
proper score and makes the posterior name the true holder *less* often; lowering
it does the reverse. No standard errors were computed, so none of these
differences is known to be real. That is what this registration is for.

This is exactly the situation in which a result gets talked into existence, so
the criteria below are fixed now.

## Design

**Instrument.** `scripts4/gamma_split.py`, 60 games, stride 4, `n_draws = 720`.
Play is the incumbent throughout; every cell scores the *same* positions, and
the truth is used only to score, never to act. The independent unit is the
**decision**, not the card: cards inside one decision share a belief and are
strongly correlated, and treating 16,342 cards as 16,342 observations would
understate the interval several times over.

**Arms.** `gamma_opp` in {0.0, 0.35, 0.7, 1.0} x `gamma_team` in
{0.0, 0.35, 0.7, 1.0, 1.5, 3.0}. Incumbent cell is (0.35, 0.35).

**Outcomes**, each a paired mean difference against the incumbent cell over the
decisions both scored, with a 95% interval:

* **Primary:** teammate-side NLL.
* **Co-primary:** teammate-side top-1 accuracy.
* Secondary, reported but not gating: opponent-side NLL and top-1, pooled NLL.

## Decision rule, fixed in advance

A cell **licenses a play experiment** only if, on the teammate pool:

1. its paired NLL interval lies **entirely below zero** (a real improvement in
   the proper score), **and**
2. its paired top-1 interval is **not entirely below zero** (it does not
   significantly worsen how often the true holder is named).

Both conditions, or nothing. Condition 2 is the one that matters and is the
reason this document exists. A model can improve NLL purely by spreading
probability mass while naming the holder correctly less often. For a policy
whose dominant error is *naming a split*, that is a worse belief, not a better
one --- the allocation decision reads the argmax, not the entropy.

**If no cell satisfies both, the direction is withdrawn and no play experiment
is run.** A cheap instrument that says no is the instrument working.

**If a cell satisfies both**, a play experiment is registered separately before
it is run, with its own ship bar. Nothing here licenses shipping; the belief
getting better does not entail the engine playing better, and this project has
already measured one case where it did not (the at-ask-time covariate, better
on the posterior and worth nothing in play).

## Withdrawal conditions

* Any cell whose improvement is not monotone in `gamma_team` in a neighbourhood
  of the optimum is treated as noise, not signal.
* If the best cell is on the boundary of the grid, the grid is widened and the
  run repeated; a boundary optimum is not reported as an optimum.
* If the incumbent cell's own team/opp pool sizes differ by more than 5x, the
  comparison is reported as underpowered on the smaller pool.

## What a null would mean

That the two jobs are not separable by a scalar. That would not refute the
underlying ceiling-split finding --- teammates would still be worth 2.6x --- but
it would say the route to that value is not "believe the same model harder on
one side". The remaining routes are a genuinely different teammate model
(conditioning on our own policy's likelihood rather than a depth heuristic,
task #53) or a change to the declaration policy rather than to the belief.

---

# OUTCOME, recorded 2026-08-29

**The split is REFUTED on its own pre-registered rule, and refuted in the
direction opposite to the one predicted.**

`results/gamma_split.json`, 60 games, 1,557 decisions, 16,342 teammate-pool
cards and 24,565 opponent-pool cards. Paired by decision against the incumbent
cell (0.35, 0.35).

## The hypothesised direction fails

The prediction was `gamma_team > gamma_opp`: teammate reads are worth 2.6x
opponent reads, so believe the teammate model harder. That cell is (0.35, 0.70):

| | paired difference vs incumbent |
|---|---|
| teammate NLL | **-0.0119** [-0.0150, -0.0088] |
| teammate top-1 | **-0.0093** [-0.0128, -0.0057] |

Condition 1 passes and **condition 2 fails**: the top-1 interval lies entirely
below zero, so the posterior names the true holder *less* often. This is exactly
the failure the co-primary was written to catch, and it is why it was written
before the numbers were read. The NLL gain is mass being spread, not the read
improving, and the allocation decision reads the argmax.

## Two cells pass both conditions, and neither is the hypothesis

| cell | dNLL (team) | dtop1 (team) | |
|---|---|---|---|
| (0.70, 0.35) | -0.0036 [-0.0070, -0.0003] | +0.0070 [+0.0025, +0.0115] | off-diagonal |
| (0.70, 0.70) | **-0.0121** [-0.0173, -0.0069] | +0.0004 [-0.0047, +0.0055] | **diagonal** |

The best passing cell is **on the diagonal**. `gamma = 0.70` on both sides beats
every split in the grid, including the off-diagonal cell that passes, by more
than 3x. So what this run found is that the incumbent `gamma` is too low --- not
that the two sides deserve different numbers.

The one off-diagonal cell that does pass has `gamma_team < gamma_opp`: believe
the teammate model *less*. That is the reverse of the hypothesis, its effect is
a third the size of the diagonal cell's, and its interval very nearly touches
zero. It is not evidence for a split in any useful sense.

## This is not even a new result about gamma

Table~\ref{tab:posterior} in the paper already reports the posterior sweep that
found `gamma = 0.45`-`0.60` beating `0.35` on NLL. The engine ships `0.35`
anyway, because the belief improving did not carry into play. So the diagonal
cell here **replicates a known belief-side result on a new pool** and licenses
nothing: that road was already walked.

## Verdict

**Withdrawn. No play experiment is run.** The direction is closed as specified
under "What a null would mean":

> That the two jobs are not separable by a scalar. That would not refute the
> underlying ceiling-split finding --- teammates would still be worth 2.6x ---
> but it would say the route to that value is not "believe the same model
> harder on one side".

That is precisely what happened. The teammate value measured by the ceiling
split is real and remains unclaimed; reweighting the existing depth heuristic is
not the way to it. The remaining routes are unchanged:

* a genuinely different teammate model --- conditioning on our own policy's
  likelihood rather than on a depth heuristic (task #53), which is the only
  route that uses the fact that our teammates run *our* policy and we possess
  it; or
* a change to the declaration policy rather than to the belief, which
  `results/declarer_holding_self.json` argues against: every voluntary and
  exact-path declaration is already correct, so there is no calibration left to
  win there.

## What the instrument cost, and what it bought

Two runs of about twenty minutes each. It bought the refutation of a direction
that had two strong published results pointing at it, before a single duel was
played. The first run, unpaired, would have licensed the play experiment: its
grid showed the best team NLL off the diagonal and said so. Pairing by decision
and adding the top-1 co-primary is what turned a licence into a withdrawal.
