# Pre-registration: how far up does the ask correction go?

Written before any pair of the m = 4 run.

## Why a ladder needs registering at all

Two steps are now measured, and the effect is **growing**:

| step | in play | 95% CI |
|---|---|---|
| m ≤ 1 → m ≤ 2 | +0.1220 | [+0.0711, +0.1729] |
| m ≤ 2 → m ≤ 3 | +0.3025 | [+0.2271, +0.3779] |

The obvious next move is to try 4, then 5, and stop when it stops working. Done
without a rule that is exactly the screening failure this project has already
documented once: trying values until one looks good, and reporting that one.

So the rule is fixed here, before the next value is tried.

## The ladder, and the stopping rule

Each step is a duel of `endgame_m = k+1` against the **currently shipped**
`endgame_m = k`, everything else identical, `endgame_d_info = +2.0`
**never refitted**. 8 blocks of 250 pairs, 2000 pairs, base seeds
991000 + 250·block for k+1 = 4 and a fresh disjoint range for each later step.

* **CI entirely above 0** — ship `k+1` and take the next step.
* **Anything else** — stop. Do not ship, do not try `k+2`, do not re-run with
  more pairs. The ladder ends at the last value that cleared.

**Every step is reported, including the one that ends the ladder.** The
stopping step is a result, not a discarded attempt: it says where in the game
the defect the exact solver found stops converting into play.

## What the ladder cannot tell us

Three things, stated now so they are not discovered as caveats later.

1. The weight is fixed at `+2.0` throughout. A step that fails may mean the
   defect stops, or may mean `+2.0` is the wrong size there. This design cannot
   separate those, and will not claim to.
2. Offline evidence exists only to m = 3. One sampled target costs ~19 s of
   rollout at m = 3 but ~162 s at m = 4 and ~1955 s at m = 9, so from m = 4 the
   ladder is running **without** a prior diagnosis that the defect is present —
   the play test is the only evidence.
3. Each step is measured against the previous rung, not against the original
   champion. The cumulative figure is not the sum of the steps, and no
   cumulative number will be quoted without measuring it directly.

## Engine integrity

Every block records an engine digest. The m = 3 run had two blocks
contaminated by agents editing the engine in the working tree while the duels
ran; they were caught by that digest and re-run. **No agent with write access
runs against this repository while any block of this ladder is in flight**, and
pooling refuses to mix digests.

## Amendments

None yet.

## Amendment 1 — one coarse step to the top, recorded before it runs

Four rungs have now cleared, each larger than the last:

| rung | in play | 95% CI |
|---|---|---|
| m ≤ 1 → 2 | +0.1220 | [+0.0711, +0.1729] |
| m ≤ 2 → 3 | +0.3025 | [+0.2271, +0.3779] |
| m ≤ 3 → 4 | +0.6995 | [+0.6033, +0.7957] |
| m ≤ 4 → 5 | +1.0125 | [+0.8961, +1.1289] |

The remaining span is m = 6, 7, 8, 9, and m = 9 is "always on" — at that point
`endgame_d_info` stops being an endgame correction and becomes a change to the
ask objective itself. Four more rungs at 2000 pairs each would spend eight
thousand pairs establishing what four monotone, accelerating, individually
significant rungs already make the strong default expectation.

**The amendment:** the next step is m ≤ 5 → m ≤ 9 in one duel, same size, fresh
seeds (661000+, agent seeds 6611+).

* **CI above 0** — ship `endgame_m = 9`. The intermediate rungs 6–8 are then
  never individually measured, and no per-rung figure will be claimed for them.
* **CI not above 0** — the coarse step is treated as the ladder's stop at m = 5,
  and one bisection at m = 7 is run to locate the turn, after which the ladder
  ends regardless of that outcome. This is the only situation in which a
  further value is tried after a failure, and it is fixed here in advance.

The stopping rule is otherwise unchanged. What is being traded away is
resolution about WHERE the gain stops growing between 5 and 9, in exchange for
four thousand fewer pairs; if the coarse step clears, that resolution is gone
for good and this amendment is why.
