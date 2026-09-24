# Pre-registration: is the claim threshold worth lowering after all?

Written **before any pair of this run has been played**.

## Why this cell and not another

`results/v04_duels.jsonl` contains 103 duel cells. Forty-five have a 95%
interval excluding zero, and almost all of those are supposed to — the champion
beating a random agent, a heuristic, v0.3. **One** is a small, cheap, unexplained
positive sitting inside a table the paper describes as "mostly nulls":

    claim threshold 0.90 vs the default 0.97    n = 400    +0.035  [+0.007, +0.063]

It is being singled out because it contradicts a documented conclusion. The
header of `fish4/claim4.py` argues that waiting to claim is close to free — an
opponent cannot take a set by claiming it, since a claim by a team that does not
hold all six *gives* the set away — and reports that "anything from 0.85 to
near-certainty plays identically: over 150 duplicate deals, thresholds 0.97 and
0.999 never once diverged." A measured, interval-excluding-zero benefit from
lowering the threshold is not what that argument predicts.

**This cell was selected for being significant, and that is the entire reason a
confirmatory run is required rather than a footnote.** Among 103 cells, roughly
five would exclude zero under a complete null. The screen's estimate is therefore
inadmissible as evidence and, per `jobs/SCREENING_DISCIPLINE.md`, may not size
this run either.

## Hypothesis

`fishbot4(opponent_gamma=0.35, claim_threshold=0.90)` scores a positive set
differential against `fishbot4(opponent_gamma=0.35)`, whose threshold is 0.97.

## Effect size assumed for sizing

**+0.02 sets per deal-pair**, a minimum interesting effect fixed in advance and
deliberately an order of magnitude below the +0.15 used for the belief-space
search and the sampling budget.

The threshold for "interesting" is lower here because the price is zero. This is
one constant. It adds no inference, no latency, no state and no code path — the
`3.57 ms + 6.34 µs per draw` of `results/precision_cost.json` is unchanged to the
last digit. Where a feature costing 1.35× a decision has to clear what the
already-shipped search delivers, a feature costing nothing only has to be real.

## Design

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds throughout.
- Per-pair standard deviation **0.286**, and this number is the interesting part
  of the design. It is not the 3.796 of the A/A pairs, nor the
  `3.88 · √(divergence share)` of `results/pair_sd_model.json`. It is derived
  from the screening cell's own recorded interval, which reproduces a cell's
  measured standard deviation to within 1% on every cell where both are
  available.

  The model is not used because this run is outside where the model was
  measured. Its 28 cells all diverge on 44–88% of pairs; a threshold that binds
  rarely diverges on a few percent, and the model's constant conditional term
  has never been checked in that regime. Using it here would be extrapolation
  presented as measurement — the exact error this project has spent five
  corrections on.
- **MDE at 80% power is 0.018**, just under the 0.02 threshold.
- The run is cheap: two blocks against arms that agree on most deals.

## A second thing this run measures, at no extra cost

Because v0.4 stores per-pair differentials, this run reports its own divergence
share and conditional standard deviation. That is a direct test of
`results/pair_sd_model.json` at a divergence far below anything it was fitted on,
and it is recorded here in advance as a prediction:

> if the model held at this end, a per-pair sd of 0.286 would imply a divergence
> share of `(0.286 / 3.88)² = 0.5%` — about 11 divergent pairs in 2000. We expect
> it to be **substantially higher than that**, because a threshold change alters
> one decision rather than the whole line of play, so its conditional
> differences should be much smaller than 3.88 and its divergence share
> correspondingly larger.

The prediction is stated so that it can be wrong. Nothing in the primary
analysis depends on it.

## How small the behavioural change is, measured before the run

`results/claim_criterion.json`, over 10 games and 998 decisions carrying a claim
candidate: raising the bar from 0.97 to 0.90 admits **one extra claim in 998**.
That is the whole behavioural difference between the two arms.

It follows that the screen's $+0.035$ rests on very few informative pairs, which
is an argument for this run rather than against it — a 400-pair cell in which
almost every pair is identical can produce a small significant number from a
handful of deals, and 2000 pairs is the cheapest way to find out whether it
survives.

The same measurement clears a confound this run could otherwise have had.
`voluntary_claim` gates on `p_exact`, while the payoff is
$\mathrm{EV} = p_{\text{exact}} + q - 1$ with $q$ the probability our team holds
all six; the two coincide only at $q = 1$, and $q$ is below $0.99$ at 88% of
these decisions. So "lower the threshold" and "gate the wrong quantity" could
have been entangled. They are not: across thresholds from 0.999 down to 0.85 the
two criteria select **identical** claim sets, and they first diverge at 0.80.
Wherever a claim is close to worth making, our team already certainly holds the
cards and only the split is in doubt — exactly the case where the two agree.
This run therefore tests the threshold alone.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 2 blocks. Demonstrated if and only if the
95% interval excludes zero.

**Homogeneity.** Cochran's *Q* across the 2 blocks, diagnostic only.

**Reported alongside, not decisive.** The screening cell's +0.035, labelled as
the selected screen it is; and the measured divergence share against the
prediction above.

## Committed in advance

- No block excluded for its result; no block added to chase significance.
- The screen's +0.035 sizes nothing and decides nothing.
- A demonstrated effect **does** move the default, and the reason it may is
  stated here rather than decided afterwards: unlike every other shipped change
  in this study, this one has no cost to weigh against it. If it is real it is
  free, and the separate cost decision the other pre-registrations reserve is
  vacuous.
- A null is reported as the second entry for this cell, alongside the screen.
