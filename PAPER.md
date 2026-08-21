# Exact Belief Tracking and the Limits of Search in Six-Player Literature

**A computational study of a team-based imperfect-information card game**

---

## Abstract

Literature (also called Fish or Canadian Fish) is a six-player, two-team,
imperfect-information card game in which players interrogate opponents for
specific cards and score by declaring the exact distribution of a six-card
half-suit among their own team. We build a rules-exact simulator, an
information boundary enforced by construction, and a belief tracker that is
*exact* rather than approximate, exploiting the fact that every card
movement in Literature is public.

Three results are worth reporting.

First, **belief tracking dominates**. An agent that merely chains every
logical implication of the public record beats a public-information
heuristic by 11.86 sets per duplicate deal-pair (95% CI [11.66, 12.06], 400
pairs, winning every single pair). Probabilistic reasoning over
deal-consistent worlds adds a further 2.07 sets [1.50, 2.63].

Second, and more surprisingly, **search does not help, and we can say why**.
Two independent search designs — determinized Monte Carlo (PIMC) and
Information-Set MCTS — lost decisively to the very policy they were built
on. We measured the cause: the standard deviation of a position's value
across possible hidden layouts is about 2.4x the gap between the best and
worst candidate move. Any search that evaluates different candidates against
different sampled layouts produces a ranking dominated by luck. Enforcing
common random numbers removes the deficit entirely, but a threshold sweep
shows agreement with optimal play converging on the no-search prior *from
below*: no configuration of search beats not searching, and doubling the
sampled-world count changes nothing. The bottleneck is the evaluation
target, not the search machinery.

Acting on that diagnosis produced the study's largest single improvement,
from a term the baseline ignored entirely: penalizing asks that would hand
the turn to a card-rich opponent if they fail is worth **0.81 sets per
duplicate deal-pair** (95% CI [0.53, 1.08]). That elaborate search machinery
could not recover a tenth of what one neglected term in the objective
supplies is the practical form of our central claim.

Third, we establish **absolute rather than relative strength**. Small
endgames are solved exactly, which requires noting that the Literature state
graph is *cyclic* — two opponents can trade a card indefinitely and return to
an identical position — so backward induction does not terminate and the
game must be solved by layered value iteration. Against these exact
solutions, belief-tracking agents choose a provably optimal move in **100%
of positions where the hidden information has already been resolved**, and
in 76.0% of positions where genuine uncertainty remains.

We additionally report that six-player Literature is seat-balanced (no
measurable first-move advantage), that the synthetic "8s and jokers"
half-suit behaves statistically like any natural half-suit, and that claim
confidence is bimodal, which makes the widely-tuned "claim threshold"
largely a no-op.

---

## 1. The game

Six players sit alternately in two teams: seats 0, 2, 4 against 1, 3, 5. The
deck is partitioned into **half-suits** of six cards. Our primary variant
uses 54 cards and nine half-suits: the eight natural half-suits (2-7 and
9-A of each suit) plus a ninth composed of the four 8s and two individually
identified jokers, a **Red Joker** and a **Black Joker**. Each player is
dealt nine cards. The classic 48-card, eight-half-suit variant is also
supported.

On turn, a player either **asks** or **claims**.

An ask names an opponent and a specific card. It is legal only if the asker
holds at least one card of that card's half-suit and does not hold the card
itself. If the opponent has it, the card transfers **face up** and the asker
keeps the turn; otherwise the turn passes to the opponent who was asked.

A claim names a half-suit and declares **which teammate holds each of its
six cards**. If the declaration is exactly right, the claiming team scores
the half-suit. If any of the six is with an opponent, the opposing team
scores it. If all six are within the claiming team but the distribution is
wrong, the half-suit is nulled and nobody scores. The requirement to name
the exact distribution, not merely to assert possession, is what makes
Literature a game about inference rather than collection.

### 1.1 A structural property: the game can go forever

Nothing in the rules forces progress. Two opponents can pass a card back and
forth and return to an identical position. We confirmed this by search: the
state graph contains cycles. Consequently **termination is a property of the
players, not of the rules**, and any claim that "every game ends" describes
an agent's stalling rule rather than Literature itself. Our agents therefore
carry an explicit progress rule (gamble a claim when no half-suit has
resolved within a window), and our exact solver treats an unbroken cycle as
scoring nothing further for either side — which correctly predicts that a
side able only to lose by claiming will stall indefinitely, exactly as human
Literature stalemates behave.

---

## 2. Information integrity

An imperfect-information study is worthless if the agents can see the hidden
state, and the failure mode is usually subtle rather than flagrant. We
enforce the boundary three ways.

**Structural.** The engine's `GameState` never reaches a policy. Policies
consume only an `Observation`: their own hand, the public event log, public
hand counts, resolved half-suits, whose turn it is, and the rules.

**Proved by reconstruction.** `Observation.reconstruct` rebuilds a seat's
entire view from nothing but (rules, that seat's initial hand, the public
event log). Tests assert the engine-provided observation is *identical* to
that reconstruction at every step of full games, for all six seats. Any
leaked private state would make the two diverge.

**Proved by invariance.** Learned features get the same treatment: tests
assert a feature vector is unchanged when the hidden cards are replaced by
any *other* layout consistent with the public record. A quantity that
depends on unobservable detail cannot survive that test.

One real leak was found this way and fixed: agent random seeds were derived
from the deal seed, so a sufficiently determined policy could in principle
invert its own seed to recover the layout. Seeds now come from an
independent stream and are recorded for reproducibility rather than coupled
to the deal.

We distinguish carefully between training and acting. Our value network is
trained on true states; no acting policy ever sees one. That line is what
makes the distinction meaningful rather than decorative.

---

## 3. Exact belief tracking

The central observation that shapes the engine:

> **Every card movement in Literature is public.** A successful ask names
> the card that moved. A claim reveals all six locations. Nothing changes
> hands unobserved.

It follows that the current location of every card is a deterministic
function of the **initial deal** and the public log. All hidden-state
inference therefore reduces to constraints on the initial deal, and those
constraints are of exactly three kinds:

1. **Candidate sets.** Per card, a six-bit mask of players who may have been
   dealt it. A failed ask excludes the target; a successful ask pins the
   card; asking for a card excludes the asker (under standard no-bluff
   rules); a claim pins all six.
2. **Exact counts.** Every player was dealt exactly nine cards (or eight).
3. **Disjunctions.** A legal ask certifies that the asker held *at least
   one* card of that half-suit at that moment: an OR-constraint over the
   cards not yet publicly located.

Propagation combines candidate filtering, exact-count reasoning in both
directions (a player whose quota is exhausted can hold nothing else; a
player whose possibilities exactly fill their quota holds all of them),
OR unit-propagation, OR subsumption, and a disjoint-OR pigeonhole rule.

We are deliberately precise about what this is and is not:

- It is **sound**. Every fact asserted as certain is genuinely implied. The
  true world is never excluded from the support. Verified continuously by
  truth-in-support checks at every step for all six seats plus an external
  spectator, and by replay-validating sampled worlds against the entire
  public history through an independent code path.
- It is **not complete**. Propagation is not full arc-consistency over the
  combined system, so exotic positions may contain a logically certain fact
  the propagator leaves merely near-certain. Such facts still appear as
  probability ~1.0 in sampling, so agents lose the proof but not the
  information.
- Sampling is **not uniform** over the consistent set. Constraint seeding
  and quota weighting skew the draws. Reported probabilities are therefore
  good heuristic estimates, not exact posteriors. Correcting this remains
  open.

### 3.1 Performance

Profiling contradicted the intuition that the rule engine would be the
bottleneck. World sampling cost 736 microseconds per world, roughly thirty
times the per-decision cost of belief updates, while rule application never
appeared near the top. Caching the constraint scaffolding across draws, and
satisfying disjoint OR-constraints during construction rather than repairing
them afterwards, reduced this to 178 microseconds, a 4.1x improvement with
no change of language. A compiled core is not yet justified; it becomes
justified when rule application, not inference, is measured to dominate.

---

## 4. Evaluation methodology

Raw win rates in a card game are dominated by the deal. Every result here
uses **duplicate (paired) deals**: each deal is played twice with the teams
swapped, on identical cards, an identical rotated starting seat, and
identical agent randomness. Only the policy assignment differs, so per-pair
set differentials are i.i.d. across deals and confidence intervals mean what
they say.

Ratings use a **regularized MAP Bradley-Terry** fit by damped Newton with
full-covariance standard errors. This matters more than it might appear.
Shutouts are common in this ladder, and the maximum-likelihood rating gap
between a policy that never loses and one that never wins is *infinite*. Our
first implementation used a fixed-iteration gradient loop and silently
reported wherever it happened to stop; those ratings were retracted.
Separated policies are now flagged so their numbers are read as bounds
rather than measurements.

We report two statistics per duel because they have different sensitivity:
the paired **score** (sign only, with a Wilson interval) and the mean
**set differential** (magnitude, with a Student-t interval). Where they
disagree we say so rather than choosing the flattering one.

---

## 5. Results

### 5.1 The strength ladder

400 duplicate deal-pairs per cell (120 where the probabilistic agent is
involved):

| matchup | pair score | 95% CI | set diff per pair |
|---|---|---|---|
| random vs heuristic | 0.000 | [0, .010] | -12.94 ± 0.19 |
| random vs memory | 0.000 | [0, .010] | -16.38 ± 0.11 |
| heuristic vs memory | 0.000 | [0, .010] | -11.86 ± 0.20 |
| heuristic vs probabilistic | 0.000 | [0, .031] | -12.08 ± 0.43 |
| memory vs probabilistic | 0.237 | [.170, .321] | -2.07 ± 0.57 |

The `memory` agent acts only on facts it can prove; `probabilistic` samples
deal-consistent worlds and plays the probabilities. The gap from
public-information heuristics to proof-based play (11.86 sets per pair,
with zero upsets in 400 pairs) is far larger than the gap from proof to
probability (2.07). In human terms: most of the skill below expert level is
bookkeeping, and the expert margin is judgement layered on top of it.

### 5.2 Search loses, and the reason is measurable

This was the most instructive result of the study.

| search design | pair score for search vs its own prior |
|---|---|
| PIMC, independent rollout batches | 0.146 |
| Information-Set MCTS, per-iteration resampling | 0.062 |
| value network on belief features | 0.150 |
| value network on perfect-information features | 0.250 |
| + quiescence to end of possession | 0.125 |
| **paired search, common random numbers** | **0.562**, CI straddles 0.5 |

Rather than tune blindly, we measured two things.

**The evaluation function was fine.** Correlation between the
depth-limited evaluation and the true final set differential was **+0.73**.

**The variance was not.** The standard deviation of a *single action's*
value across sampled hidden layouts was **0.698**; the mean gap between the
best and worst candidate action was **0.293**. A noise-to-signal ratio of
**2.4**. Any search that allocates different sampled worlds to different
candidates — which is precisely what UCT does by construction, and what
independent PIMC batches do by accident — is ranking luck rather than merit.

Forcing all candidates onto identical worlds with identical rollout seeds
(common random numbers), and overriding the prior only on a significant
paired difference, eliminated the deficit entirely.

But it did not create a surplus. A threshold sweep against exact ground
truth is unambiguous:

| configuration | agreement under uncertainty | mean value loss (sets) |
|---|---|---|
| **prior, no search** | **76.0%** | **0.104** |
| paired search t=1.0 | 73.5% | 0.116 |
| paired search t=1.5 | 74.0% | 0.122 |
| paired search t=2.5 | 75.5% | 0.110 |
| paired search t=4.0 | 75.5% | 0.110 |
| paired search t=8.0 | 75.5% | 0.110 |
| paired search, 24 worlds, t=2.5 | 75.5% | 0.110 |
| value search t=1.0 | 70.5% | 0.147 |

Agreement rises monotonically as the override bar is raised and converges on
the prior **from below**, the exact signature of false-positive overrides
under multiple comparisons. At a strict threshold search simply stops
overriding and becomes the prior.

The conclusion is stronger than "our search needs tuning". **No setting of
the search beats not searching, and doubling the world count changes
nothing.** The machinery, the sample size and the statistics are not the
binding constraint. The *evaluation target* is: neither depth-limited
rollouts nor a learned value function ranks candidate asks better than the
prior's simple success probability. This is where we would direct further
work, and it is a caution for anyone assuming that lookahead is
automatically an improvement in an imperfect-information team game.

### 5.3 Absolute strength: agreement with exact optimal play

Every metric above is relative. To obtain an absolute one we solve small
endgames exactly and ask how often each agent chooses a provably optimal
move. Because the state graph is cyclic (Section 1.1), this requires layered
value iteration: claims strictly reduce the number of unresolved half-suits
and so always descend to a simpler layer, while asks and passes cycle within
a layer and are solved to a fixpoint, with an unbroken cycle valued at zero
further score.

We report two regimes separately because they mean different things.
*Resolved* positions are those where every remaining card's location is
already publicly determined: hidden information is not a factor, the
perfect-information optimum *is* the optimum, and a strong agent should reach
100%. *Uncertain* positions retain genuine hidden information, where
agreement is a comparative signal and 100% is not the target.

327 positions, 130 of them resolved:

| agent | resolved | uncertain | mean value loss |
|---|---|---|---|
| probabilistic | **100.0%** | **76.0%** | **0.104** |
| memory | **100.0%** | 69.0% | 0.138 |
| paired search | 100.0% | 75.5% | 0.110 |
| value search | 100.0% | 70.5% | 0.147 |
| heuristic | 66.2% | 47.7% | 0.275 |
| random | 48.5% | 28.9% | 0.465 |

Belief-tracking agents are **exactly optimal in every position where
optimality is checkable**. This is a stronger statement than any tournament
result, and it also bounds where remaining improvement can come from: not
from the endgame, which is solved, but from midgame positions too large to
enumerate.

The benchmark also earned its keep as a debugging instrument. In an earlier
run, value search scored 127/130 on *resolved* positions — failing three
cases with no hidden information at all. Dissection showed all three were
search overriding a correct prior, each time selecting an action worth -1.00
when +1.00 was available: in a fully determined position every sampled world
is identical, the paired difference has zero variance, and the significance
test degenerates into trusting the network, which was extrapolating badly on
lopsided endgames rare in its training data. The fix is the Literature
analogue of a chess tablebase: when an agent's own beliefs pin every live
card, solve the position instead of estimating it. This restored 130/130 and
is leak-free by construction, since the reconstruction uses only public
events plus the agent's own hand and refuses unless every live card is
pinned.

### 5.4 When to claim

The claim threshold is the parameter practitioners most often tune. We swept
it directly, 150 duplicate deal-pairs per cell, everything else identical:

| vs baseline 0.97 | pair score for 0.97 | set diff per pair | verdict |
|---|---|---|---|
| 0.60 | 0.590 [0.510, 0.666] | +0.71 [+0.34, +1.08] | 0.97 better |
| 0.70 | 0.570 [0.490, 0.647] | +0.45 [+0.18, +0.72] | 0.97 better |
| 0.85 | 0.497 [0.418, 0.576] | -0.01 [-0.09, +0.06] | indistinguishable |
| 0.999 | 0.500 [0.421, 0.579] | +0.00 [+0.00, +0.00] | identical play |

Two findings, the first of which refutes a prediction we ourselves made.

We had built an expected-value model of claiming versus waiting, which
derived an optimal threshold near 0.70. **The experiment falsified it**:
claiming at 0.70 is measurably worse than at 0.97. The model's error is
identifiable — it treated the resolution of an unknown teammate split as
roughly a coin flip, when in practice continued asking localizes teammate
holdings far more reliably, making patience worth more than modelled.

More interesting is the second: comparing 0.97 with 0.999 produced a
differential of **exactly zero across 150 paired deals**. The two policies
never once diverged. Claim confidence is **bimodal**: a strong player either
knows the distribution or does not, and essentially never occupies the
narrow band that threshold-tuning is meant to arbitrate. Effort is better
spent making the split *knowable* than deciding when to gamble on it.

### 5.5 What actually improves the strongest policy

Having established that search does not help, we attacked the evaluation
target directly, adding candidate terms to the ask score one at a time. Each
was measured against the identical baseline over 600 duplicate deal-pairs
(14,400 games in total). Positive values favour the new term.

| added term | gain, sets per deal-pair | 95% CI | verdict |
|---|---|---|---|
| turn-risk, weight 0.60 | **+0.81** | [+0.53, +1.08] | real |
| belief samples 32 to 96 | **+0.54** | [+0.25, +0.82] | real |
| scarcity, weight 0.20 | **+0.55** | [+0.26, +0.83] | real |
| turn-risk, weight 0.15 | **+0.48** | [+0.21, +0.75] | real |
| reveal cost, weight 0.15 | +0.29 | [+0.01, +0.57] | marginal |
| reveal cost, weight 0.05 | +0.14 | [-0.14, +0.42] | none |
| depletion bonus, weight 0.15 | -0.01 | [-0.26, +0.24] | none |

The largest single gain comes from a term the baseline ignored entirely:
**which opponent receives the turn when an ask fails**. Penalizing asks that
would hand the turn to a card-rich opponent, applied only to the failure
branch, is worth 0.81 sets per deal-pair. That the strongest policy was
throwing this away, while elaborate search machinery could not find a
tenth of it, is the clearest illustration of the paper's central claim: in
this game the objective, not the depth of search, is what binds.

Two null results are worth stating because they contradict common intuition.
A bonus for draining an opponent toward zero cards did **nothing**
(-0.01 [-0.26, +0.24]); what matters about hand size is the danger of arming
a large hand, not the appeal of emptying a small one. And information
leakage, though detectable, is small: penalizing the exposure of a
previously unshown half-suit gained only +0.29 with an interval barely
excluding zero.

Finally, belief precision has not saturated. Raising the number of sampled
layouts from 32 to 96 still gains +0.54 sets per pair, having already gained
+0.93 going from 8 to 32.

#### Dose-response, and why these terms are tie-breakers

Sweeping each winning term across a wider range reveals the same inverted-U
in both, at 600 duplicate deal-pairs per cell:

| weight | turn-risk | scarcity |
|---|---|---|
| light (0.6 / 0.2) | **+0.56** [+0.27, +0.86] | **+0.65** [+0.37, +0.93] |
| medium (1.0 / 0.4) | +0.10 [-0.19, +0.39] | +0.57 [+0.29, +0.86] |
| heavy (1.6 / 0.8) | **-1.51** [-1.82, -1.20] | **-1.32** [-1.61, -1.03] |

A clean dose-response curve is itself evidence that the effects are real
rather than sampling noise, and its shape tells us what kind of quantity
these terms are. They are **tie-breakers**: valuable for discriminating
among asks of comparable success probability, destructive once they begin
to override that probability. Success likelihood remains the dominant term.

The two also **stack**. At their individual optima the combination gains
**+1.41 sets per deal-pair** [+1.11, +1.70], slightly more than the sum of
+0.56 and +0.65, indicating the terms discriminate between different asks
rather than re-ranking the same ones. This combined policy is a substantial
improvement over the prior champion, and it was obtained purely by adding
neglected terms to the objective, with no search at all.

#### Why margins against a common baseline are not a ranking

Belief precision and the new ask terms turned out **not** to be additive,
and the way we discovered that is worth stating.

Measured against the same baseline over 800 duplicate deal-pairs each, the
combined policy with 96 sampled layouts gained +1.53 sets per pair while the
same policy with 32 gained +1.28. The natural reading is that more sampling
is better. Played **directly against each other** over 400 pairs, they are
indistinguishable: +0.10 [-0.25, +0.44], pair score 0.49.

So the extra sampling, worth +0.54 sets per pair on top of the *plain*
belief policy, is worth nothing measurable once the ask-scoring terms are in
place. The two improvements were substitutes rather than complements: better
ranking of asks and sharper estimates of where cards are were, to a large
extent, buying the same thing.

The methodological point generalizes. Two candidates measured against a
shared baseline can have overlapping intervals and non-overlapping margins,
and neither tells you how they fare against each other. Our promotion rule
requires beating the *incumbent* directly, which is what caught this. We
therefore rejected the 96-sample variant: three times the inference cost for
no demonstrable gain, and slower advice in the live coach.

#### A methodological warning

The first version of this experiment reported the **opposite** conclusion
for turn-risk, at n=1000 per cell, with tight intervals: all three weights
appeared clearly harmful. The ablated agent had accidentally normalized a
different term by a factor of six, so setting the new weight to zero did not
reproduce the baseline and every cell compared two changes at once. The
confound was caught only by noticing an implausible monotonic pattern in the
magnitudes.

We now enforce by test that an ablated agent reduces decision-for-decision
to the baseline when its new weights are zero, and that a non-zero weight
demonstrably changes some decision. The affected results are marked
RETRACTED in the experiment registry rather than deleted. We report this
because a large sample size and a narrow confidence interval provide no
protection whatsoever against a confounded comparison, and the failure is
easy to miss precisely because the output looks authoritative.

### 5.6 Findings about the game itself

**Turn retention is the single best summary statistic of skill.** Measuring
"possessions" (runs of consecutive successful asks before losing the turn)
over 400-game tables:

| tier | cards gained per possession | possessions gaining nothing |
|---|---|---|
| memory | 0.68 | 62% |
| probabilistic | 1.61 | 40% |

Stronger tables also have *fewer, longer* possessions (16,457 versus 30,055
for the same number of games), because the turn changes hands less often.

**Ask accuracy peaks in the midgame**, not the opening: 57.7%, 65.9%, 63.4%
across thirds of the game for the probabilistic tier (38.1%, 43.5%, 40.8%
for memory). Information accumulates faster than cards leave the table, then
late-game attrition erodes the edge. Openings are the least informed part of
the game.

**Failed asks are normal.** Even strong play fails 37.8% of asks (59.2% at
the memory tier). Failure rate is a poor measure of skill; cards per
possession is a good one.

**There is no measurable seat or first-move advantage.** Set differential
for the starting player's team, with the starting seat rotated across deals,
was -0.03 [-0.28, +0.21] at the probabilistic tier and -0.13 [-0.37, +0.12]
at the memory tier. Both intervals comfortably contain zero at n=400.

**The 8s-and-jokers half-suit is not special.** Despite the intuition that a
synthetic half-suit assembled from four 8s and two jokers should resolve
later or null more often, mean resolution order was 3.97 versus 4.00 for
natural half-suits, and null rate 4.75% versus 6.0% (n=400 versus 3,200).
Neither difference is meaningful, at either skill tier. We note the caveat
that this is measured under agents that do not deliberately conceal suits.

### 5.7 External validity: the classic 48-card game

Every result above was obtained on our 54-card variant, whose ninth
half-suit is a synthetic assembly of four 8s and two jokers. A reasonable
objection is that the findings might be artifacts of that construction
rather than properties of Literature. We therefore repeated the key
measurements on the classic 48-card ruleset:

| measure | 54-card | 48-card |
|---|---|---|
| gain from the improved ask objective | **+1.51** [+1.17, +1.85] | **+1.37** [+1.01, +1.72] |
| cards per possession | 1.72 | 1.74 |
| ask success (early / mid / late thirds) | 60% / 67% / 64% | 59% / 67% / 66% |
| failed-ask share | 36.3% | 36.0% |
| seat advantage | +0.03 [-0.26, +0.33] | +0.08 [-0.21, +0.38] |
| median claim delay | 0 | 0 |

*(300 games and 400 duplicate deal-pairs per variant.)*

The rulesets are near-indistinguishable strategically. The only clear
difference is game length (107 asks per game versus 93), which follows
directly from one extra half-suit and one extra card per player. The
improvement to the ask objective, the phase structure of ask accuracy, the
absence of seat advantage, and the claim-timing behaviour all transfer.

This strengthens the earlier finding that the synthetic half-suit is not
treated differently *within* a game: adding it does not change the game
either.

---

## 6. Failed experiments

We record these deliberately, because the negative results were more
informative than the positive ones.

1. **PIMC search** lost to its own prior (0.146). Cause: world noise
   dominated the action gap.
2. **Information-Set MCTS** lost worse (0.062), because UCT allocates
   different worlds to different actions by construction.
3. **A value network trained on belief features** lost 34-6 when applied
   inside determinized search. Cause: train/inference distribution mismatch.
   Inside a sampled world every location is certain, so belief features
   (entropy, spread, expected share) take values never seen in training.
   Retraining on perfect-information features raised explained variance from
   43.7% to 58.7% and correlation from 0.669 to 0.771.
4. **Quiescence extension** (evaluating at the end of the current
   possession rather than immediately) was predicted to help, since turn
   retention is the strongest skill statistic. It made things worse (0.125
   versus 0.250). The perfect-information greedy continuation was too strong
   and too uniform: inside a determinized world nearly any successful ask
   drains the same cards, so candidates converge to similar leaves and the
   comparison loses discrimination.
5. **Naive backward induction** for exact solving did not terminate,
   because the state graph is cyclic.
6. **An expected-value claim model** predicted a threshold near 0.70 and was
   refuted by direct measurement.

---

## 7. Limitations

- Belief propagation is sound but not complete, and world sampling is not
  uniform over the consistent set. Reported probabilities are heuristic
  estimates.
- Exact solving is limited to roughly seven live cards in a single
  unresolved half-suit; the state space grows as 6^k.
- The perfect-information solutions used for the absolute benchmark are not
  the same object as optimal play under uncertainty. We therefore report the
  resolved and uncertain regimes separately and only claim optimality in the
  former.
- All strategy findings are measured under agents that do not deliberately
  deceive or conceal. If deceptive strategies emerge from future training,
  the half-suit and information-cost results should be re-measured.
- No result here demonstrates convergence to equilibrium. We have not
  computed exploitability, and we make no claim that the game is solved.

---

## 8. What we would do next

The diagnosis in Section 5.2 pointed at the ask objective, and Section 5.5
confirmed it pays: three terms the baseline ignored are each worth roughly
half a set per deal-pair, and belief precision has not saturated. The
immediate work is to find where those terms peak and whether they combine
rather than duplicate each other, since two individually good terms can
easily push toward the same asks.

Beyond that, in order of expected value:

- **Learn the ask objective rather than hand-weighting it.** The terms that
  worked were guessed. A model trained to predict the value of an ask from
  its features should dominate any hand-tuned combination, and unlike the
  value functions tried here it would be trained on the quantity actually
  being ranked.
- **Correct the sampler's non-uniformity.** Every probability the engine
  reports inherits this bias, including the ones the winning terms consume.
- **Widen exactly solvable subgames** for more absolute ground truth, which
  is the only validation that cannot flatter us.
- **Only then return to search**, teacher-student distillation and
  population play. Those stages remain blocked in a precise sense: a teacher
  no stronger than its student cannot teach, and search is not yet stronger
  than the policy it would be distilling from.

---

## Appendix: reproducing this work

The engine, agents, experiments and this paper are in one repository. Every
experiment writes an append-only manifest recording the code commit, both
random seed streams, the agent specifications and the result, and flags
whether it was run from a modified working tree.

```
py -m pytest tests -q            # 188 tests: rules, fuzz, leakage proofs,
                                 # belief soundness, statistics, exact solver,
                                 # coaching, ablation-equivalence guards
py scripts/run_large_study.py    # the duplicate-deal experiments
py scripts/diagnose_search.py    # the variance measurement of Section 5.2
py -m fish.cli solve             # exact ground truth on a sample endgame
py -m fish.cli serve             # simulator, analyser and live coach
```
