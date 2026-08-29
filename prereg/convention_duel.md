# Pre-registration: does the aimed convention win games?

**Registered 2026-08-29, before any duel involving the convention was run.**

## Why a duel is required and what it is being asked

Everything measured so far is about the **belief**. The posterior instrument
scores arms off-policy --- the decoder is off while the games are played, so
every arm sees the same positions --- and it says the aimed code book makes the
belief both better calibrated and better at naming the true holder.

That is not the same claim as "the engine plays better", and this project has
already measured one case where it was not: the at-ask-time depth covariate
improved the posterior and was worth nothing in play. Two things the belief
instrument structurally cannot see:

1. **The sender pays.** At gate 0.05 the encoder gives up a mean of **0.0090
   probability of success** on every ask it encodes, on 63% of our asks. That
   is a real cost in tempo and cards, and it is paid whether or not the message
   is ever used.
2. **Both sides change at once.** In a duel the encoder and decoder are both
   live, so the belief that picks the ask is itself being shifted by the
   convention. The instrument holds that fixed by construction.

## Gate

**This duel runs only if `prereg/convention_aimed.md` replicates on fresh
seeds under its own three conditions.** If the replication fails, there is
nothing here to duel and this document is void.

## Design

`scripts4/duel.py`, duplicate deals: every deal is played twice with the two
configurations swapped between seats, so the pair difference removes the deal.
The independent unit is the **pair**.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same, plus `convention_max_cost = 0.05`, `convention_aim = True`,
  `convention_beta = 0.8` --- the exploratory optimum, and only if the
  replication leaves it there.
* **n_pairs:** 3,000. At the historical pair-difference SD for this engine
  (~2.6 sets) that gives a 95% half-width near 0.093 sets, which resolves the
  +0.15 bar below with room to spare.
* Rules: `wrong_distribution_outcome="opponent"` throughout, as everywhere else.

## Outcome and ship bar, fixed in advance

**Primary:** mean paired difference in sets per game, Y minus X, with a 95%
interval.

**Ship bar: +0.15 sets/game**, the same bar the deadline-signalling channel was
held to and declined against (`prereg/deadline_signalling.md`, measured
+0.122 [+0.029, +0.215]). Using the same number is deliberate --- these are two
ways of spending the same resource, and the cheaper one does not get a cheaper
bar.

* **lower bound of the interval > 0 AND point estimate >= +0.15** --> ships,
  after the usual re-measurement of every affected figure.
* **lower bound > 0 but point estimate < +0.15** --> a real but sub-bar effect.
  Recorded, not shipped, exactly as the signalling channel was.
* **interval contains 0** --> the belief improvement does not carry into play.
  Recorded as such, and the convention stays at zero.
* **upper bound < 0** --> the convention costs more in probability than the
  message is worth. Recorded, and the direction closes.

**Secondary, reported and not gating:** allocation-error rate per game (the
error class this was built to attack, 0.1676/game at v1.0), ownership-error
rate, mean cards publicly located per game, and the sender's realised carry
rate and mean cost in the duel population.

## Withdrawal conditions

* If Y's realised carry rate in the duel differs from the 62.9% measured on the
  instrument by more than 10 points, the duel population is not the one the
  belief result was measured on and the comparison is reported as such.
* If either side raises `IllegalAction`, the run is void --- that is a bug, not
  a result, and this build has already produced one.
* If the pair-difference SD exceeds 4.0 sets, the run is underpowered for this
  bar and is extended rather than read.

## What a null would mean

That 1.72 bits an ask, correctly aimed and correctly decoded, improves the
belief measurably and does not survive the price of sending it. That would be
a clean and publishable negative: it would put the ceiling on pre-play
agreement in this game at the *cost of the channel* rather than at the receiver's
inference, and it would say the remaining slack is in the ask objective's
willingness to pay rather than in what an ask can be made to say.
