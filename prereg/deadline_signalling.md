# Pre-registration: the signalling gate was set before the tempo price was measured

Written before any game of this program is played. Every input below is a
figure this project already holds; none is fitted here.

## The inconsistency this responds to

`fish4/agent4.py` gates the signalling protocol on

```python
cheap = p[order[0]] <= self.signal_max_p     # 0.15
```

and `signal_mode` defaults to `"off"`, so in the deployed configuration the
engine never signals at all. When it was measured it was measured at 0.15
(`jobs/j14_signalling.json` swept 0.15 and 0.35; `jobs/r5_signal_*.json`, the
only award-rule run, used the default).

§tempo of the paper then measured what a turn is actually worth, bucketed by
$p_\text{best}$ --- the success probability of the ask the seat would otherwise
have made:

| $p_\text{best}$ | pairs | price | se |
|---|---|---|---|
| $[0.00, 0.25)$ | 374 | $-0.043$ | 0.169 |
| $[0.25, 0.50)$ | 511 | $+0.004$ | 0.143 |
| $[0.50, 0.75)$ | 179 | $+0.508$ | 0.258 |
| $[0.75, 1.01)$ | 400 | $+0.415$ | 0.164 |

**A turn is free below $p_\text{best} = 0.50$ and costs about $+0.45$ above
it.** The gate is set at $0.15$ --- less than a third of the way to where the
measured price crosses zero. The two sections have never been connected. That
is the whole of this registration: not a new mechanism, a gate calibrated
against a number that did not exist when it was chosen.

## What is now known that was not known then

**What an avoided misdeclaration is worth.** $+1.7898$, 95\%
$[+1.5927, +1.9870]$ sets (`results/error_value.json`), measured rather than
assumed from the rulebook. So a signal pays whenever

    P(it places a split we would otherwise get wrong)  >  price of the turn / 1.79

and below $p_\text{best} = 0.50$ the numerator of that ratio is
indistinguishable from zero.

**That the lever is reachable.** Over 800 cross-engine games, of the 130
half-suits we declared wrongly, the median number of *our own* turns between
assembling the set and the deadline is $25.5$; only $16$ of $130$ had none
left (`results/acquisition_v07.json`).

**Why the channel closes.** `GameState.legal_asks` requires the asker to hold
a card of the half-suit. Once our team holds all six, no opponent can ask
there again, so nothing they do will place the split and a deliberately failed
ask of our own is the only remaining channel.

## What is NOT being registered

Not "signalling works". It has been measured twice and returned $+0.002$
$[-0.086, +0.090]$ in the void era and $+0.068$ $[-0.033, +0.169]$ under the
award rule, both at $\text{signal\_max\_p} = 0.15$. The second is positive and
does not clear zero. This registers the *gate*, at the threshold the tempo
measurement points to.

## Arms

- **A** = `V06_DEPLOYED`, signalling off. The shipped champion.
- **B** = A + `signal_mode="stuck"`. The previously measured setting, at the
  default $0.15$, included as a **replication** of `r5_signal`'s $+0.068$
  under a fresh seed block. If B does not reproduce, C means nothing.
- **C** = A + `signal_mode="stuck"`, `signal_max_p=0.50`. The measured
  free-turn threshold.

## Design

Duplicate-deal paired, both seat parities, fresh seed block, award rule pinned
in the runner, opponent `dylan_v07` through `BRIDGE_REV = 2`. 1,000 games per
arm, which `results/r5_signal_check.json`'s paired SD of $\approx 1.15$ puts
at about $\pm 0.071$.

## Primary outcome, fixed now

Paired difference of set margins against v0.7, C minus A.

## Secondary outcomes, fixed now

1. The declaration path ledger for every arm.
2. Wrong declarations per game, paired.
3. **The error-value decomposition** (`scripts4/error_value.py`): the value of
   an avoided error and the cost when none is avoided, fitted on this run's own
   journal. This project has twice reported "the ledger moved and the margin
   did not" without being able to say why; it can now, and a null here is
   required to be decomposed rather than merely filed.

## Ship bar

Point estimate $\geq +0.15$ with the interval clear of zero. The usual bar,
used here without amendment: unlike `prereg/forced_exhaustive.md` this is a
knob that trades a turn for information, so the bar that exists to stop
knobs-on-noise is the right instrument.

## Withdrawal conditions, fixed now

1. **B does not replicate** $+0.068$ within its interval: withdraw the whole
   run. The gate cannot be studied on a base that does not reproduce.
2. C's margin is negative beyond noise: withdraw, and report that turns are
   not free at $0.50$ in this population --- which would contradict §tempo and
   is the most interesting way this could fail.
3. The ledger moves and the margin does not, again: report it decomposed. The
   value and tempo terms are the deliverable in that case, not a third
   "real reduction that buys no sets".
4. Wrong declarations rise: withdraw. A signalling protocol that costs
   accuracy is not doing what the theory says.

## Expected outcome, written down in advance

C beats B --- more firings at a threshold where the turn is measurably free
should be better than fewer --- and neither clears $+0.15$. The honest
prediction is another decomposable null: perhaps $+0.05$ to $+0.10$, with the
ledger moving more than the margin and the error-value fit showing the tempo
term eating most of it. If C clears $+0.15$ I should check the seating and the
ledger before believing it, because that would be three times what the
previous measurement of the same mechanism returned.

---

# Outcome, recorded against the registration above

Run 2026-08-28, `scripts4/signal_gate_confirm.py 500 3`, 1,000 games per arm
on identical deals, both seat parities, `BRIDGE_REV = 2`, zero fallbacks, zero
unfinished. `results/signal_gate_confirm.json`,
`results/signal_gate_journal.jsonl`.

| arm | margin | vs A |
|---|---|---|
| A shipped, signalling off | +2.4760 | — |
| B `signal_max_p` 0.15 | +2.5940 | **+0.1180** [+0.0325, +0.2035] |
| C `signal_max_p` 0.50 | +2.5980 | **+0.1220** [+0.0291, +0.2149] |

## Withdrawal conditions, checked in order

1. **B replicates.** The registration required B to reproduce `r5_signal`'s
   $+0.068$ within its interval. $[+0.0325, +0.2035]$ contains $+0.068$. Not
   triggered.
2. **C is not negative.** Not triggered.
3. **The ledger moved and the margin did not.** Not the case here: the margin
   moved and its interval is clear of zero. The decomposition is reported
   below anyway, because secondary 3 asked for it unconditionally.
4. **Wrong declarations rose.** They fell: $0.170 \to 0.156$ (B) $\to 0.152$
   (C) per game. Not triggered.

The run is valid and reports a real positive effect.

## Verdict: it does not ship

The bar was *point estimate $\geq +0.15$ with the interval clear of zero*.
C is $+0.1220$. The interval is clear of zero; the point estimate is not at
the bar. **It does not ship**, and the bar is not amended after seeing the
number — that is the entire function of writing it down first. The effect is
real and it is smaller than the threshold this project uses to decide that a
knob is worth its complexity.

## What actually happened, which is not what the registration expected

The registration's argument was that the gate at $0.15$ was calibrated against
nothing, and that §tempo's measurement — a turn is free below
$p_\text{best} = 0.50$ — put the correct threshold more than three times
higher. The prediction was **C beats B**.

C did not beat B. It matched it, and the path ledger says why:

| arm | exact | voluntary | gate | forced | wrong/game |
|---|---|---|---|---|---|
| A | 792 | 3746 | 288 (26.7% wrong) | 178 (52.2% wrong) | 0.170 |
| B | 805 | 3714 | 75 (9.3%) | 323 (45.2%) | 0.156 |
| C | 796 | 3692 | 78 (10.3%) | 307 (46.3%) | 0.152 |

Signalling moves about 210 declarations out of the gate path and into the
forced path, and **B and C move almost exactly the same ones**: 75 against 78
gate declarations, a difference of three in a thousand games. Widening the
gate by a factor of $3.3$ changed the engine's behaviour on three
declarations.

So the gate was never the binding constraint, and the reason is visible once
stated: signalling engages when the seat is stuck, and a stuck seat is one
whose best ask is already bad. $p_\text{best} \leq 0.15$ is very nearly
*implied* by the situation the protocol fires in, so raising the ceiling to
$0.50$ admits almost nothing new. §tempo was right about the price of a turn
and wrong about which quantity was limiting the mechanism.

That retires the hypothesis rather than leaving it open, which is worth more
than the $+0.004$ it bought.

## Secondary 3: the error-value decomposition

`scripts4/error_value.py` on this run's own journal. For C:

| games | paired margin |
|---|---|
| avoided no error, $n=876$ | $+0.0502$ $[-0.0248, +0.1253]$ |
| avoided one, $n=66$ | $+1.6061$ $[+0.9819, +2.2302]$ |
| avoided two or more, $n=6$ | $+3.6667$ $[+0.9861, +6.3472]$ |
| **added** an error, $n=52$ | $-0.9615$ $[-1.6399, -0.2832]$ |

Two things follow, and one of them is new.

**The whole effect is avoided errors.** The 876 games where signalling avoided
nothing contribute $+0.044$ of the $+0.122$ with an interval containing zero;
the 72 games where it avoided one or more contribute $+0.128$. The mechanism
does exactly what the theory said it would, and it is small because it only
matters in 7% of games.

**Its ceiling is that it adds errors almost as often as it avoids them** — 52
games against 72. That is the number to attack if this mechanism is ever
revisited, not the gate.

A caveat on the regression, because the fitted intercept and the conditional
mean disagree and the conditional mean is the one to believe. The fit reports
a cost-when-nothing-avoided of $+0.0990$ $[+0.0117, +0.1863]$, excluding zero,
against the directly conditioned $+0.0502$ $[-0.0248, +0.1253]$, which
contains it. The line is misspecified: at $dw = -1$ it predicts
$0.099 - 1.278 = -1.179$ against an observed $-0.962$, so the added-error
games pull the intercept up. Avoiding an error is worth more than adding one
costs — $+1.61$ against $-0.96$ — which says the errors this protocol *adds*
are cheaper than the ones it avoids, and a straight line through both cannot
represent that. Reported here rather than quietly using the friendlier number.

**Sign check against the other runs.** The stuck-claim gate priced a deferral
at $-0.36$ to $-0.43$ sets. Here the equivalent quantity is positive. These
are not in conflict: that gate defers a declaration and waits, which spends
the deadline; this protocol spends one turn to place a split and keeps the
declaration. The two mechanisms pay for information in different currencies,
and only one of them is buying time.
