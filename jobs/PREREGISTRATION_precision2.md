# Pre-registration: does precision keep paying past 480 draws?

Written **before any pair of this run has been played**.

## What the last rung established

`fishbot4(n_draws=480)` beats the same policy at 160 by **+0.340 sets per
deal-pair, 95% CI [+0.243, +0.436]** over 6000 pre-registered pairs, homogeneous
at I² = 0%. That is the largest effect in the project and it is now shipped:
`WEB_DRAWS = 480`, `V04_PRECISE` in the registry.

Two prior measurements say the rung above may also be there:

- `results/precision_scaling.json`: posterior L1 error per card falls as
  $n^{-0.475}$ from 40 draws to 1280 **with no bias floor**. That is the pure
  Monte Carlo law — the sampler is unbiased and precision is nowhere near
  saturated.
- `results/ess_probe.json`: the exact DP is reached in only 9 decisions out of
  641, so almost every $P(\text{success})$ in the engine is still a sampled
  estimate rather than an exact one.

Neither says the *policy* can feel the next step. Only a duel does.

## Hypothesis

`fishbot4(opponent_gamma=0.35, n_draws=1440)` scores a positive set differential
against `fishbot4(opponent_gamma=0.35, n_draws=480)`.

The comparison is against 480, not against 160, because 480 is what ships. A
1440-vs-160 cell would win on the step already taken and answer nothing.

The ratio is the same 3× as the last rung, deliberately: if the response is
linear in $\log(\text{draws})$ the two steps are worth the same, and running the
identical ratio is what makes that comparison meaningful rather than rhetorical.

## Effect size assumed for sizing

**+0.15 sets per deal-pair**, a *minimum interesting effect* and not an estimate
— the same threshold the last rung used, chosen before the data on grounds
independent of it.

The price is higher this time and that is part of the threshold's meaning. From
`results/precision_cost.json` a decision costs 3.52 ms plus 5.84 µs per draw, so
480 draws is 6.3 ms and 1440 is 11.9 — **+5.6 ms, a 1.89× decision**, against
the 1.35× the last rung cost. An effect below what the already-shipped lookahead
delivers, for nearly twice the inference time, is not a thing this engine should
buy.

Explicitly **not** assumed: that this rung is worth what the last one was. The
last rung's +0.340 sizes nothing here.

## Design

- **6 blocks × 1000 pairs = 6000 duplicate deal-pairs**, fresh seeds throughout,
  disjoint from every seed already recorded.
- Per-pair standard deviation **3.799**, the *measured* mean of the six
  480-vs-160 blocks.

  `results/pair_sd_model.json` would predict 3.603 from the divergence share of
  0.862. The measurement is used in preference to the model, and the 5% gap is
  recorded here rather than discovered afterwards: the model exists to size runs
  that have no comparable cell, and this one has six.
- **MDE at 80% power is 0.137**, under the 0.15 threshold.
- Cost: at 1440 draws each pair is roughly twice a 480-draw pair, so this run is
  about as expensive as the last one again.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 6 blocks. Demonstrated if and only if the
95% interval excludes zero. `scripts4/precision_verdict.py` implements exactly
this analysis for the last rung and is reused for this one.

> **Corrected before any pair of this run was played.** That sentence originally
> read "is reused unchanged", and it could not have been: the script had the
> first rung's block labels hard-coded, so pointing it at this run was
> impossible without editing it. It is now parameterised over both rungs, with
> each rung's constants — its minimum interesting effect, its per-pair standard
> deviation, its pre-registered MDE — fixed in the code beside the document that
> fixed them. A commitment a document makes on behalf of code the code cannot
> keep is not a commitment, and the fix belongs here rather than in a footnote
> written after the run.

The per-pair standard deviation above was also re-checked after a correction to
how `pool_cells` recovers a standard error from a recorded interval (it used a
normal critical where the harness uses *t*). That moved the measured mean of the
six 480-vs-160 blocks by $-0.0004$ and left the MDE at $0.1374$ either way, so
**3.799 stands and this design is unchanged**.

**Homogeneity.** Cochran's $Q$ across the 6 blocks, diagnostic only.

**Reported alongside, not decisive.** The log-linearity contrast: this estimate
against the last rung's +0.340. Equal steps support a response linear in
$\log(\text{draws})$; a smaller one is diminishing returns. Descriptive only —
no decision hangs on it, and with two points on the curve it could not.

## Committed in advance

- No block excluded for its result; no block added to chase significance.
- The run proceeds whatever the interim state of any other experiment.
- A demonstrated effect does **not** automatically move `WEB_DRAWS` again. The
  decision to pay 1.89× per decision is separate from the decision about whether
  the effect is real, and will be made with the measured latency in hand — the
  same commitment the last rung made and kept.
