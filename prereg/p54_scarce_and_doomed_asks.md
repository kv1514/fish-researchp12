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
