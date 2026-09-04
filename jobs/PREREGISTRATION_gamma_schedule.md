# Pre-registration: settle the dilution correction (`gamma_schedule = 1.0`)

Written **before any pair of this run has been played**.

## Why this cell and not the biggest number on the board

The v0.5 mandate says to let measurement pick the direction, and two
measurements pick this one.

**The information calibration.** `results/inference_curve.json` puts the
exchange rate at about **0.45 sets per card** of certainty, roughly flat from 5%
to 100% of the hidden cards, and `results/posterior_card_equivalents.json` puts
the champion at **18.05 card-equivalents of uncertainty**. Against that, the
whole demonstrated history of this engine — +0.340 for tripling the sampler — is
**0.76 cards**. Move-selection is spent; the posterior is where the sets are.

**The model is measurably misspecified, in a specific way.**
`scripts4/choice_curve.py` fits the depth exponent from 17,005 self-play
decisions with a genuine choice, block-bootstrapped over games:

| half-suits resolved | 0 | 1 | 2 | 3 | 4 | 5 | 6-8 |
|---|---|---|---|---|---|---|---|
| alpha | 2.00 | 1.28 | 1.20 | 0.68 | 0.30 | 0.41 | −0.02 |
| clustered SE | 0.08 | 0.08 | 0.12 | 0.12 | 0.13 | 0.18 | 0.16 |

The engine uses one constant. Against the covariate it actually conditions on,
that constant is wrong at both ends and in opposite directions.

**And the mechanism has already survived a prediction test.** `fish4/oppmodel.py`
argues the decay is mostly *covariate drift*, not behaviour: initial-deal depth
describes the asker's current hand less well as the game runs on (mean absolute
disagreement rises 0.16 → 0.66 cards), and noise in a covariate attenuates its
coefficient. It then predicted that if this reading is right, the schedule
should become **unnecessary** under `depth_mode="at_ask"`, where the covariate
does not drift. That was run: **+0.005, 95% CI [−0.333, +0.343]**. The
prediction held.

So this is not the largest screen number being chased. It is the one cell whose
mechanism was measured first, predicted second, and confirmed third.

## What is being tested

    challenger  fishbot4 {opponent_gamma: 0.35, gamma_schedule: 1.0}
    reference   fishbot4 {opponent_gamma: 0.35}          (V04_CHAMPION)

`gamma_schedule` is a claim about **shape, not strength**:

    gamma_eff(ask) = gamma * [ (1 - s) + s * alpha(frac) / ALPHA_MEAN ]

`ALPHA_MEAN` is the profile averaged over the observed distribution of asks, so
`s = 1` redistributes the model's belief across the game without changing how
much of it there is in total. `s = 0` is the incumbent exactly. That separation
matters: gamma itself sits on a broad duel-tuned plateau, and confounding shape
with strength would leave a positive result unattributable.

## Sizing, and why it is bigger than the screen implies

Screened once at 400 pairs: **+0.263, 95% CI [−0.087, +0.612]**, unresolved.

Sizing for +0.263 would need about 1,640 pairs. This run uses **6 blocks ×
1000 = 6000 pairs**, seeds **34 000 000** stepping 200 000, sized instead for an
MDE of about **0.137** at 80% power with the A/A per-pair sd of 3.796.

The reason is a lesson this session paid for. The `value_keep` screen's selected
cell decayed **0.320** from screen to settle, against a winner's-curse
correction of 0.153 that I had computed and believed — the realised decay was
about twice the max-of-three model. Sizing this run for the screen's own number
would repeat that mistake at a larger scale.

Selection here is milder than that case — the cell came from a batch of four,
not from 103 — so the correction is smaller, but the direction is the same and
the run is sized so that a halved effect still resolves.

## Outcomes, fixed in advance

- **Interval entirely above +0.05** — the dilution correction pays. It becomes
  part of v0.5, and the next question is whether it stacks with 480 draws,
  which is a separate pre-registered run and will not be inferred by chaining.
- **Interval containing zero, point estimate positive** — not resolved. Reported
  as a failure to resolve, not as a null, and the pairs it would take to settle
  are stated rather than the result being quietly kept.
- **Interval containing zero, point estimate near zero** — the screen's +0.263
  was selection, and the dilution correction does not pay in play even though
  the misspecification it corrects is real. That would be the most interesting
  outcome: a component measurably wrong in the model whose correction is worth
  nothing on the board, which is evidence about how much the posterior's shape
  matters at all.
- **Interval entirely below zero** — correcting a measured misspecification
  makes play worse. That would mean the model's errors are partly compensating
  and would call the whole opponent-model line into question rather than this
  cell.

## The prediction

**+0.13**, and I expect the interval to contain zero at its lower end.

Reasoning: take the screen's +0.263, apply a decay of roughly the size this
session measured rather than the size the max-of-three model predicts, and
about half survives. That is 0.29 cards on the information scale — small, but
against a champion whose entire improvement history is 0.76 cards it would be a
real contribution.

## What this does not decide

Nothing about `depth_mode="at_ask"`, which is demonstrated at +0.102 and
deliberately unshipped because its own pre-registration fixed 0.15 as the bar.
Nothing about whether the two stack — the at-ask prediction test says they
should not, and that is a separate claim. And nothing about the public table.
