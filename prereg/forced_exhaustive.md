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
