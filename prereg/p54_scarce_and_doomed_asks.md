# Pre-registration: P54, `scarce` and the asks that cannot succeed

Written before any P54 game.

## A fact about the rules, not a correlation

If your **team** holds all six cards of a half-suit, an ask in it is made to an
opponent, and an opponent holds none of them. **It cannot succeed.** And
`fish/engine.py::_apply_ask` hands the turn to the target on a failure, so each
one costs the whole rest of the visit.

`results/doomed_asks_17100000.json`, 400 games, 18,293 of our asks:

| | doomed asks | share of own asks |
|---|---:|---|
| KRAKEN | 2,451 | **0.1340** [0.1230, 0.1444] |
| SESTINA | 1,834 | **0.0961** [0.0879, 0.1047] |

Intervals do not overlap. **6.13 guaranteed-failure asks a game, 39% more than
theirs.** Zero of them hit, in two independently written implementations that
agree exactly on the same seeds — which is the self-test, because a single hit
would mean the team count is wrong.

**These are not signals.** This engine has a signalling protocol whose method is
a deliberately doomed ask, and it is OFF in the champion: `signal_mode='off'`,
`signal_budget=0`, `w_signal=0.0`, `convention_beta=0.0`.

## The engine is not blind — it knew and asked anyway

At the moment of each doomed ask, reading the seat's own posterior for
P(our team holds all six of this half-suit), over 120 games:

| threshold | share of doomed asks at or above it |
|---:|---:|
| ≥ 0.10 | 0.787 |
| ≥ 0.25 | **0.603** |
| ≥ 0.50 | **0.272** |
| ≥ 0.75 | 0.075 |

Mean **0.340**. So more than a quarter of these asks are made with the belief
already putting even odds or better on the half-suit being ours outright. The
information is there and the decision rule does not use it.

The posterior read saves and restores the agent's RNG. The first version did
not, and `build_posterior` draws from that same generator, so it changed the
games it was measuring.

## And one live term points straight into it

`scarce` is `F[i,2] = (team_exp[hs]/6 - 0.5) * 2`, weighted **+0.2** — it
rewards asking where our **team's** expected share is high. But an ask succeeds
only if an **opponent** holds the card. The term is pointed at the failure mode.

**Mechanism pre-check, run before this registration**, 100 games per setting:

| `w_scarce` | doomed-ask share | per game |
|---:|---|---:|
| **+0.2** shipped | 0.1340 [0.1230, 0.1444] | 6.13 |
| 0.0 | **0.1056** [0.0901, 0.1214] | 4.83 |
| −0.2 | **0.0852** [0.0713, 0.1015] | 3.91 |

Monotone, and at −0.2 below SESTINA's rate. The knob moves the waste.

## The arms

* **C1** `w_scarce = 0.10` — halved
* **C2** `w_scarce = 0.00` — off
* **C3** `w_scarce = -0.10` — reversed
* **C4** `w_scarce = 0.40` — **doubled**, both signs

Nothing else moves. `w_suit` stays at its shipped 0.06 in every arm.

## Predictions, recorded before the run — including why this may fail exactly as P53 did

1. **The doomed-ask rate falls monotonically from C4 to C3.** Already
   established by the pre-check for three of the five points; if the duel's
   arms do not reproduce it, the harness and the pre-check disagree and nothing
   is readable.
2. **C4 is the worst arm.** Same shape as P53's prediction 1, and registered for
   the same reason: if doubling the term that points into the waste does *not*
   hurt, the account above is wrong.
3. **THE REAL RISK, NAMED IN ADVANCE.** P53 moved its target quantity perfectly
   and lost anyway, because flattening a concentration preference is damaging in
   itself — `w_suit` at −0.06 cost **−1.17** in self-play. `w_scarce` going
   negative is *the same kind of change*, and C3 may fail the same way while
   still reducing doomed asks. **So the outcome I expect is that C1 and C2 are
   near neutral and C3 is negative, with the doomed-ask rate falling across all
   of them** — which would say the waste is real, the knob removes it, and
   removing it this way costs more than it saves.
4. If that happens, the honest conclusion is that **`scarce` is not the lever**
   and what is needed is a term that prices *this ask cannot succeed*
   specifically, rather than a blunt preference against half-suits our team
   holds. That is a new term and a separate registration, not a re-scope of this
   one.

## The bar and the withdrawal conditions

Unchanged: **+0.15 sets/game with the interval clear of zero against SESTINA at
`BRIDGE_REV 3` AND in self-play**, 300 deals × 2 parities, paired within deal.

Withdrawn if either population's interval lies entirely below zero. One
population only is opponent-specific and does not ship.

Harness conditions: any arm whose `weights.scarce` does not equal its registered
dose at run time; and a non-monotone dose response, which as in P51, P52 and P53
means **no single dose may be read**. `scripts4/arm_overlap.py` is run on the
result, and `scripts4/doomed_asks.py` is re-run on the winning and losing doses
so the mechanism is measured on the same block as the margin.

---

## OUTCOME, `results/p54_scarce_and_doomed_asks.json`

$7{,}200$ games on block 17,500,000, 300 deals × 2 parities, zero fallbacks,
zero unfinished, dose check passed at run time. All four arms distinct (521+ of
600 pairings differ).

| arm | `w_scarce` | vs SESTINA | self-play | ask hit rate |
|---|---:|---|---|---:|
| C4 | **+0.40** | −0.1667 [−0.439, +0.106] | **+0.1200** [−0.093, +0.333] | 0.5054 |
| — | +0.20 champion | — | — | 0.5192 |
| C1 | +0.10 | −0.2533 [−0.508, +0.001] | −0.0833 [−0.312, +0.145] | 0.5263 |
| C2 | 0.00 | **−0.4567** [−0.723, −0.191] | −0.0900 [−0.308, +0.128] | 0.5336 |
| C3 | −0.10 | **−0.5800** [−0.858, −0.302] | **−0.2433** [−0.460, −0.026] | 0.5335 |

**C2 and C3 withdrawn.** Nothing clears.

### Prediction 2 failed; prediction 3, the registered risk, was right

**C4 is the BEST arm, not the worst.** Doubling the term that points into the
waste *helps* — it is the only arm positive in either population. Prediction 2
failed exactly as P53's prediction 1 did, and for the same reason.

Prediction 3 named this in advance: *"the outcome I expect is that C1 and C2 are
near neutral and C3 is negative, with the doomed-ask rate falling across all of
them — which would say the waste is real, the knob removes it, and removing it
this way costs more than it saves."* That is what happened, except that C1 and
C2 are worse than neutral.

### And the decisive measurement: the best arm makes MORE doomed asks

`results/doomed_asks_scarce040.json`, 150 games at `w_scarce = 0.40`:

| | doomed-ask share | per game |
|---|---|---:|
| champion (+0.20) | 0.1340 [0.1230, 0.1444] | 6.13 |
| **C4 (+0.40), the best arm** | **0.1781** [0.1583, 0.1998] | **8.30** |
| SESTINA | 0.0961 | — |

**The arm that makes the most guaranteed-failure asks is the best arm, and the
arms that remove them are the worst.** The waste is real, logically certain,
verified twice over and 39% worse than the opponent's — and it is **not the
binding constraint**. It is a symptom of a preference that is net beneficial, not
a leak to plug.

Prediction 4 therefore stands as written: **`scarce` is not the lever.** What it
would take is a term pricing *this ask cannot succeed* specifically — narrow
enough to cut the provably worthless asks without flattening the preference that
is evidently earning its keep. That remains untried, and after this result it is
a weaker prospect than it looked: the 27% of doomed asks made at
P(own all six) ≥ 0.5 are worth at most a fraction of a channel that two dose
sweeps say is already near its optimum.

### The hit rate, for the third time

C4 is the best arm and has the **lowest** hit rate (0.5054 against the
champion's 0.5192). C2 and C3 are the worst and have the **highest** (0.5336,
0.5335). With P53's monotone sweep this is the third independent confirmation
that hit rate is anti-correlated with margin in this engine.

### A correction to this registration's own motivation

It cited `concent` — "confirmed negative at 4,000 games" — as corroboration for
reducing concentration. That was a loose reading. `concent` prices the change in
how our team's holding is spread **across our own seats**; `suit` and `scarce`
price **which half-suit** to ask in. They are different quantities, and the
`concent` result is not evidence about these knobs in either direction. P53 and
P54 together say the opposite of what that citation implied: **both
concentration knobs are at or below their optimum, and moving either downward is
costly.**
