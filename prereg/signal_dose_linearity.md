# Is the log-odds shift linear in the dose?

Registered 2026-09-04, **before the 15,700,000 bank is played**. The arm, the
dose, the prediction, the sample size, the verdicts and the withdrawal
conditions are fixed here and are not adjustable afterwards.

## What is already established, and what it leaves open

`prereg/signal_dose_law.md` settled the shape of the transfer ACROSS
OPPONENTS: the protocol shifts the log-odds that an opponent misdeclares by a
constant, and the multiplicative reading is refuted. That was measured with
the dose held fixed by construction, so it says nothing about what happens
when the dose changes -- and the dose is the one lever this project can
actually turn.

Converting every scored arm into the log-odds shift that would produce its
measured effect (`scripts4/dose_linearity.py points`, descriptive) gives:

    point                dose  baseline     shift   shift per signal [95%]
    dylan_v07 @ 0.69    0.686    21.08%  +0.01236   +0.01801 [-0.00951, +0.04525]
    dylan_v07 @ 1.48    1.477    21.08%  +0.01086   +0.00736 [-0.00644, +0.02099]
    ev_claim  @ 2.17    2.171     7.96%  -0.03246   -0.01495 [-0.05242, +0.02010]
    dylan_v07 @ 2.77    2.766    21.08%  +0.06695   +0.02420 [+0.01747, +0.03087]
    ev_claim  @ 2.87    2.872     7.96%  +0.06135   +0.02136 [+0.00607, +0.03611]
    heuristic @ 3.09    3.093    62.01%  +0.06533   +0.02112 [+0.00566, +0.03679]
    dylan_v07 @ 8.94    8.940    21.08%  +0.19396   +0.02170 [+0.01823, +0.02511]

Four of the seven clear zero, and all four give a shift per signal between
+0.0211 and +0.0242 -- across a 3.2-fold dose range, a 7.8-fold baseline
range and three different engines. Three of those four share one designed
dose, so their agreement about DOSE is the matched-dose design and not
evidence; the comparison that is not circular is 8.94 against ~2.9, two
banks and two registrations apart, and it holds.

If that is real, one number describes the whole surface -- a log-odds shift
per signal, independent of opponent and of volume -- and the transfer law is
its fixed-dose special case.

**The paper currently says the opposite about volume.** It reads the same
dose-response as convex with a turn-on near three signals a game, on the
ground that every arm consistent with zero sits below three. Under the linear
reading those arms are consistent with zero because they are underpowered,
not because the mechanism is off. This registration exists to decide which.

## The arm

The **exact configuration that produced the 1.477 point**: `signal_mode`
"stuck", `signal_max_p` 0.50, `signal_budget` 6, against `dylan_v07`, paired
against the shipped control on identical deals. No calibration stage and no
sweep: this is a direct replication at power of an arm that already ran, at a
fresh seed base, and choosing the configuration after seeing a dose is what
this design is avoiding.

Dose 1.477 is chosen because it sits inside the dead zone the threshold
reading claims (below three signals a game) and because the existing estimate
there, +0.00725 [-0.00631, +0.02081], lies BETWEEN the two predictions and
excludes neither. That is the definition of the point worth re-running.

## The prediction, computed before the run and not adjustable after

The linear law is fitted to **one** point: `dylan_v07` at dose 8.940
(`results/signal_budget_11700000.json`, arm `B_uncapped`). It is the only
well-measured point that is neither at the test dose nor part of the
matched-dose design, and it is six times the test dose away, so this is an
extrapolation and not an interpolation.

    k = +0.02170 log-odds per signal a game

Applied to `dylan_v07`'s baseline of 21.08% over 3.998 declarations a game:

| law | predicted extra wrong declarations a game at dose 1.477 |
|---|---|
| **linear in dose** (shift = k x dose) | **+0.0215** |
| **threshold** (no effect below ~3 a game) | **0** |

The prediction is a FORMULA, not a number: it is evaluated at the dose the
run actually realises, `predict(0.2108, 3.998, k * dose)` in the sense of
`scripts4/dose_law_table.py`. The +0.0215 above is that formula at 1.477 and
is recorded for concreteness. Over the dose tolerance below the prediction
moves between +0.0183 and +0.0248, and no part of that range reaches zero.

## Sample size and power

**5,000 paired deals**, 10,000 games per arm, 20,000 games total. The 1.477
arm ran at 2,000 deals with a half-width of 0.01356, so 5,000 gives about
0.0086 on the same instrument. That separates +0.0215 from 0 by about 2.5
half-widths in each direction.

**Power limit: the realised half-width must be at most 0.0095.** Above that
the run is UNDERPOWERED regardless of where the point estimate lands, and
this is fixed here so that a wide interval cannot be read as a null.

## Verdicts, all four named in advance

- **LINEAR** -- the interval covers the linear prediction and excludes zero.
- **THRESHOLD** -- the interval covers zero and excludes the linear
  prediction. The paper's current reading survives and the surface is not one
  parameter.
- **NEITHER** -- the interval excludes both. The shift is dose-dependent in
  some way neither reading captures, which is the outcome that would hurt
  most and is named here so it cannot be discovered later.
- **UNDERPOWERED** -- the interval covers both, or the half-width exceeds
  0.0095.

## Withdrawal conditions

1. **The margin identity closes** on both arms, checked from the recorded
   ledger, residual zero on every game.
2. **The control arm is the shipped configuration**, `signal_mode` off.
3. **The realised dose is within 15% of 1.477**, the same tolerance the
   matched-dose and dose-law studies used. Outside it the arm did not
   reproduce the operating point it is replicating.
4. **No unfinished games and no bridge fallbacks.**

## What this cannot do

It puts one well-powered point at low dose against one at high dose. Two
doses is a line through two points, and a line through two points is not a
demonstration that the surface is a line -- a smooth saturating curve through
both would be indistinguishable here and is not tested. What it CAN do is
kill the threshold reading, or kill the linear one, and those are the two
readings this project has actually written down.

It also says nothing about why a log-odds shift should be proportional to the
number of signals. That would be a mechanism, and this is still a
description.

Nothing enters `V06_DEPLOYED` on any outcome.
