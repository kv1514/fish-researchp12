# Pre-registration: the ask objective's tempo term ignores the price of a turn

Written before the knob exists. Every input is a figure this project already
holds.

## The inconsistency

`fish4/askfeat.py` gives every candidate ask a tempo feature

```python
F[i, 1] = fail * ctx.turn_risk[t]        # (1 - p) * how dangerous the target is
```

weighted by `w_turn = 0.6`. The penalty is linear in the ask's chance of
failing and carries a constant coefficient: the objective charges the same
rate for risking the turn no matter what the turn is worth.

§tempo of the paper measured what a turn is worth, and it is not a constant.
Bucketed by $p_\text{best}$, the success probability of the ask the seat would
otherwise have made:

| $p_\text{best}$ | pairs | price | se |
|---|---|---|---|
| $[0.00, 0.25)$ | 374 | $-0.043$ | 0.169 |
| $[0.25, 0.50)$ | 511 | $+0.004$ | 0.143 |
| $[0.50, 0.75)$ | 179 | $+0.508$ | 0.258 |
| $[0.75, 1.01)$ | 400 | $+0.415$ | 0.164 |

The paper's own summary: "Below $p_\text{best} = 0.5$ a turn is worth nothing;
above it, about $+0.45$." That section says in its opening that none of the
objective's tempo weights "was ever fitted against a measured scale, because
none existed. This section supplies one." It supplied one and nothing went
back to use it.

## How often this bites

Measured, 1,115 ask decisions over 12 self-play games at `V06_DEPLOYED`:

| $p_\text{best}$ band | decisions | share |
|---|---|---|
| $[0.00, 0.25)$ | 259 | $0.232$ |
| $[0.25, 0.50)$ | 331 | $0.297$ |
| $[0.50, 0.75)$ | 168 | $0.151$ |
| $[0.75, 1.01)$ | 357 | $0.320$ |

**$52.9\%$ of ask decisions are in the regime where the turn at stake is
measurably free**, and the objective charges the full
$0.6 \times (1-p) \times \texttt{turn\_risk}$ at every one of them. This is
not a rare gate: it is the code path the engine takes on most of its moves.

## The strategic claim, stated plainly so it can be wrong

When you have no good ask, take the long shot: the turn you are risking is
worth nothing, so the only thing that should decide is what the ask might win.
The engine currently behaves as though the turn were always worth the same,
and is therefore too cautious in exactly the positions where caution is free.

## The knob

`FishBot4(turn_free_below=0.0)`, a probability. When the top-scoring ask's
$p$ falls below it, the tempo column is re-weighted by `turn_free_scale`
(default $0.0$) and the asks re-ranked. At `turn_free_below=0.0` the test can
never pass and the champion is bit-identical.

Two passes, deliberately. $p_\text{best}$ is defined as the success
probability of the ask the incumbent objective would have chosen, which is
exactly what §tempo bucketed by --- so the first pass scores with the
incumbent weights to find it, and only then is the tempo column scaled. Using
$\max_i p_i$ instead would be cheaper and would not be the same quantity; the
extra pass is one matrix-vector product per decision.

## Arms

- **A** = `V06_DEPLOYED`.
- **B** = A + `turn_free_below=0.50`, `turn_free_scale=0.0`. The threshold the
  measurement points at, with the term switched off below it.
- **C** = A + `turn_free_below=0.50`, `turn_free_scale=0.5`. Half weight, as a
  dose rung: if B helps and C helps half as much, that is a dose-response; if
  C helps more than B, the right threshold is not the one the tempo table
  suggests and the story is wrong.

## Design

Duplicate-deal paired, both parities, fresh seed block, award rule pinned,
opponent `dylan_v07` at `BRIDGE_REV = 2`. 1,000 games per arm.

## Primary outcome, fixed now

Paired difference of set margins against v0.7, B minus A.

## Secondary outcomes, fixed now

1. Ask hit rate and asks per game, per arm --- the term's direct target.
2. Turns per game, per arm. `scripts4/acquisition.py` measured that half our
   acquisition edge is volume, so an intervention on the tempo term should be
   read against volume and not only against the margin.
3. The declaration path ledger, because everything else this session moved the
   ledger without moving the margin and the comparison is worth having.
4. The error-value decomposition on this run's journal.

## Ship bar

Point estimate $\geq +0.15$ with the interval clear of zero. The usual bar:
this is a knob that trades caution for upside, which is exactly what the bar
exists to police.

## Withdrawal conditions, fixed now

1. B is negative beyond noise: withdraw, and report that the tempo term is
   doing work the tempo measurement does not explain --- `turn_risk` is a
   function of the target's hand size, which correlates with how much
   information a failed ask reveals, so the term may be paying for something
   other than tempo. That would be the most interesting failure.
2. C beats B: the threshold is wrong and the argument from §tempo does not
   survive; report and withdraw rather than tune $0.50$ into whatever wins.
3. Hit rate falls without the margin rising: the engine is taking worse asks
   and being paid in something the ledger is not showing. Withdraw.

## Expected outcome, written down in advance

I do not know the sign, and saying so now is the point. The measurement
identifies a term that is charging for something the same paper says is free
in half of all decisions, which is a real mis-specification. But a
mis-specified term is not necessarily a harmful one: `turn_risk` is
$-(\text{target's hand size} - \text{mean})$, so the penalty also happens to
push asks toward players holding fewer cards, and that may be worth something
for reasons that have nothing to do with tempo. A plausible outcome is that
removing it costs sets, which would be a more useful result than confirming
the arithmetic.

---

# Outcome, recorded against the registration above

Run 2026-08-28, `scripts4/tempo_confirm.py 500 3`, 1,000 games per arm on
identical deals, both parities, `BRIDGE_REV = 2`, zero fallbacks, zero
unfinished. `results/tempo_confirm.json`, `results/tempo_journal.jsonl`.

| arm | margin | vs A |
|---|---|---|
| A shipped, one tempo rate | +2.1220 | — |
| B `turn_free_below` 0.50, scale 0.0 | +2.3500 | **+0.2280** [+0.0076, +0.4484] |
| C same threshold, scale 0.5 | +2.2060 | +0.0840 [−0.1216, +0.2896] |

## The mechanism check passes, and that is the strongest thing here

The registration predicted a specific causal chain and did not know its sign.
The chain appeared:

| arm | turns | asks | landed | hit rate |
|---|---|---|---|---|
| A | 56.522 | 51.235 | 26.775 | 0.5226 |
| B | 58.565 | 53.201 | 27.364 | 0.5144 |
| C | 57.016 | 51.678 | 26.926 | 0.5210 |

More turns, more asks, a *lower* hit rate, and more cards landed. That is
exactly "when the turn is free, take the long shot": worse asks by success
probability, more of them, more cards. And the dose rung is monotone in dose —
full charge $+0.0000$, half charge $+0.0840$, no charge $+0.2280$ — which is
the internal consistency that makes an effect believable past its interval.

## Withdrawal conditions, checked in order

1. **B negative beyond noise.** No.
2. **C beats B.** No: $+0.0840$ against $+0.2280$. The threshold from §tempo
   survives its own dose test.
3. **Hit rate falls without the margin rising.** The hit rate fell
   ($0.5226 \to 0.5144$) and the margin rose. Not triggered — and the fall is
   the predicted direction, not a warning sign.

Nothing fired. The run is valid.

## A note on arm A's absolute margin, because it looks wrong

A came in at $+2.1220$ against a $10{,}000$-game headline of $+2.3466$, which
is $2.4$ standard errors low. Across the five runs that carry an untreated A
the $z$ scores against the headline are $-2.43$, $+1.42$, $+1.21$, $-0.49$,
$+0.20$: $\chi^2 = 9.7$ on 5 degrees of freedom, $p \approx 0.09$. A is fine;
this block drew low. It does not touch the estimate, because B is paired to A
on every deal and a shared low draw cancels in the difference. It is recorded
because an unexplained $2.4\sigma$ in a headline figure is exactly the kind of
thing that should not be noticed for the first time by a reader.

## The bar does not have one reading, and that is a defect in the record

`prereg/tempo_regime.md` says, in full: **"Point estimate $\geq +0.15$ with the
interval clear of zero."** B is $+0.2280$ with a lower bound of $+0.0076$. By
the document, **B ships**.

`scripts4/tempo_confirm.py` implemented something else. It shipped only when
the whole interval sat above $0.15$, and it carried a `CONDITIONAL = 0.05`
band whose comment cited "the pre-registration" — which contains no such band.
By the code, **B does not ship**.

Both artifacts predate the run. Neither can be dismissed as post-hoc, and I am
not going to pick the one that gives the answer I would prefer. Picking either
here is bar-shopping, and the fact that the two readings would resolve
identically on every previous run in this project — including the signalling
gate this morning — is why the disagreement went unnoticed until a result
landed between them.

The runner now computes and prints **both** readings on every run, and the
invented conditional band is gone.

## Verdict: unresolved, and resolved by a bigger run rather than by a choice

**B does not ship today.** The interval is wide for a reason this project
measured this morning: `scripts4/pairing_value.py` shows that pairing's value
is governed by how often a knob changes a decision, and this knob fires on
$53\%$ of ask decisions, so the arms diverge immediately and pairing removes
almost nothing. The width is a sample-size problem with a known cure, not an
ambiguity to be argued away.

### Addendum, fixed before any game of it is played

- **Design.** Identical to the above in every respect except size and base.
- **Size.** $8{,}000$ games per arm — $4{,}000$ deals $\times$ 2 parities —
  fixed now, analysed **once**, at the end. No interim looks, no stopping
  early. At the observed paired sd this puts the standard error near $0.040$,
  which is the point at which the two readings of the bar coincide for an
  effect of the size measured.
- **Base.** The current champion, which as of today carries
  `claim_forced_exhaustive=1` (`prereg/forced_exhaustive.md`). This makes the
  new run a **replication against a different base**, not an extension: the
  $1{,}000$ games above are the evidence that motivated it and are **not
  pooled** with it.
- **Bar, disambiguated in advance.** Ship **only if both readings agree** —
  point estimate $\geq +0.15$ *and* interval lower bound $> +0.15$. If they
  disagree again, the result is reported as unresolved and nothing ships. This
  is the stricter of the two, chosen because the cost of being wrong in that
  direction is a delayed ship and the cost of being wrong in the other is a
  false positive in the champion and in the paper.
- **Withdrawal conditions.** Unchanged, plus: if C beats B at this size, the
  threshold argument from §tempo is withdrawn regardless of B's own number.
