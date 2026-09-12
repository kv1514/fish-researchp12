# Pre-registration: charge an ask for the entry point it spends

**Registered 2026-08-30, before any duel of `w_reach` was run and before any
margin of any kind existed.** What existed when this was written: the term, its
seven shape tests, the confirmation that the champion is bit-identical at zero,
and the bite screen below — which contains no margin.

## This is the first intervention in six that is not about knowing more

Split gamma, the at-ask covariate, the convention's decoder, `locate`, the
declarability leaf and the claim gamma were each an attempt to give the engine a
better belief. All six are measured and none of them bought anything in play.
The error ledger has been pointing somewhere else the whole time.

`prereg/claim_gamma.md` finally read it. 480 games, our seats:

| path | per game | error rate |
|---|---|---|
| voluntary | 3.548 | **0.06%** |
| gate | 0.221 | **19.8%** |
| forced | 0.206 | **41.4%** |

**62 of 63 wrong declarations come from `gate` and `forced`** — decisions with
*no alternative*. `gate` fires when the ask we were about to make cannot land;
`forced` when no legal ask exists. Calibration cannot help a choice with one
option, and `prereg/forced_exhaustive.md` already ships the best play once
stuck. What has never been attempted is **not getting stuck**.

## It is steerable, and it is not what it looks like

`scripts4/forced_locus.py`, 15,929 decisions over 150 games. Every figure is a
**residual against control decisions with the same cards still in play**,
because `live_asks` decays with the game and every stuck decision is late; the
uncontrolled version of this table showed a gradient for a feature that merely
decays with time, and did.

| lead (seat's own decisions) | 0 | 1 | 2 | 3 | 5 | 8 | 12 |
|---|---|---|---|---|---|---|---|
| live_asks residual | −10.2 | −10.4 | −9.8 | −8.8 | **−6.9** | **−4.0** | +0.6 |
| hand residual | +0.60 | +0.89 | +0.83 | +0.73 | +0.58 | +0.72 | +0.57 |

Visible **five to eight of the seat's own decisions ahead** — thirty to fifty
table moves. And `hand` is **positive at every lead**: a seat about to be stuck
holds *more* cards than the control while having ten fewer live asks. You do not
get forced by running out of cards. You get forced by holding cards in half-suits
where everything else is on your own side.

## The term

    reach = -pi * prod over the other five cards of (1 - P(an opponent holds it))

* `pi` — it spends nothing if it does not land.
* the product — P(the half-suit stops being askable by us). Taking the last card
  an opponent held closes it as an entry point; taking one of four leaves it
  open.
* the asked card is **excluded**: we hold it either way once the ask lands, so it
  cannot keep the half-suit open. Including it would zero the term precisely on a
  certain steal, which is the bug `claim`, `concent` and `locate` all shipped
  with at v1.
* **Negative**, so a positive weight penalises. Asserted over random beliefs.

Nothing in the basis prices this. `deplete` rewards draining an *opponent*;
`scarce` and `concent` reward team share and concentration — both of which
*consume* entry points, and neither of which is charged for them.

**And the possession search cannot substitute for it.** The theorem in
`prereg/declarability_leaf.md` says a chain cannot change a teammate/teammate
ratio because `apply_success` only moves cards from an opponent to us — which is
exactly why askability, a function of opponents' holdings, is the one thing that
search *can* see. That is an argument for the direction, not for this shape.

## The shape was chosen on the bite screen, and that is recorded

**v1 divided by `n_askable`** — the share of our entry points spent. That shape
cannot reach the decision: median 0.0064 of a score whose P(success) part spans
~1.0 at `w = 0.3`, a top-ask change in **1.6%** of positions, and only **7.6%**
at `w = 1.2`. That is `locate`'s `1/u` again, and `locate` is a measured null.

**v2 drops the divisor**, on the argument that what a seat walks toward is *zero*
entry points and each one lost is one step nearer however many remain — so the
cost is closer to constant than to proportional. It is also the shape with the
fewest free choices.

`scripts4/term_bite.py reach`, 3,780 real champion decisions:

| w | median \|delta\| | / spread | corr | bite |
|---|---|---|---|---|
| 0.30 | 0.0242 | 0.037 | −0.473 | 5.1% |
| 0.60 | 0.0484 | 0.074 | −0.473 | 11.5% |
| **0.80** | **0.0645** | **0.099** | **−0.473** | **15.2%** |
| 1.00 | 0.0807 | 0.123 | −0.473 | 19.9% |
| 1.60 | 0.1291 | 0.197 | −0.473 | 28.5% |

**The confirmation runs at `w = 0.80`** — the smallest weight whose bite lands in
the **[15%, 60%]** window, the identical rule `prereg/declarability_leaf.md`
registered and the identical justification: bite is a mechanism quantity on the
champion's own transcripts and cannot be traded for a margin, while every point
of it is objective displaced.

Note the correlation: **−0.473**, where `locate`'s was **+0.42**. This term
points *against* the objective rather than restating it, which is what a term
that prices something nothing else prices should do.

## Design of the confirmation

`scripts4/duel.py`, duplicate deals, the pair as the independent unit.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same plus `w_reach = 0.8`, everything else identical.
* **3,000 pairs at fresh seeds**, half-width ~0.11.
* Rules `wrong_distribution_outcome="opponent"` throughout.

## Decision rule, fixed in advance

**Primary:** mean paired difference in sets/game, Y − X, 95% interval.

**Ship bar: +0.15 sets/game.**

* lower bound > 0 and point ≥ +0.15 → **ships**, after re-measuring every
  affected figure.
* lower bound > 0, point < +0.15 → real but sub-bar. Recorded, not shipped.
* interval contains 0 → the trajectory is visible and not worth steering.
* upper bound < 0 → harmful, and the direction closes.

## A mechanism screen first, with its rules fixed here

`scripts4/path_ledger.py --vs=self --arm=w_reach=0.8`, 480 games, against the
same run at the default. Both rules are about quantities the treatment is meant
to move and both are answerable by that run.

* **`gate` + `forced` declarations per game must fall.** They are 0.427 at the
  default. If they do not fall, the term is not reaching the trajectory it was
  built from and **no duel is run.**
* **Total declarations per game must not fall by more than 10%.** This is the
  term's stated risk, not an afterthought: `reach` is largest exactly when our
  team already holds the rest of the half-suit, so it penalises the ask that
  **completes a set** — the ask that banks one. If the engine starts declining
  sets to stay flexible, that shows up here, and **no duel is run at this
  weight.**

## Secondary outcomes, reported and not gating

* Wrong declarations per game, by path and by class (allocation / ownership).
* Mean move index of our declarations.
* `live_asks` residual at leads 3, 5 and 8 — the diagnostic re-run on the arm.
  If the term works, that curve should flatten.

## Withdrawal conditions

* `IllegalAction`, a null action, or an unfinished game on either side → void.
* Y's mean moves per game differing from X's by more than 8 → reported as tempo
  rather than as declaration quality. Measured separately; `duel.py` does not
  report it.

## What a null would mean

That being forced is *visible* and not *avoidable* — that the asks which would
preserve reach are worth less than what they give up, and the engine's apparent
walk into a corner is the correct price of taking cards. That would be a real
finding: it would say the 62 errors are not a defect but the cost of the game,
and it would close the last direction the error ledger points at.

---

# SCREEN OUTCOME, recorded 2026-08-30: both rules fire, no duel is run

## The registered screen

`scripts4/path_ledger.py --vs=self`, 480 games, identical deals, our seats only.
Baseline `results/path_ledger_self.json`, arm
`results/path_ledger_self_w_reach0.8.json`:

| path | baseline | /game | wrong | `w_reach = 0.8` | /game | wrong |
|---|---|---|---|---|---|---|
| exact | 252 | 0.525 | 0 | 276 | 0.575 | 0 |
| voluntary | 1703 | **3.548** | 1 | 1148 | **2.392** | 1 |
| gate | 106 | **0.221** | 21 | 281 | **0.585** | 63 |
| forced | 99 | 0.206 | 41 | 103 | 0.215 | 40 |
| **TOTAL** | 2160 | **4.500** | **63** | 1808 | **3.767** | **104** |
| wrong per game | | 0.1313 | | | **0.2167** | |
| margin | | 0.0 | | | **−1.6708** | |

**Both pre-registered rules fire.**

> `gate` + `forced` declarations per game must fall.

They were 0.427. They are **0.800** — nearly doubled.

> Total declarations per game must not fall by more than 10%.

They fell **16.3%**.

**No duel is run.** The margin of −1.67 sets a game is not a pre-registered
outcome and is recorded only because it points the same way.

## The failure is exactly the risk the registration named, and it is quantified

> `reach` is largest exactly when our team already holds the rest of the
> half-suit, so it penalises the ask that **completes a set** — the ask that
> banks one. If the engine starts declining sets to stay flexible, that shows
> up here.

It did. Voluntary declarations fall **33%** and the displaced ones reappear in
`gate` — up **165%**, at a 22.4% error rate. The term did not stop the engine
getting stuck; it stopped the engine *finishing*, and pushed declarations out of
the path with a 0.06% error rate into one with 22%.

## A POST-HOC diagnostic, labelled as such

`forced_locus.json` showed stuck seats holding *more* cards with *fewer* live
asks, and this term assumed the causality: completing half-suits strands you.
The screen says that reading is backwards, so the natural check is the opposite
sign — **rewarding** the ask that completes a half-suit. **This was chosen after
seeing the screen and is a diagnostic, not a registered arm.**

| arm | gate+forced /game | wrong /game | margin |
|---|---|---|---|
| baseline | 0.427 | 0.1313 | 0.0 |
| `w_reach = +0.8` | 0.800 | 0.2167 | −1.671 |
| `w_reach = −0.4` | **0.348** | **0.1000** | −0.075 |
| `w_reach = −0.8` | **0.330** | 0.1042 | −0.100 |

**The mechanism reverses cleanly.** A negative weight cuts stuck declarations by
19–23% and wrong declarations by 24%, while voluntary declarations hold at
3.49–3.59. So the trajectory *is* steerable, and in the direction opposite to
the one the term was built for: the clog is caused by **not finishing**
half-suits, not by finishing them.

**And the margin does not follow.** −0.075 and −0.100, both negative, neither
anywhere near the +0.15 bar. `path_ledger` reports no interval, so these are
consistent with zero rather than evidence of harm — but nothing here suggests a
3,000-pair confirmation would find +0.15, and running one on a weight found by
flipping a sign after reading a screen is the forking path this project
forbids. **No confirmation is registered.**

## What this closes, and it is the bound rather than the term

The registration's own caveat is what came true:

> It is an upper bound and a loose one. The counterfactual for a forced
> declaration is not "no error" — the half-suit still has to be resolved, and if
> we do not declare it someone else does, possibly correctly.

**Removing a quarter of the wrong declarations bought nothing.** The 0.258
sets-a-game bound was loose in exactly that way, and the 62 errors in the ledger
are not recoverable value — they are the price of resolving half-suits that had
to be resolved by someone.

That is a different kind of null from the six before it. Those were better
*beliefs* that bought nothing. This is a better *position*, achieved and
measured, that also bought nothing. Together they say the ledger's remaining
errors are not a defect to be fixed but the cost of the game as this engine
plays it.
