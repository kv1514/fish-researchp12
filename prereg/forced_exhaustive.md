# Pre-registration: the last declaration is searched with a heuristic it does not need

Written before the arm exists. The screening measurement is already run and is
stated here in full so it cannot be re-described afterwards.

## The defect, located exactly

`fish4/claim4.py::best_for_half_suit` finds the MAP split by shortlisting on
per-card marginals and scoring the shortlist against the joint posterior. Two
truncations:

```python
trimmed = [opts[:2] if len(opts) > 1 else opts for opts in per_card]
...
for _, cand_assign in cands[:max(1, self.cfg.exact_candidates)]:
```

The first keeps only the top **two** candidate holders per card, so with three
teammates the third is never considered for any card. The second scores only
the top **three** of the surviving $2^6 = 64$ combinations against the joint.

Both are reasonable speed heuristics in general play, where this runs at every
decision. Neither is needed at the moment that matters most.

## Why the last half-suit is different

`forced_claim` fires when no legal ask exists. Measured over 500 self-play
games: 188 of 192 forced claims fire with every opponent cardless, and **104 of
192 fire at one live half-suit** --- where the declaration ends the game. There
is no downstream position to trade against, so the objective is exactly
$\mathrm{EV} = 2p_{\text{exact}} - 1$, monotone in $p_\text{exact}$, and the
right move is simply the argmax. The whole team space there is at most
$3^6 = 729$ assignments and usually far fewer, because pinned cards are fixed.

## The screen, already run

`scripts4/forced_ceiling.py`, 500 self-play games, award rule, all six seats
ours. Every forced declaration at one live half-suit had its **full 729-way
argmax enumerated** alongside the split the engine actually named:

| | |
|---|---|
| forced declarations at one live half-suit | 104 |
| our pick was **not** the argmax | 38 (36.5%) |
| the argmax **was** the true split | 32 (30.8%) |
| we were right | 18 (**17.3%**) |

So a policy that took its own argmax would have been right **30.8%** of the
time against our **17.3%**. That is not a theoretical ceiling: 30.8% is the
measured accuracy of the argmax policy on those same 104 real positions.

Also recorded, and not the target of this registration: the sampled posterior
is miscalibrated at the deadline, overconfident in $[0.45, 0.60)$ (claims
0.528, observes 0.362) and underconfident above 0.60 (claims 0.700, observes
0.867). A separate problem, and this change does not address it.

## The arm

`ClaimConfig.forced_exhaustive: int = 0` --- the maximum number of live
half-suits at which the forced path enumerates the full team space instead of
the shortlist. At 0 the branch never runs and play is bit-identical.
`ClaimConfig.forced_exhaustive_cap: int = 1024` --- refuse to enumerate above
this many assignments, so the knob cannot become a timeout.

Arm A = `V06_DEPLOYED`. Arm B = A + `forced_exhaustive=1`.

## THE DECISION RULE IS NOT THIS PROJECT'S USUAL ONE, and here is why, in advance

The predicted margin effect is **+0.028 sets/game**: a 13.5-point accuracy gain
on 0.104 declarations per team per game at two sets of differential each.
Against a paired-difference SD near 1.15 that needs roughly 12,000 games to
resolve from zero. Every duel this project could afford would return a null,
and that null would read as "no effect" when the truth is "an effect two orders
of magnitude below what this instrument can see".

So the ship bar of $+0.15$ sets/game, which exists to stop knobs that trade one
thing for another from being adopted on noise, is **the wrong instrument here
and is deliberately not used.** This is not a preference: it is a search that
fails to optimise the objective its own docstring states, at a decision where
the game ends immediately and nothing is traded away. Stating that before the
run rather than after is the entire point of writing it down.

**Primary outcome, fixed now.** Forced-declaration accuracy at one live
half-suit, arm B against arm A on identical deals, fresh seeds, both parities.
Ships if accuracy rises with the interval clear of zero.

**Secondary outcome, fixed now.** The paired margin against v0.7 with its
interval, reported whatever it says, and **explicitly not a ship criterion**.
The expectation recorded in advance is that it is indistinguishable from zero.

**Guards, fixed now.**
1. Whole-game bit-identity at `forced_exhaustive=0`.
2. Accuracy must not fall in any other bucket. A search that finds a better
   split at live=1 and disturbs live=2 is not the change registered here.
3. The enumeration must agree with the incumbent wherever the incumbent's
   shortlist already contained the argmax --- i.e. the arm must be a strict
   improvement in search, not a different objective. Checked by asserting that
   arm B's chosen split never has *lower* `p_exact` than arm A's.

**Withdrawal conditions, fixed now.**
- Accuracy does not rise: withdraw, and report that the argmax gap measured in
  the screen does not survive being acted on --- which would mean the ranking
  is an artifact of scoring positions we did not have to choose in.
- Accuracy rises but the margin moves *negatively* beyond noise: withdraw. A
  correct declaration that costs sets means the objective at that node is not
  what the docstring says, and that is a bigger finding than this knob.
- Runtime at the forced node rises enough to matter for the web table: cap it
  harder rather than shipping a stall.

## Expected outcome, written down in advance

Accuracy at live=1 rises from about 17% to about 31%, because that is what the
screen already enumerated on real positions. The margin comes back
indistinguishable from zero with an interval comfortably containing +0.028. If
the margin comes back *large*, something is wrong with the seating and I should
go looking for it rather than celebrate.

---

## OUTCOME, part 1: the primary passes, and the secondary was not run

### The primary, which is the ship criterion

2,400 games, self-play, our seats' forced declarations at one live half-suit:

| arm | right | of | accuracy | 95% CI |
|---|---|---|---|---|
| A_shipped | $77$ | $258$ | $0.2984$ | $[0.2459, 0.3569]$ |
| B_full | $105$ | $258$ | $\mathbf{0.4070}$ | $[0.3488, 0.4679]$ |

Paired at the game level: $+0.0117$ more correct last declarations per game,
95\% $[+0.0067, +0.0167]$ --- clear of zero. Accuracy rises by $10.9$ points,
$28$ more correct declarations in $258$. The screen predicted $17.3\% \to
30.8\%$ on 104 positions; the confirm measures $29.8\% \to 40.7\%$ on 258. The
levels differ because the screen's block was a different seed set; the
**gain**, $13.5$ points against $10.9$, replicates.

**Guard 2 (accuracy must not fall in any other bucket): passed, and exactly.**
Every other live-count bucket is identical between arms --- $114/140$ at
live=2, $22/24$ at live=3, and so on down --- because `forced_exhaustive=1`
gates on at most one live half-suit and nothing else is reached.

**Guard 3 (never a lower-scoring split): passed**, enforced in
`_exhaustive_split` and checked in `tests4/test_forced_exhaustive.py` by
spying on every substitution rather than trusting the code.

### The secondary was not run, and the figure it produced is not a null

The pre-registration fixed the secondary as "the paired margin **against
v0.7**". It was run in self-play, and in that runner's first version *all six
seats* received the arm's parameters. Both teams therefore improved by the
same amount, and $(\text{ours} - \text{theirs})$ cannot move. It reported

\[ +0.0000, \quad 95\%\ [-0.0142, +0.0142] \]

which is not a null. It is an arithmetic identity wearing a confidence
interval, and its interval is tight precisely because there is nothing in it
to vary. Read as a null it would have been the most misleading number in this
study: it excludes the $+0.028$ the pre-registration predicted, so it would
have looked like a *refutation* of an effect it never measured.

The runner now gives the opponent the untreated baseline in self-play, and the
pre-registered v0.7 arm is queued. **Nothing ships until that is reported**,
even though the ship criterion is the primary and the primary passed: a
registration that names a secondary and then does not run it is not a
registration that was honoured.

---

## OUTCOME, part 2: the pre-registered secondary, and the ship decision

### The secondary, run as registered

1,000 games against dylan_v07 through `BRIDGE_REV = 2`, zero fallbacks, zero
unfinished.

| arm | right | of | accuracy | 95% CI |
|---|---|---|---|---|
| A_shipped | $28$ | $87$ | $0.3218$ | $[0.2330, 0.4257]$ |
| B_full | $37$ | $87$ | $\mathbf{0.4253}$ | $[0.3267, 0.5302]$ |

Paired: $+0.0090$ more correct last declarations per game,
$[+0.0031, +0.0149]$ --- clear of zero. **Guard 2 passes exactly**: every
other live-count bucket is identical between the arms ($54/74$, $10/18$,
$2/4$, $0/2$).

Margin: $+0.0180$ $[+0.0063, +0.0297]$, which contains the $+0.028$ predicted
in advance and excludes zero.

### It replicates three times over

| population | accuracy gain |
|---|---|
| screen, 104 positions | $17.3\% \to 30.8\%$ ($+13.5$) |
| confirm, self-play, 258 positions | $29.84\% \to 40.70\%$ ($+10.9$) |
| confirm, v0.7, 87 positions | $32.18\% \to 42.53\%$ ($+10.4$) |

Different seed blocks, different opponents, the same effect.

### Guard 3, runtime, and what the measurement does and does not support

Twelve games each way: $1.235$ s/game unarmed against $1.005$ s/game armed,
which is $-18.7\%$ and cannot be read as a speed-up. It was taken while three
workers were saturating the box, so it is contaminated by load and the sign is
not meaningful. What it does support is the only thing the guard asks: there
is no evidence of a slowdown. The structural argument is the stronger one --
the enumeration is capped at 1,024 assignments, fires only at one live
half-suit, and does so about $0.2$ times a game. A clean timing on an idle box
is worth taking before the next release note quotes a number.

### The decision

Every condition the pre-registration fixed in advance is met. The primary
rises with the interval clear of zero **in both populations**; guards 2 and 3
pass; no withdrawal condition triggers --- accuracy did not fail to rise,
the margin did not move negatively, and runtime shows no problem.

**This ships.** It is the first change of this session to clear its own bar.

**Sequenced, not immediate.** Two other pre-registered runs are in flight
against `V06_DEPLOYED` as their arm A. Changing the champion while they run
would leave their recorded baseline labelled as something the repository no
longer contains. The knob is flipped once the queue drains, and
`tests4/test_forced_exhaustive.py`'s bit-identity test has to be rewritten
when it is: after shipping, "the default reproduces the champion" is a
statement about the *new* champion, and the test that currently asserts the
knob is off would be asserting the opposite of the truth.
