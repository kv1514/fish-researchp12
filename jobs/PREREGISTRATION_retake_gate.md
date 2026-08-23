# Pre-registration: does withholding help once it only fires on a real duel?

Written **before any pair of this run has been played**, with the base rate and
the noise both measured first and recorded in `results/duel_depth_base_rate.json`
and `results/pair_sd_model.json`.

## The prior, stated up front because it is bad

Five screening cells have measured this family and all five failed:

| cell | pairs | effect vs champion |
|---|---|---|
| retake penalty w0.30 | 200 | −0.340 [−0.665, −0.015] |
| retake penalty w1.00 | 200 | −1.015 [−1.562, −0.468] |
| score-adaptive w_behind 0.50 | 200 | −0.185 |
| score-adaptive w_behind 1.00 | 200 | −0.890 |
| score-adaptive w_behind −0.50 | 200 | −0.075 |

Two lose decisively and the loss grows monotonically with the penalty. **This is
the sixth cell of a family with five failures**, and that has to be on the record
before the number exists, because a positive here read without it would look far
stronger than it is. If this run comes out positive it earns a replication, not
a paragraph.

## Why it is not simply a sixth guess

The measured penalty is **ungated**: it fires on the first retake as well as the
fiftieth. The argument in `fish4/adaptive.py` is not about the first. It is about
a repeated public exchange teaching the table that a half-suit is contested while
neither side nets a card across the cycle. The first retake is a certain ask that
keeps the turn and reveals nothing the table did not just watch — penalising it
pays the theory's cost without being in the situation the theory describes.

So the implementation did not match its own stated hypothesis, and every cell
above tested the implementation. `retake_min_depth` gates the penalty on
`duel_depth`, and this run tests the hypothesis.

## What was measured before sizing, rather than assumed

- Duels are not rare: `duel_depth ≥ 2` at **57%** of decision points.
- A retake is on the menu at **11.2%** of positions; **3.25%** are at depth 1,
  which are exactly the ones the gate spares.
- So the gate un-flags **29%** of the flagged positions. If the ungated penalty's
  −0.340 is proportional to what it flags, the most the gate can recover is
  **+0.098** — which is why a 200-pair screen was **not** run: it resolves
  ±0.192 at best and would have returned a null whatever the truth was.

## Effect size and sizing

The comparison is **gated penalty (w=0.30, `retake_min_depth=2`) vs the
champion**, so the hypothesis is "the theory-matching form does not lose", and
the interesting alternatives are −0.340 (the gate changes nothing), −0.242 (it
removes its share of the harm) and 0 or above (the depth-1 exemption was the
whole problem).

Per-pair sd is **not** taken as the A/A 3.796. `results/pair_sd_model.json`
measures, over 28 cells, that `sd ≈ 3.88 · √(share of pairs on which the arms
diverge)`, with the conditional part varying by only 5.9%. The ungated arms
diverged on 0.440 of pairs; the gate keeps 71% of the flagged positions, so the
estimate is 0.31 and **sd ≈ 2.16**.

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds throughout.
- **MDE at 80% power ≈ 0.135**, which separates −0.340 from 0 comfortably and
  separates −0.242 from 0 adequately.
- Sized on the A/A figure instead, the same power would have demanded about
  6200 pairs and this would not have been run.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 2 blocks; report the estimate and its 95%
interval.

**The contrast that matters.** This estimate against the ungated −0.340. The
gate is vindicated to the extent the difference is positive; it is refuted if
the two are indistinguishable, because then the depth-1 exemption changed
nothing that mattered.

**Homogeneity.** Cochran's *Q* across the 2 blocks, diagnostic only.

## Committed in advance

- No block excluded for its result; no block added to chase significance.
- A positive result does **not** change a default. It earns one replication at
  the same size on fresh seeds, and only a replication that agrees gets written
  up as an effect. Five prior failures in this family is exactly the prior under
  which a single positive is most likely to be noise.
- A negative or null result is reported as the sixth entry in the table above.
