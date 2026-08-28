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
