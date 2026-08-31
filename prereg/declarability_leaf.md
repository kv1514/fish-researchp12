# Pre-registration: score declarability inside the search, not beside it

**Registered 2026-08-30, before any duel of `lookahead_declare` was run and
before the bite screen's output was read.** What existed when this was written:
the term, its thirteen shape tests, the confirmation that the champion is
bit-identical at zero, and a measured 2.0x wall-clock cost. No margin of any
kind, and no bite number.

## The target is identified, and it is the same one as last time

`prereg/declaration_timing.md` decomposed what perfect knowledge of a teammate's
cards is worth by routing the same cheat to one decision at a time, 600 games:

| the cheat reaches | ceiling over honest | share |
|---|---|---|
| the declaration channel only | +1.0767 [+0.7979, +1.3554] | 0.316 |
| the ask channel only | +0.7600 [+0.4731, +1.0469] | 0.223 |
| both | +3.4100 [+3.1625, +3.6575] | 1.000 |

`D + K = 1.84` against `T = 3.41`. **46% of the prize — 1.57 sets a game —
is in neither channel alone.** Only an intervention that couples asking to
declaring can reach it.

`prereg/locate_term.md` tried the cheap coupling and it is closed: an additively
weighted one-ply ask feature, null at 3,000 pairs, **+0.047 [−0.075, +0.168]**,
and *diagnosed* — median size 0.0444 against an objective whose P(success) term
alone spans ~1.0, correlation +0.42 with the score it meant to correct, and a
change in the top-ranked ask in **3.9%** of positions. Raising the weight to
2.0, three times the shipped `turn` term, still touched only one ask in nine.

The conclusion recorded there is the premise here:

> The interaction worth 1.57 sets a game is not reachable by an additively
> weighted one-ply feature, whatever that feature measures, because such a
> feature can only nudge a ranking that the P(success) term dominates.

## What is different, stated as a mechanism and not as a hope

The champion already runs a belief-space search — `w_lookahead = 0.25`, depth 3,
beam 4 — whose currency is **cards banked before the possession ends**. Cards
are not what the game pays for. The error ledger says so precisely: 0.1676 of
our 0.1759 wrong declarations a game are **allocation** class, our team holding
all six of a half-suit and naming the wrong split, against 0.0083 ownership
errors.

`fish4.lookahead.declarability` adds the missing currency:

    D(B) = sum over live half-suits of  prod_c max_{p in team} M[c, p]

the expected number of half-suits whose split we could name correctly. Its
contrast with the ownership product `prod_c sum_{p in team} M[c, p]` **is** the
allocation/ownership split written in belief terms: the two are equal exactly
when each card's team mass sits on a single teammate, and a half-suit our team
certainly owns but splits 50/50 on every card scores 1.0 for ownership and
1/64 for declarability.

It is priced **per edge**, credited to the ask that creates it and discounted by
the chain that must land to reach it:

    V(B, d) = max_a  p_a * [ 1 + w * (D(B|a) - D(B)) + V(B|a, d-1) ]

Three things follow that a feature could not do:

1. **It multiplies rather than adds.** The gain enters inside a product of
   probabilities, so a chain that ends with a nameable half-suit is worth more
   *the whole way down*, not by a bonus averaged into one ask's score.
2. **It compounds.** A half-suit reachable only in two asks is invisible at
   depth 2 and visible at depth 3. `test_deeper_search_finds_more_declarability`
   asserts exactly that.
3. **It prices ORDER.** Securing a nameable half-suit first is worth
   `w * G * p * (1 - p)` — zero when everything is certain, maximal at a coin
   flip. That is a preference the cards-only chain provably cannot hold: on the
   constructed position in `tests4/test_declare_leaf.py` it scores the two asks
   *exactly* equally.

**It is refused at depth 1.** `lookahead_bonus` returns zeros at `depth <= 1`
whatever `w_declare` is, because a one-ply declarability bonus is the family
`locate` already closed and a knob that permitted it would invite that run
again.

## The weight is chosen by a rule fixed here, on a mechanism and never on a margin

`scripts4/declare_bite.py` measures, over real champion ask decisions and
through the real objective (`fish4.agent4._SCORE_RECORDER`, not a copy of it):
the size of the term against the score spread, its correlation with the score,
and its **bite** — the fraction of decisions where it changes the top-ranked
ask.

**The confirmation runs at the SMALLEST `w` in {0.25, 0.5, 1.0, 2.0} whose bite
falls in [15%, 60%].**

* **Smallest**, not largest: every point of bite is objective displaced, and
  this project's most durable finding is that displacing P(success) is
  expensive — a learned half-suit value with correct units cost 7.4 sets a pair.
* **15% floor** is ~4x `locate`'s 3.9%. A term that re-ranks 4% of asks
  produced a 95% interval of ±0.121 centred on 0.047; nothing that small can be
  the 1.57.
* **60% ceiling**: above that the term is not tie-breaking the objective, it is
  overriding it, and the duel would be measuring a different policy rather than
  a correction to this one.
* **If no `w` lands in that window, no duel is run.** The term is then either
  in `locate`'s regime or a replacement objective, and either way the
  registration closes without spending 3,000 pairs.

Bite is a mechanism quantity measured on the *champion's own* transcripts. It
cannot be traded for a margin, which is what makes selecting on it legitimate
where selecting on a screen's point estimate would not be.

## Design

`scripts4/duel.py`, duplicate deals, the pair as the independent unit.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same plus `lookahead_declare = w`, everything else identical —
  same `w_lookahead`, same depth, same beam.
* **3,000 pairs at fresh seeds.** Half-width ~0.11, which resolves the bar.
  There is no screen-then-confirm here because the weight is not being chosen
  from margins; there is nothing for a screen to select.
* Rules `wrong_distribution_outcome="opponent"` throughout.

## Decision rule, fixed in advance

**Primary:** mean paired difference in sets/game, Y − X, 95% interval.

**Ship bar: +0.15 sets/game** — the bar the signalling channel, the convention
and `locate` were all held to.

* lower bound > 0 and point ≥ +0.15 → **ships**, after re-measuring every
  affected figure and re-checking the site's move latency against the 2.0x cost.
* lower bound > 0, point < +0.15 → real but sub-bar. Recorded, not shipped.
* interval contains 0 → the coupling does not pay in the search either.
* upper bound < 0 → harmful, and the direction closes for good.

## Secondary outcomes, reported and not gating

* **Mean move index of our declarations.** The mechanism check. The
  teammate-oracle declares at move **39.2** against the honest **68.0**;
  `locate` moved it by **0.3**. If this term is doing what it claims, this
  number falls materially.
* Allocation and ownership wrong-declaration rates per game.
* Declarations per game by path (voluntary / gate / forced).
* Wall-clock per decision, which is a shipping cost and not a strength claim.

## Withdrawal conditions

Written to the rule this project has now learned three times — **a condition has
to be about something the treatment does not change, and answerable by the run
meant to answer it**:

* `IllegalAction`, a null action, or an unfinished game on either side → void.
* Y's mean moves per game differing from X's by more than 8 → the term is
  changing the length of games rather than their outcome, and the effect is
  reported as tempo rather than as declaration quality. `scripts4/duel.py` does
  not report this, so it is measured separately and deliberately, as it was for
  `locate`.

**There is deliberately no condition on the SHAPE of the effect across
weights.** `prereg/locate_term.md` registered one and it fired on noise: three
arms at 400 pairs have half-widths averaging 0.29 against a 0.15 bar, so
"monotone or single-peaked" was unevaluable whatever the term did. Only one
weight is duelled here, chosen on bite, so there is no shape to test and no
temptation to read one out of noise.

## What a null would mean

That declarability is the wrong *quantity*, not the wrong place to put it —
because the "wrong place" explanation is the one `locate` already used, and
running the same excuse twice is how a research programme stops learning. The
next question would then be whether the ceiling's 1.57 lives in **what the
oracle declares** rather than **when**, which `scripts4/declaration_timing.py`
can already answer by arm.

A null would **not** re-open the closed directions. Each was refuted on its own
terms.

---

# SCREEN OUTCOME and AMENDMENT, recorded 2026-08-30

## The screen fires the no-duel rule as registered

3,786 real champion ask decisions, 40 games, through the real objective:

| w_declare | median \|delta\| | p90 | / score spread | corr | bite |
|---|---|---|---|---|---|
| 0.25 | 0.0039 | 0.0254 | 0.006 | +0.600 | 0.5% |
| 1.00 | 0.0162 | 0.1034 | 0.026 | +0.603 | 2.0% |
| 2.00 | 0.0331 | 0.2083 | 0.052 | +0.606 | 3.7% |

**Nothing reaches the 15% floor.** The registered rule is unambiguous:

> If no `w` lands in that window, no duel is run.

**No duel is run at these weights.** The screen cost seven minutes and it
replaced a 3,000-pair confirmation, which is exactly what it was built for.

## The number that makes this more than a null

At `w = 2.0` the term is **five times the size** of `locate` — 0.052 of the
score spread against `locate`'s ~0.01 — and it bites **less**: 3.7% against
3.9%. Being bigger did not make it more decisive. The correlation says why:
**+0.60 here against `locate`'s +0.42.** It points where the objective already
points, harder than the term it replaced.

That is a hypothesis, not yet a finding: **declarability along a possession
chain may be largely a restatement of the cards banked along it.** Taking cards
is what makes half-suits nameable, so the two currencies may not be separable
inside a possession at all — in which case the search cannot use the second one
however heavily it is weighted.

## The amendment: extend the grid, with an a-priori ceiling and a prediction

The registered grid stopped at 2.0 and was chosen before the term's scale was
known. Extending it is an amendment and is recorded as one. It is legitimate
for the reason the registration already gave for selecting on bite at all:

> Bite is a mechanism quantity measured on the champion's own transcripts. It
> cannot be traded for a margin.

**The extension is `w` in {2, 4, 6}, and 6 is a ceiling fixed by argument, not
by trying.** A half-suit is six cards. At `w > 6`, making a half-suit nameable
is worth more to the search than taking every card in it, so the search would
prefer positions it can *name* to positions it can *win*. That is a replacement
objective, and this project has already measured what those cost: a learned
half-suit value with correct units and a calibrated model lost 7.4 sets a pair.
**If `w = 6` does not clear 15%, the registration closes with no duel.**

`w = 2.0` is re-run on the identical seeds as a replication check on the screen
itself.

## The prediction, stated before the extended grid is run

If the collinearity hypothesis is right:

* **(a)** bite stays below 15% even at `w = 6`, and
* **(b)** the correlation of the term against the **cards chain alone** — a new
  column, since the old one was against a score that already contains the chain
  and so could not say which part was being restated — is high and roughly
  flat across weights, while the correlation against the score with the chain
  removed is much lower.

**The falsifier:** bite clearing 15% at `w = 4` or `w = 6` while the cards
correlation stays moderate. That would mean the hypothesis is wrong and the
grid was simply mis-scaled, and a duel would then be run at the smallest
clearing weight exactly as originally registered.

---

# OUTCOME, recorded 2026-08-30: closed structurally, and no duel was run

`results/declare_bite.json`, written by `scripts4/declare_bite.py`.

## The extended grid confirms the prediction

Same 3,786 champion decisions, `w = 2.0` replicated exactly on the earlier
seeds:

| w_declare | median \|delta\| | / spread | r score | r cards | r rest | bite |
|---|---|---|---|---|---|---|
| 2.00 | 0.0331 | 0.052 | +0.606 | +0.617 | +0.570 | 3.7% |
| 4.00 | 0.0667 | 0.107 | +0.609 | +0.622 | +0.572 | 6.7% |
| 6.00 | 0.1004 | 0.162 | +0.611 | +0.625 | +0.573 | **8.7%** |

**Prediction (a) holds.** Bite does not reach 15% even at `w = 6`, the a-priori
ceiling. **The falsifier did not fire, so no duel is run** and the registration
closes as written. At `w = 6` the term is 16% of the score spread — sixteen
times `locate`'s size — and still re-ranks fewer than one ask in eleven.

**Prediction (b) is half right, and the half that fails matters.** The
correlation is high and flat, as predicted, but it is *not* specific to the
cards chain: +0.62 against the chain and +0.57 against the score with the chain
removed. So declarability along a possession is not merely a restatement of
cards banked — it is a restatement of the objective as a whole, P(success)
included, which is what one should expect of a quantity built as `p` times a
gain. That is the same diagnosis `locate` earned, reached by a different route.

## The real result is a theorem, and it closes more than this term

`ChainState.apply_success` collapses the taken card's row to a point mass on us
and runs one proportional-fitting sweep: scale the **target's** column by a
constant, then divide each row by its total. Both operations preserve ratios
among the non-target entries of a row, and the target is always an opponent.
Therefore, for any two teammates `t1, t2` and any card the chain does not take:

    M[c, t1] / M[c, t2]  is INVARIANT under the entire search tree

at every depth, every beam width, and **every leaf evaluation, a perfect one
included**. `tests4/test_declare_leaf.py` asserts it to 5e-16 over random
chains. A possession chain resolves allocation uncertainty on exactly the cards
it takes — at most `depth` of them — and on nothing else in the deal.

`scripts4/allocation_locus.py` prices what that costs. Allocation uncertainty
per card, in nats, is `log(sum_team M[c,p]) - log(max_team M[c,p])`; summed over
a half-suit it is exactly `log(ownership) - log(declarability)`. A chain can
take card `c` only from an opponent, so at most a `1 - team_mass_c` share of
that card's deficit is even in principle reachable. Over 20,472
(decision, live half-suit) pairs from real champion play, deficit-weighted:

| half-suits with P(our team owns it) | pairs | unreachable by ANY possession chain |
|---|---|---|
| any | 20,472 | 40.7% |
| ≥ 0.05 | 3,605 | 58.2% |
| ≥ 0.5 | 609 | 84.5% |
| **≥ 0.9** | **91** | **100.0%** |

**Read the bottom row.** The half-suits our team almost certainly owns are
exactly the allocation case — 0.1676 of our 0.1759 wrong declarations a game —
and every card in them is on our own side, so a search that can only take cards
from opponents cannot touch **any** of that uncertainty. Not at 100 plies, not
with a perfect leaf.

This is not a null. It is a proof that the direction the `locate` null pointed
at was the wrong one, and it says so before the 3,000-pair duel rather than
after.

## What ships

Nothing. `lookahead_declare` stays 0.0, `V06_DEPLOYED` is untouched, and the
champion is bit-identical at the default — asserted by test, not by inspection.
The term, the theorem test, and both instruments stay in the tree because the
next attempt on the interaction has to clear the bar this one just established.

## Where the 1.57 actually has to be attacked

The theorem says which lever is left. The teammate/teammate ratio on a card
neither side can ask for moves only on **public events** — a teammate asking
(proving they lack that card and hold one of the half-suit), or being asked and
answering. Those are inputs to the belief tracker, not to any search.

Two consequences, and neither is a repeat of a closed direction:

1. **The miss is priced at zero and it is the most informative outcome in the
   game.** `possession_value` says so explicitly: "a miss ends the possession,
   so it contributes no cards." True in cards, and false in information — a
   miss publicly proves where a card is *not*. Nothing in the twelve-term basis
   prices what our own miss teaches our partners about our hand.
2. **How much of the teammate split is recoverable from the public record at
   all, and how much does the tracker already recover?** That is an off-policy
   fit question, answerable without a duel, and it bounds every future attempt
   the way this theorem just bounded the search.

The second is the cheaper and it gates the first: if the tracker already
extracts nearly everything the record contains, the ceiling's 1.57 is not
inference at all and the search should move to what the oracle *does* rather
than what it *knows*.
