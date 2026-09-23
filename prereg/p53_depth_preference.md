# Pre-registration: P53, the depth preference — we over-concentrate at the bottom

Written before any P53 game. The mechanism pre-check below was run *before* this
registration and is reported here rather than after the duel, because P52's
lesson was that an arm can lose without ever having moved the quantity it was
aimed at.

## The chain, end to end, every link measured

**1. The deficit is entirely in reaching six, not converting six.**
`results/assembly_ledger_16100000.json`, 400 games:

| | ours | theirs |
|---|---:|---:|
| half-suits won a game | 4.145 | 4.855 |
| reached **peak 6** a game | **4.098** | **4.860** |
| converted a peak 6 into a win | 0.9732 | 0.9748 |

The conversion gap is **−0.0016**. The peak-6 gap is **−0.762**. Everything is
assembly. The excess shows up as half-suits stalled at 3, 4 and 5 — +0.690 a
game, which almost exactly accounts for the shortfall.

**2. And the stall is at the BOTTOM of the ladder, which is not where this
project has been looking.** Climb rate = upward transitions per ply spent at
that holding:

| holding | ours | theirs | gap |
|---:|---:|---:|---:|
| 1 | 0.02930 | 0.04493 | **−0.01563** |
| 2 | 0.04084 | 0.05568 | **−0.01484** |
| 3 | 0.04577 | 0.05075 | −0.00498 |
| 4 | 0.05775 | 0.04747 | **+0.01028** |
| 5 | 0.06763 | 0.05581 | **+0.01182** |

**We are faster at finishing and slower at starting**, and we spend **38% more
plies** holding only one or two of a half-suit. They make 9.5% more upward
transitions overall.

**3. Because our ask allocation is far steeper in own-depth than theirs.**
`results/ask_allocation_16300000.json`, 400 games, 18,498 of our asks against
19,119 of theirs, classified by the asker's own pre-ask count — the same
objective rule for both engines, no posterior and no model of anyone:

| held | P(chosen \| k) ours | theirs | ratio | share of our asks | share of theirs |
|---:|---:|---:|---:|---:|---:|
| 1 | **0.11258** | **0.19717** | **0.57** | 0.2432 | **0.3467** |
| 2 | 0.28986 | 0.23826 | 1.22 | 0.3238 | 0.2986 |
| 3 | 0.63851 | 0.40890 | **1.56** | 0.2341 | 0.1830 |
| 4 | 0.75711 | 0.71711 | 1.06 | 0.1296 | 0.1083 |
| 5 | 0.72841 | 0.85836 | 0.85 | 0.0693 | 0.0634 |

Their curve is nearly flat from 1 to 2 (0.197 → 0.238). Ours more than doubles
(0.113 → 0.290). **At a half-suit we hold one of, they ask 75% more readily than
we do.**

`P(chosen | k = 0)` is exactly zero for both engines over the whole run, which is
the self-test: the rules forbid it, so a single counter-example would mean the
harness is misreading the hand.

**4. And a prior measurement points the same way.** The `concent` term, which
rewards increasing team concentration, was *confirmed negative at 4,000 games*,
and the paper's own summary is that "trading hit rate for concentration is a
measured disaster." Less concentration being better is the same direction this
registration takes; it is corroboration, not proof, because that arm moved a
different quantity.

## The mechanism pre-check, run before this registration

`w_suit` weights `ctx.my_depth[hs]` — the asker's own count — and is the depth
preference itself. 40 games per setting:

| `w_suit` | our P(chosen \| held 1) | ratio to theirs |
|---:|---:|---:|
| **+0.06** (shipped) | 0.113 | 0.57 |
| 0.00 | 0.132 | 0.62 |
| −0.06 | 0.259 | 1.39 |

The knob spans the target: SESTINA sits at 0.197 and linear interpolation puts
the match near **−0.03**. `w_scarce` also flattens, but its bite is at holdings 3
and 4 rather than 1, so it is not the lever for this gap and is not swept here.

**So the arm is known to move the measured quantity before it is played.** That
is what P52 lacked: `w_claim` lost *and* never moved $D_{\text{us}}$, and those
two facts had to be separated afterwards.

## The arms

One flag, four doses, both signs.

* **B1** `w_suit = 0.00` — the preference off
* **B2** `w_suit = -0.03` — interpolated to match their holding-1 rate
* **B3** `w_suit = -0.06` — deliberate overshoot, to find the turn
* **B4** `w_suit = +0.12` — **double it**, the direction the chain says is wrong

Nothing else moves. `w_scarce` stays at 0.2 in every arm.

## Predictions, recorded before the run

1. **B4 is the worst arm in both populations.** If doubling the preference does
   *not* hurt, the chain above is wrong about the sign and everything built on it
   needs re-reading. This is the prediction I would most regret getting wrong.
2. **The dose response is monotone across B4, champion, B1, B2** and turns
   somewhere at or before B3. A response that is not monotone means the term is
   interacting rather than adding, and — as in P51 and P52 — **no single dose may
   then be read**.
3. **$D_{\text{us}}$ rises in B1 and B2**, measurably, by the mechanism check
   above. `scripts4/claim_term_mechanism.py`'s harness is re-used to measure it,
   because P52 showed a duel cannot see this.
4. **Most likely outcome is a gain below the bar.** Fifty-two registrations have
   produced one shipped change. What is different here is that the causal chain
   is measured end to end rather than argued, and the knob is verified to move
   the first link. That raises the prior; it does not clear the bar.

## The bar and the withdrawal conditions

Unchanged: **+0.15 sets/game with the interval clear of zero against SESTINA at
`BRIDGE_REV 3` AND in self-play**, paired within deal, 300 deals × 2 parities,
cluster bootstrap over deals.

Withdrawn if either population's interval lies entirely below zero. Clearing one
population only is **opponent-specific and does not ship** — and that risk is
real here in a way it was not for the belief arms, because this arm was designed
from a measured comparison *against SESTINA specifically*. A gain that appears
only against them is the expected failure mode and will be reported as such.

Harness conditions: any arm whose `weights.suit` does not equal its registered
dose at run time, and non-monotonicity per prediction 2.
`scripts4/arm_overlap.py` is run on the result, because an arm that changes
almost nothing and an arm that changes nothing are different claims.
