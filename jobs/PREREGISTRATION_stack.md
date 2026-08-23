# Pre-registration: do the two demonstrated gains add?

Written **before any pair of the run has been played**, and before either of the
two features has ever been played alongside the other.

## What is already known

Two configurations beat `V04_CHAMPION` by a pre-registered margin:

| configuration | effect vs champion | 95% CI | pairs |
|---|---|---|---|
| champion + lookahead (d3, w0.25) | +0.104 | [+0.020, +0.189] | 6000 |
| champion + `n_draws=480` | +0.340 | [+0.243, +0.436] | 6000 |

Both intervals exclude zero. Neither run contained the other feature. So the
project has two demonstrated improvements and **zero** evidence about the thing
it would actually ship, which is both of them at once.

## Why this is not a formality

The temptation is to assume +0.104 and +0.340 add to +0.444 and move on. There
is a specific mechanism here that says they might not. The lookahead searches a
belief; the sampler is what produces that belief. More draws make the searched
belief sharper, and a sharper belief is exactly what the lookahead was buying by
searching in the first place. If the lookahead's gain comes from correcting
sampling error in the one-ply score, then paying for precision directly removes
the error the lookahead was compensating for, and the two overlap rather than
add. The opposite is equally arguable — a sharper belief makes each searched
node more trustworthy, so the search compounds — which is the point: it is
arguable either way, so it has to be measured.

This is the same failure the project has already paid for four times in another
costume. Reasoning about a quantity is not measuring it.

## Hypothesis

`fishbot4(opponent_gamma=0.35, n_draws=480, w_lookahead=0.25, lookahead_depth=3,
lookahead_beam=4)` scores a positive set differential against
`fishbot4(opponent_gamma=0.35, n_draws=480)` — that is, **the lookahead still
pays once precision has been bought.**

The comparison is deliberately against the *precise* configuration, not against
the champion. Against the champion the stack would win on the sampler alone and
the number would say nothing about the question.

## Effect size assumed for sizing

**+0.104 sets per deal-pair**, the lookahead's own measured effect against the
champion. This is the hypothesis "the two add" stated as a number, and the run
is sized to detect it. It is not a minimum interesting effect: any positive
increment is interesting here, because the alternative on the table is dropping
a feature that costs 6.7 ms per decision.

Using a previously measured effect for sizing is legitimate **only** because
that effect was itself measured on an unselected pre-registered run, and it is
not being re-estimated by this one. No cell of this run contributes to it.

## Design

- **6 blocks × 1000 pairs = 6000 duplicate deal-pairs**, fresh seeds throughout,
  disjoint from every seed used by the lookahead and precision runs.
- Per-pair standard deviation **3.796**, from the 4800 A/A pairs.
- **MDE at 80% power is 0.137.** That is above the +0.104 being sized against,
  and this is stated here rather than discovered later: at 6000 pairs the run
  has roughly 65% power against its own hypothesis. Six more blocks would reach
  80%, and the reason for not running them is cost, not evidence.
- Because the run is underpowered against its stated alternative, **an interval
  including zero will not be reported as "the lookahead does not pay on top of
  precision."** It will be reported as what it is: an interval, with its width,
  that fails to resolve an effect of the size assumed.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 6 blocks. Demonstrated if and only if the
95% interval excludes zero.

**Homogeneity.** Cochran's $Q$ across the 6 blocks, diagnostic only.

**Reported alongside, not decisive.** The additivity contrast: the pooled
estimate here against the lookahead's +0.104 measured against the champion. If
the two intervals overlap, the features add as far as this study can tell; if
this one sits below, they overlap in effect and the stack is worth less than the
sum. This comparison is descriptive and no decision hangs on it.

## Committed in advance

- No block will be excluded on the basis of its result.
- No further block will be added to chase significance.
- The run proceeds whatever the interim state of any other experiment.
- `V04_STRONGEST` and `WEB_DRAWS` are **not** changed by this result in either
  direction without a separate decision recorded with the cost in hand. Both
  features are already independently demonstrated; this run is about what to
  claim, not about what to ship.
