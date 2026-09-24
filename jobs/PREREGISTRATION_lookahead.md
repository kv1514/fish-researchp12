# Pre-registration: does the belief-space lookahead help?

Written and committed **before** the run starts. The point is that the analysis
cannot be chosen after seeing the numbers, because this configuration has already
produced two errors of exactly that shape:

1. A 200-pair screening cell resolved at $+0.570$ and failed to replicate.
2. The "decisive" 1400-pair run was sized against $+0.23$ — an estimate inflated
   by the very screening cell that had been excluded on principle — so it was
   under-powered for the true effect and came back inconclusive.

Both were the winner's curse, the second one committed inside the correction for
the first. This document exists so there is no third.

## Hypothesis

`fishbot4(opponent_gamma=0.35, w_lookahead=0.25, lookahead_depth=3,
lookahead_beam=4)` scores a positive set differential against the identical
policy with `w_lookahead=0`.

## Effect size assumed for sizing

**+0.153 sets per deal-pair.** This is the unbiased pooled estimate over the four
*unselected* cells (2400 pairs) already run. It is deliberately **not** the
$+0.226$ or $+0.23$ figures, which include the selected screening cell.

## Design

- **6 blocks × 1000 pairs = 6000 duplicate deal-pairs**, fresh seeds throughout.
- Per-pair standard deviation taken as **3.796**, the value measured over the
  4800 A/A pairs of the variance study, not the older 3.869.
- **MDE at n = 6000 is 0.137**, giving a genuine margin over the assumed 0.153.
  At the 5000 pairs originally proposed the MDE is 0.150 — essentially equal to
  the effect, i.e. exactly 80% power and a one-in-five chance of a third
  inconclusive run. The extra 1000 pairs cost about 17 minutes.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 6 new blocks (6000 pairs). Every block is
unselected, so no cell may be dropped for its result. The effect is
**demonstrated** if and only if this 95% interval excludes zero.

**Secondary, reported either way.** Pool of the 6 new blocks with the 4 existing
unselected cells: 8400 pairs, MDE 0.116. Reported for the estimate, not for the
verdict — the primary decides.

**Homogeneity check.** Cochran's $Q$ across the 6 new blocks. This is diagnostic
only. Given the A/A study measured $\tau = 0$ and coverage of 23/24, a
significant $Q$ here would be evidence of a genuinely deal-population-dependent
effect rather than a reason to switch to random-effects pooling.

## Committed in advance

- No cell will be excluded on the basis of its result.
- If the primary interval includes zero, the result is reported as **not
  demonstrated**, whatever the secondary says.
- No further run will be added to chase significance. If 6000 pairs does not
  settle it, the honest conclusion is that the effect is below what this project
  can resolve at a reasonable cost, and that is the finding.
