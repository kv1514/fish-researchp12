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

---

# OUTCOME, recorded 2026-08-29: the duel found a defect, not a result

**The convention as registered LOSES, heavily, and the reason is a
mis-specified gate rather than the idea.** Recorded here in full because the
belief instrument had cleared it three times and would never have caught this.

## What the duel said

Duplicate deals, X = KRAKEN v1.0, Y = the licensed arm (gate 0.05, aimed,
`beta = 0.8`). Positive means **the champion is stronger**.

| n | diff |
|---|---|
| 40 pairs | +1.750 [+0.645, +2.855] |

An order of magnitude larger than anything the sender's measured cost --- 0.0090
probability per encoded ask --- could account for. So the ablation, same deals
and same agent seeds:

| arm | diff |
|---|---|
| **encoder only** --- speak, do not listen | **+1.467** [+0.818, +2.116] |
| **decoder only** --- listen, nothing sent | +0.033 [-0.646, +0.712] |

**All of the loss is speaking.** Listening at `beta = 0.8` with no message on
the wire is a clean null, which is the design intent of a soft weight vindicated:
a constraint can be fatally wrong, a likelihood can only be mildly wrong.

## The defect: the gate was priced in the wrong currency

`encode_cost` compared the drop in **probability of success** between the best
legal card and the agreed one, and `convention_max_cost = 0.05` read as "give up
at most five points of success probability".

But the agent does not rank asks by probability of success. `scores` carries
lookahead, tempo, concentration, and the information the ask leaks. Re-pricing
the gate in the objective's own units and measuring the gap the swap actually
costs, over 877 swaps in six games:

| | objective-score gap |
|---|---|
| median | **+0.3596** |
| p75 | +0.6865 |
| p90 | +1.2503 |
| max | +1.5000 |

The objective's own range here is about 1.5. **The old gate was routinely paying
a third of the objective for a message it believed cost 0.009.** That is the
-1.467 sets/game, and it is a specification error of exactly the kind this
project keeps finding: a number that looks bounded because it is bounded in some
quantity, just not the one that matters.

## What it costs the earlier results

Not the decoder. The belief measurements are paired within their own
transcripts, and the decode genuinely improves the posterior on those
positions; the aimed replication stands as a statement about **inference**.

What it costs is the **carry rate**, and with it the claim that the channel was
cheap. Re-priced, over 1,088 asks:

| | share of asks |
|---|---|
| objective already picks the agreed card | 19% |
| agreed card ties the chosen one | 5% |
| **free total** | **24%** |
| gap <= 0.05 objective units | 12% |
| gap <= 0.10 objective units | 18% |

against the **63-74%** the mis-priced gate reported. So the free channel is
about a third as wide as `results/convention_cost.json` implied, because that
analysis also measured cost in probability (0.131 for a random card) and
understates it the same way.

The 1.72 bits an ask is still a true fact about the rules. What is not true is
that most of it was free.

## Next, and re-registered rather than assumed

The gate now reads the same `scores` the pick was made from
(`fish4/agent4.py`). Re-running the same ablation at
`convention_max_cost = 1e-9` --- the **free-message gate**, swap only when the
agreed ask ties the chosen one, so the message costs literally nothing and no
calibration is needed --- and at 0.05 objective units, 200 pairs each.

**The bar is unchanged at +0.15 sets/game.** A re-priced gate does not get a
softer bar for having been wrong once.
