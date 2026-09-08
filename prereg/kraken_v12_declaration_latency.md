# P44 — KRAKEN v1.2, second attempt: the declaration latency

**Written before any arm was played. Seeds, arms, bars and the expected
outcome are fixed here and are not amended afterwards.**

## Why there is a second attempt

P43 put three registered candidates at the 1.95-point ask deficit and moved
none of them. The post-P43 analysis (§"Where the ask deficit lives" in the
paper; `results/ask_deadness_signal.json`, `results/completion_latency.json`)
then located the deficit somewhere else:

* Under the no-bluff rule a half-suit admits no landable ask **exactly when our
  own team already holds all six of it**. A dead ask is an ask into a half-suit
  we have won and not declared.
* We make **13.79%** of our asks there against SESTINA's 9.81%, and we sit on a
  completed half-suit for **16.80 plies** against their **7.84**.
* Priced at this project's measured value of a donated turn, the excess is
  **+0.458 [+0.157, +0.793]** sets a game against a deficit of −0.5250.

That analysis is exploratory and licenses nothing by itself. This document is
what it licenses: a registration.

## The specific defect this attacks

`fish4/claim4.py`'s module docstring justifies the 0.97 threshold with an
argument that is *nearly* right and has one hole:

> *"An opponent cannot take the set from us by claiming it... So the only cost
> of waiting is running out of opportunity... Waiting is close to free."*

Waiting is not free. Its price is every ask the owning team spends into that
half-suit while it waits, each of which surrenders the turn for certain. That
cost was never in the model, and it is now measured at 1.520 asks per
completion.

The engine does have machinery for this — the stuck claim gate, the
signalling ask, `avoid_doomed_asks` — and **every piece of it is conditioned on
`p[order[0]] <= 0.0`**, the agent being *certain* the best ask cannot land.
That is 1.5% of decisions (`results/doomed_ask_diag.json`). On the asks that
actually are dead the belief's own estimate averages **0.3377**, so none of it
fires. The apparatus is aimed at the right idea through a gate that almost
never opens.

Both arms below replace a certainty test with a graded one. Neither is a new
idea; each is an existing idea at a threshold that can be reached.

## The arms

Fixed here. Nothing is added to this list without a new registration.

| arm | one change from `V06_DEPLOYED` |
|---|---|
| **D1** `dead_ask_threshold = 0.5` | when the top-scoring ask's half-suit is more likely than not entirely ours, restrict the choice to asks whose half-suit is not, and re-rank by the same objective |
| **D2** `claim_owned_threshold = 0.77` | declare a half-suit we are essentially certain we own (`p_team >= 0.99`) at exactness `0.77` rather than `0.97` |
| **D3** both | licensed **only if both D1 and D2 clear the screen independently** |

At their defaults (`dead_ask_threshold = 1.01`, `claim_owned_threshold = 1.01`)
neither test can pass and the champion is bit-identical, which `tests4/`
asserts rather than assumes — the same discipline as `endgame_m = 0`.

### Why 0.77 rather than a sweep

It is a break-even, not a tuned value. Declaring now is worth `2p − 1`.
Waiting is worth at most `2 × 0.9759 − 1` (our measured declaration accuracy)
minus the dead asks spent meanwhile, `1.520 × 0.2713 = 0.412` sets at the
measured turn price. Equating:

    2(0.9759 − p) = 0.412   ->   p = 0.770

The approximation is stated rather than hidden: both inputs are averages over
all completions, not conditional on standing at a decision where `p_exact` is
already below `0.97`, and the bias direction is not known. **This is one point,
chosen in advance, not the best of a sweep.** If it fails, that is a result
about this break-even and not about the whole threshold family.

### Why 0.5 rather than a sweep

"More likely than not that we already own it" is the only threshold in `[0, 1]`
that can be named without reference to an outcome. `p_team_all` is the
independence approximation already computed for every half-suit
(`fish4/askfeat.py`), so the arm costs no new sampling.

## The futility screen, and its threshold

Fixed before the run, in this project's usual form: **an arm that changes fewer
than 2% of ask decisions (D1) or fewer than 0.25 declarations per game (D2)
does not reach a duel.** `avoid_doomed_asks` fires on 1.5% of decisions and is
a measured null at that rate, so an arm firing at the same rate is not worth
6,000 pairs to re-establish. Screen: 200 deals × 2 parities at seed base
**9,500,000**, instrumented only, no duel.

## Design

* Duel screen: 300 deals × 2 parities, seed base **9,600,000**.
* Confirm: 600 × 2 at **9,700,000**. Screen and confirm are **never pooled**.
* Both populations, every arm: **against SESTINA v1.0 through `BRIDGE_REV 3`**
  and **against the v1.1 champion in self-play**, paired within deal, the
  champion replaying every deal on this block rather than differenced against
  `results/mega_match.json`.

## The bar

**Ships only on +0.15 sets/game with the 95% interval clear of zero in BOTH
populations.** A candidate clearing against SESTINA and failing self-play is
reported as opponent-specific and is not shipped — the shape this project has
already withdrawn a feature for.

Three arms are tested. Multiplicity is named here rather than in a discussion
section: at the 0.15 bar with intervals clear of zero in two populations, the
per-arm false-positive rate is not the family rate, and a single arm clearing
by a hair in both populations is weaker evidence than this document's bar
makes it look.

## The predicted outcome

Recorded before the runs so the result can be a result rather than a relief.

**D1 clears the futility screen and fails the duel.** The kill-check already
showed our ask objective steers away from dead half-suits *better* than
SESTINA's does (−0.0101 against +0.0198 relative to a random draw from the same
menu), so the ask side is the channel where we are already ahead, and pushing
it harder is not obviously where half a set is hiding. I expect a small
negative from the information a dead ask carries: under the no-bluff rule a
failed ask publicly proves the asker holds another card of that half-suit,
which is exactly the fact a partner needs to place a split — so D1 removes
the engine's own mechanism for resolving the allocation it is stuck on.

**D2 is the one with a case.** It attacks the latency directly rather than its
symptom, and its threshold comes from a break-even rather than a sweep. I still
do not predict it clears: v0.3 swept this threshold and found 0.70 costs 0.45
sets against 0.97, with everything from 0.85 up playing identically. D2 differs
from that sweep in being *conditional* — it lowers the bar only where
`p_team >= 0.99`, which is the case the sweep did not separate — but the prior
is against it.

**Most likely outcome: nothing ships and there is no v1.2.** That is the
outcome P43 recorded in advance and got. Writing it down again is the only
thing that makes a clear result believable if one arrives.

## Withdrawal conditions

An arm is void, not reported, if: the knob's default is not bit-identical to
the champion; the arm's firing rate is zero (the parameter did not reach the
code path); or any interval comes back zero-width, which is the signature of an
experiment that did not run. All three have happened in this project.

## OUTCOME

**Nothing ships. There is no v1.2, and the champion is unchanged.**

### The futility screen stopped D2

400 games at seed base 9,500,000 (`results/p44_futility.json`):

| arm | fired | bar | |
|---|---|---|---|
| D1 `dead_ask_threshold = 0.5` | 916/18,515 asks = **4.95%** | 2.00% | pass |
| D2 `claim_owned_threshold = 0.77` | 94 in 400 games = **0.235/game** | 0.250/game | **stop** |

D2 misses by 6% of its bar. The bar was fixed in advance for exactly this case,
so D2 did not reach a duel and D3 — licensed only if both arms cleared
independently — was not built.

**Why it fires so rarely is the result, not the disappointment.** D2 gates on
`p_team >= 0.99`: we know the set is ours and cannot place the split.
`results/ask_deadness_signal.json` measures the belief's own probability that a
genuinely dead half-suit is entirely ours at **0.3377** on average. We do not
sit on completed half-suits because we know we own them and cannot split them.
We sit on them **because we do not know we own them.** That is not what the
95.3% allocation-error statistic invites a reader to assume — that statistic is
about declarations we made and got wrong, not about the ones we never made —
and it means the latency is an ownership-inference problem wearing an
allocation problem's clothes.

### D1 reached the duel and failed in both populations

600 pairings, 1,800 games at seed base 9,600,000 (`results/p44_screen.json`),
zero fallbacks, zero unfinished:

| arm | vs SESTINA | self-play | verdict |
|---|---|---|---|
| D1 | **−0.3233** [−0.527, −0.119] | **−0.2300** [−0.448, −0.012] | no |

Not a null. A significant negative in both populations, which is a stronger
result than a null and was predicted here with its mechanism before the run.

**And it worked.** The candidate's ask hit rate is **0.5245** against the
champion's **0.5184** on the same deals. D1 did exactly what it was built to
do — it landed more asks — and cost a third of a set a game doing it.

That is the finding worth carrying: **the ask hit rate is not a quantity to
maximise.** Under the no-bluff rule a failed ask publicly proves the asker
holds another card of that half-suit, which is precisely the fact a partner
needs to place a split. An ask into a half-suit our team wholly owns is not
waste — it is the engine's own mechanism for resolving the ownership it does
not yet know it has. D1 removed it, the hit rate rose, and the engine got
worse.

This closes the reading the cross-engine table invites. The corrected
head-to-head shows us 1.95 points behind on ask hit rate and calls it "the only
channel in which the two engines actually differ"; P44 shows that closing that
gap directly makes us weaker. **A hit-rate deficit is not necessarily a deficit
to close.**

### What was predicted, and what was not

The prediction above — D1 clears futility and fails the duel, from information
carried by the failed ask — is confirmed, including the sign and the mechanism.
The prediction that D2 was "the one with a case" is wrong in an instructive
way: it never got a case, because the precondition it assumed (that we know we
own the set) is false four times out of five.
