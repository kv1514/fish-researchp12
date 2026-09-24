# Pre-registration: does trading hard inside a duel pay?

Written **before any pair of this run has been played**, with the reachable base
rate and the noise both measured first and recorded in
`results/retake_bonus_base_rate.json`.

## Why this is not a seventh guess

Six cells of the adaptive family have been measured and none has paid:

| cell | pairs | effect vs champion |
|---|---|---|
| retake penalty w0.30 | 200 | −0.340 [−0.665, −0.015] |
| retake penalty w1.00 | 200 | −1.015 [−1.562, −0.468] |
| score-adaptive w_behind 0.50 | 200 | −0.185 |
| score-adaptive w_behind 1.00 | 200 | −0.890 |
| score-adaptive w_behind −0.50 | 200 | −0.075 |
| **retake penalty w0.30, gated on a real duel** | **2000** | **−0.004 [−0.067, +0.059]** |

Every one of them **withholds**. The opposite policy — take the card straight
back, trade hard inside the duel — has never been measured here, and it is what
strong players more often describe doing. `w_retake` is subtracted from the ask
scores, so a negative weight is exactly that bonus and the engine needs no
change: `retake_min_depth=0` reproduces every measurement already taken.

This is a different hypothesis, not the same one with the sign flipped by
accident. The withholding argument was about a repeated public exchange
teaching the table that a half-suit is contested. The trading argument is that
a certain card in hand now beats an uncertain one later, and that resolving a
contested half-suit early is worth more than the information it gives away.

## What was measured before sizing, rather than assumed

A re-take is a **certain** ask, so the objective already scores it with
P(success) = 1 — the term the whole paper says dominates. A bonus can therefore
only change a decision where the re-take is on the menu **and something else
currently outranks it**. Over 489 positions with a legal ask:

- a re-take is on the menu at **11.2%** of positions;
- at **69%** of those it is *already the chosen ask*, where a bonus is inert;
- so a bonus can act at **3.5%** of all positions, and a penalty at the
  disjoint **7.8%**. The family's other base-rate script counts their union,
  which is neither quantity.

And the reachable positions are near-ties: the score gap to the leader has
**median 0.000** and mean 0.155. At the median reachable position the bonus is
breaking an exact tie between two asks the objective values equally.

**That is the honest statement of the hypothesis, and it is weaker than the one
the folk advice makes.** Breaking a tie has expected value zero unless the
objective is systematically wrong in a way correlated with re-taking. This run
tests that, not "trade hard in a duel" as usually meant.

## Effect size and sizing

Per-pair sd is **not** the A/A 3.796. Scaling the ungated penalty's measured
divergence share of 0.440 by the ratio of reachable positions gives
`s ≈ 0.162` at w = −0.30, hence **sd ≈ 1.57**.

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds throughout
  (base seeds 26 000 000 and 26 200 000, checked against every recorded and
  queued cell by `scripts4/check_seeds.py`).
- **MDE at 80% power ≈ 0.098.**
- **No alternative is stated, because nothing measures one.** This direction has
  never been run, so there is no prior effect to size against and none is
  invented here. The design is sized to resolve an effect of the same order as
  the ones this study calls real elsewhere (the lookahead's +0.104, precision's
  +0.340), and that is the whole claim about its power.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 2 blocks; the estimate and its 95%
interval. Demonstrated if and only if the interval excludes zero.

**Homogeneity.** Cochran's *Q* across the 2 blocks, diagnostic only.

**The contrast worth reporting.** This estimate against the gated *penalty*'s
−0.004. Both act on disjoint slices of the same situation in opposite
directions, so a positive here beside a null there would say the asymmetry is
real; two nulls would say the re-take decision does not repay any policy at all.

## Committed in advance

- No block excluded for its result; no block added to chase significance.
- A positive result does **not** change a default. Six prior nulls in this
  family is exactly the prior under which a single positive is most likely to
  be noise, so a positive earns one replication at the same size on fresh seeds
  and nothing else.
- A null is reported as the seventh entry in the table above, and specifically
  as a null about **tie-breaking**, since that is what the base rate says the
  weight can reach.
