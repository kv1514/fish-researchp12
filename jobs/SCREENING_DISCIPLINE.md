# What a screening cell is allowed to conclude

Nothing. That is the rule, and it exists because this project has now made the
same mistake three times, each time one level above where it was last caught:

1. A 200-pair screening cell resolved the lookahead at $+0.570$ and failed to
   replicate.
2. A paper section was built on a $Q$ statistic over three cells; a 24-block A/A
   study then measured $\tau = 0$ and coverage 23/24, refuting it.
3. The run written to *correct* the first error was sized against an effect
   estimate that included the selected cell, so it was under-powered and came
   back inconclusive.

All three are the winner's curse. The third was committed inside the correction
for the first.

So the cells in `j21_screen_followon.json` are **screens**. A screen may do
exactly one thing: decide whether a hypothesis is worth a pre-registered run.
It may not:

- appear in the paper as an effect estimate,
- be pooled with a later confirmatory run,
- or be used to size that run.

At 400 pairs the MDE is about $0.37$ sets per deal-pair against the measured
per-pair SD of $3.796$. That is large. A screen that comes back at $+0.2$ has
measured nothing; a screen that comes back at $+0.8$ has earned a
pre-registration, not a result.

## The cells, and what each is for

**`precision half n_draws 80 vs 160`** is deliberately first and deliberately
backwards. `results/precision_scaling.json` shows posterior L1 error falling as
$n^{-0.475}$ with no bias floor from 40 to 1280 draws, so precision is available
for purchase. Whether the *policy* can feel it is a different question, and the
cheapest way to ask it is to take precision away: halving the draws runs faster
than the baseline, so this cell costs less than the one it screens for. If 80
draws play level with 160, the axis is closed and the expensive direction need
never be run.

**`precision triple n_draws 480 vs 160`** is the expensive direction, run last
so the cheap cell can cancel it.

**`gamma_schedule 0.4` and `0.8`** test whether an ask early in a game is better
evidence of depth than an ask late, by re-weighting the opponent choice model's
per-ask likelihood by the fraction of half-suits already resolved. The model is
the largest effect in the engine at $+1.9$ sets per deal-pair, which is why a
better-specified version of it is worth asking about at all.

Note that these two cells are **not** independent tests of one idea: they are two
strengths of the same term, and taking the better of the two is itself a
selection. If either looks promising the pre-registered run must fix the strength
in advance, and the honest choice is the one whose mechanism was argued for
before the numbers arrived, not the one that scored higher.
