# Pre-registration: is posterior precision worth buying?

Written **before the `n_draws=480` screening cell finished**, deliberately. The
lookahead took four rounds to settle partly because its confirmatory run was
sized against a number the screen had inflated, and the only reliable way not to
repeat that is to fix the design before the number exists.

## What is already known, and what is not

`results/precision_scaling.json`: posterior L1 error per card falls as
$n^{-0.475}$ from 40 draws to 1280, with no bias floor. That is the pure Monte
Carlo law, so the sampler is unbiased and precision is nowhere near saturated at
the operating point of 160 draws. It says the error is available for purchase.
It says nothing about whether the policy can feel it.

`results/ess_probe.json`: at the champion configuration, 160 draws are worth
83.7 effective, and the exact DP is reached in 9 decisions out of 641. So the
precision of every $P(\text{success})$ in the engine is the precision of that
one sampled batch.

The screening cell at `n_draws=80` — the cheap direction, taking precision away
— has run. Under `jobs/SCREENING_DISCIPLINE.md` it may decide whether this
hypothesis earns a pre-registration and may **not** be used to size the run.

## Hypothesis

`fishbot4(opponent_gamma=0.35, n_draws=480)` scores a positive set differential
against the identical policy at `n_draws=160`.

## Effect size assumed for sizing

**+0.15 sets per deal-pair**, and this is a *minimum interesting effect*, not an
estimate. It is chosen before the data and on grounds independent of them:
$+0.15$ is roughly what the belief-space lookahead turned out to be worth, and
tripling the sampling budget costs about three times the inference time per
decision. An effect smaller than the one already-shipped feature delivers, for
that price, is not a thing this engine should adopt.

Sizing against a threshold rather than an estimate is the point. No screening
cell contributes a number to this calculation, so there is no estimate for
selection to inflate.

## Design

- **6 blocks × 1000 pairs = 6000 duplicate deal-pairs**, fresh seeds throughout.
- Per-pair standard deviation **3.796**, from the 4800 A/A pairs.
- **MDE at 80% power is 0.137**, comfortably under the 0.15 threshold.
- The cost is real and is part of the decision: at 480 draws each deal-pair
  costs roughly three times a baseline pair, so this run is worth about 18,000
  baseline pairs of machine time. It is the most expensive experiment in the
  study and is being run once.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 6 blocks. Every block is unselected, so
no cell may be dropped for its result. The effect is **demonstrated** if and
only if this 95% interval excludes zero.

**Homogeneity check.** Cochran's $Q$ across the 6 blocks, diagnostic only, read
the same way as in the lookahead pre-registration.

**Reported alongside, not decisive.** The `n_draws=80` screening cell, as
context on the shape of the response, explicitly labelled as a screen.

## Committed in advance

- No cell will be excluded on the basis of its result.
- If the primary interval includes zero, the result is **not demonstrated**,
  whatever the screening cell said.
- No further run will be added to chase significance.
- A demonstrated effect does **not** automatically change the default. `n_draws`
  trades strength against latency, and the public table has a request budget;
  the decision to move the default is separate from the decision about whether
  the effect is real, and will be made with the measured cost in hand.
