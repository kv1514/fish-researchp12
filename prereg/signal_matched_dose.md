# Does the signalling effect generalise, compared at equal dose?

Registered 2026-09-01, **before the calibration bank at 13,900,000 is played**
and before any arm of the scored bank at 14,300,000 exists. The grid, the
levers, the calibration rule, the feasibility gate, the sample size, the
primary and the verdicts are fixed here and chosen nowhere else.

## Why the previous attempt could not work

`prereg/signal_generality.md` compared opponents at whatever dose each one
happened to produce, and `results/signal_dose_arms.json` shows why that is not
a comparison. The dose factors into three opponent-dependent terms:

    fires/game = opportunity (s_A) x amplification (s_B/s_A) x gate (f/s_B)

    opponent      s_A   s_B/s_A   f/s_B   fires/game
    dylan_v07   4.150      3.02   0.896       11.248
    ev_claim    3.005      1.65   0.462        2.283
    search      3.112      1.64   0.390        1.992
    memory      2.770      1.95   0.421        2.277
    self        1.030      1.44   0.423        0.627

The middle term is the protocol's own doing: a signal is a doomed ask, it
throws away the turn, and it hands back the same stuck state. So dose is not
an opponent property that can be measured in advance and matched by choosing
opponents. That earlier registration assumed it was, and its independent
variable was therefore not independent.

**A cap cannot fix it.** `signal_budget` only lowers a dose. Matching downward
puts every opponent at or below 2.283 fires a game, and
`results/signal_budget_11700000.json` measures dylan_v07's own opponent channel
at that dose as +0.0073 [-0.0063, +0.0208] -- covering zero. Matching down
compares two nulls and answers nothing.

## The lever that raises a dose

`signal_max_p` is the cheapness gate: the protocol fires only where our best
ordinary ask has probability at most this of landing. It ships at $0.50$ and
passes $89.6\%$ of stuck turns against dylan_v07 against $39$ to $46\%$
elsewhere. Raising it toward $1.0$ lets the protocol fire on stuck turns where
we still had a decent ask, which **raises** the dose.

What it does not change is the signal itself. `perpetual.signalling_ask` picks
a card in a half-suit our own team provably holds, so it is doomed by
construction whatever the gate says, and it proves exactly the same fact to the
same partners. Only the opportunity cost of spending the turn changes.

**This makes the arms different policies, and that is the price.** At matched
dose we are comparing "the protocol tuned to fire N times a game" across
opponents, not "the shipped protocol" across opponents. The shipped comparison
is the one that cannot be made; this document does not pretend otherwise.

## Grid

Two opponents. `dylan_v07`, the reference. `ev_claim`, the only other honest
policy in the registry with declaration-error volume for the mechanism to move
(7.96% against dylan_v07's 21.08%; every other engine sits at 3-7%, which
`results/opponent_error_screen.json` established is the floor).

`search`, `memory` and `self` are excluded here and the reason is stated rather
than left to inference: they have less gate headroom than `ev_claim` and lower
baseline error, so they are strictly harder cases of the same test, and a null
against them would not discriminate.

## Calibration, on its own bank, scored for nothing

Seed base **13,900,000**, 200 deals x 2 parities. Its only outputs are a
parameter per opponent and a feasibility verdict. **No effect from this bank is
reported as evidence for or against anything.**

1. For each opponent, sweep `signal_max_p` over $(0.50, 0.70, 0.85, 1.00)$ and
   measure fires a game.
2. **The common dose** $D$ is the largest dose the WEAKER opponent reaches at
   `signal_max_p = 1.00`, rounded down to one decimal. The stronger opponent is
   brought down to $D$ with `signal_budget`, which is what a cap is for.
3. Each opponent's `signal_max_p` is then the smallest swept value whose dose
   is at least $D$.

## The feasibility gate, which can end this study

The dose-response against dylan_v07 is measured at three points and only three:
absent at $0.686$ (+0.0083), absent at $1.477$ (+0.0073), present at $8.940$
(+0.1363 [+0.1135, +0.1590]). Everything between is unmeasured.

So the calibration bank must also measure **dylan_v07's own opponent channel at
the common dose $D$**. If it does not clear zero there, the scored run is
**ABANDONED and not run**, and this is not a failure to work around by
searching for a $D$ where it does clear: re-picking $D$ after seeing that
result is choosing the dose after the data, which is the defect this whole
document exists to avoid.

**Abandonment is itself an answer, and it is registered as one.** It would mean
the mechanism needs a game state that no opponent except dylan_v07 can be made
to produce, at any setting of the gate. That is a statement about the
conditions the convention requires, and it would be reported as the outcome
rather than as a null result.

## Scored run

Seed base **14,300,000**, barred from 2,400,000, 3,600,000, 9,300,000,
9,700,000, 9,900,000, 10,100,000, 10,500,000, 10,900,000, 11,300,000,
11,700,000, 12,100,000, 12,500,000, 13,100,000 and the 13,900,000 calibration
bank. Agent seed base 143,000. 800 deals x 2 parities = 1,600 games an arm,
clustered on the deal, t at k-1 df, k = 800.

Two arms per opponent, on the identical deal.

| arm | parameters |
|---|---|
| `A_shipped` | `{}` -- the champion, signalling off |
| `B_matched` | `signal_mode="stuck"`, `signal_max_p` and `signal_budget` from calibration |

## Primary, and the two hypotheses it separates

The primary is **the opponent's extra wrong declarations a game**, `B_matched`
minus `A_shipped`, paired on the deal, per opponent. Not the margin: the margin
at a raised gate is expected to be WORSE, because signalling where we had a
good ask costs more in the race channel, and that cost is not what this
registration is about.

Against dylan_v07 the mechanism raises the opponent's declaration error rate
from $21.08\%$ to $24.02\%$. Two readings of that generalise differently, and
both are stated before the run:

- **H_proportional** -- the same rate FACTOR, x1.139. On `ev_claim`'s 7.96%
  baseline over 3.728 declarations a game that predicts **+0.0414** a game.
- **H_absolute** -- the same rate RISE, +2.94 points. That predicts **+0.1096**.

The measured half-width on this quantity at 800 deals is $0.0209$
(`results/signal_generality_ev_claim_12100000.json`), so z is 3.9 against
H_proportional and 10.3 against H_absolute, and the two predictions differ by
+0.0682, more than three half-widths apart. **800 deals separates each from
zero and from the other.** This is the first registration in this line that is
comfortably powered for its primary rather than marginally so.

## Verdicts, fixed now

- **GENERAL** -- `ev_claim`'s opponent channel clears zero at matched dose.
  Report which of H_proportional and H_absolute the interval is consistent
  with; if it covers both, say so rather than picking.
- **DYLAN-SPECIFIC** -- dylan_v07's channel clears zero at dose $D$ and
  `ev_claim`'s covers zero with a half-width at or below $0.0209$. The
  mechanism needs this opponent, not merely this dose.
- **INFEASIBLE** -- the calibration gate fails: no common dose exists at which
  the reference opponent shows the effect. Reported as the conditions being
  unreachable, per above.
- **UNDERPOWERED** -- the realised half-width exceeds $0.0414$, so
  H_proportional would not have cleared zero. Reported as a failure of this
  design, not as a null.

## Withdrawal conditions

1. **The identity closes** on the counted ledger for every arm and opponent,
   under `wrong_distribution_outcome="opponent"`.
2. **`A_shipped` is bit-identical to the champion** in both opponents' runs.
3. **The calibrated dose actually matched.** Fires a game must land within
   $\pm 15\%$ of $D$ for both opponents in the SCORED run. Calibration is on a
   different bank, so a parameter that hit $D$ there can miss here, and a
   comparison at unequal dose is the thing this design exists to prevent. If
   it misses, the run is withdrawn and reported as a calibration failure.

Any of the three failing withdraws the run; the file is kept under a
`_withdrawn_` name rather than deleted.

## What this still cannot do

It compares two engines, one of them ours. It cannot speak to human declarers,
and it cannot separate "the convention confuses readers of the public record"
from "it confuses this family of readers", because both engines here descend
from code in this repository or were written against the same rules. It also
matches the MEAN dose and not its distribution: dylan_v07's stuck turns carry a
half-width of 1.238 against ev_claim's 0.4515 on equal samples, so the tails
differ even where the means agree, and a mechanism sensitive to long episodes
rather than to total volume would not be controlled by this design.

Nothing here enters `V06_DEPLOYED` on any outcome. `signal_max_p` above 0.50 is
a measurement instrument, not a proposed configuration, and the margin it
produces is expected to be worse than the champion's.
