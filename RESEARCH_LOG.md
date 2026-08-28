# Fish Engine - Research Log

Living log of experiments, results, failures, and hypotheses.

Conventions: 54-card variant, baseline rules (SPEC.md), paired-deal
evaluation (every deal played twice with teams swapped, same cards and same
agent randomness). "Pair score" = wins + 0.5*ties over deal-pairs. "Set
diff" = per-pair set differential, range +/-18.

Evidence tiers used throughout: **DEMONSTRATED** (large controlled
experiment, CI reported), **PROMISING** (preliminary), **SPECULATIVE**
(hypothesis, no data).

---

## Current bottleneck analysis

Rewritten 2026-08-28. The previous table was from the era when search losing
to its own prior was the live problem; that is settled and the table had not
moved since. Ranked by measured size, not by how interesting the problem is.

| rank | bottleneck | evidence | status |
|---|---|---|---|
| 1 | We cannot locate our own teammates' cards | 0.1676 of our 0.1759 wrong declarations a game are allocation class -- our team held all six and we named the wrong split. Ownership errors are 0.0083 a game (`results/margin_decomposition.json`). Now priced as HEADROOM and not merely as errors: a cheating arm handed its teammates' cards gains **+3.4100** [+3.1625, +3.6575] sets/game, against **+1.3067** [+1.0070, +1.6063] for one handed the opponents' (`results/ceiling_split.json` -- bounds, not strength) | open, and the largest single lever left. See rank 2 for why it is hard |
| 2 | The channel freezes before the question is asked | once a team holds all six, `legal_asks` bars every opponent from asking there, so no ask will ever again NAME one of those cards -- though public hand counts still constrain it, and a teammate whose quota reaches zero is excluded from every unresolved card. The team jointly knows the answer and no member does: a distributed-knowledge problem, not an inference one | the only channel is a deliberately failed ask, priced at +0.1220 [+0.0291, +0.2149] and adding an error almost as often as it avoids one (`prereg/deadline_signalling.md`) |
| 3 | The ask objective charges a constant rate for a turn whose price is not constant | a turn is free below p_best = 0.50 and costs ~+0.45 above it; 53% of ask decisions are in the free regime and pay the full charge | 1,000 games give +0.2280 [+0.0076, +0.4484], which ships under the pre-registration as written and not under the runner's stricter reading. An 8,000-game replication decides it |
| 4 | Sampling is not uniform over consistent worlds | OR seeding and quota weighting skew draws | open since session 2: needs importance weighting or MCMC refinement. Every probability the engine reports inherits this |
| 5 | The transcript is read for constraints and not for choices | the posterior conditions on what an ask PROVED and never on the fact that this ask was chosen over the others. For teammates the policy is known exactly, which is the case where inversion is safe | open (task #53). The opponent-side version already failed once: the fitted exponent is -1.00 against our own +1.21 |

What is NOT a bottleneck, measured rather than assumed:

- **The deal.** Its share of a game's outcome variance is -1.3% [-4.0%, +1.5%]
  over 5,000 duplicated deals (`results/deal_luck.json`). There are no high
  cards in Fish and the cards move continuously, so a hand can be awkward but
  not weak.
- **Reading the table.** Our declaration accuracy is 96.5% and 95% of what is
  left is the teammate problem above, not the opponent one.
- **Game-level form.** Declaration accuracy has an overdispersion of 1.07 and
  an across-parity correlation of +0.018: there is no such thing as a game
  where anybody read the cards better. What looks like it in a loss is
  selection on coin flips.

---

## Session 1 - engine, beliefs, baseline ladder

### Key theoretical result driving the design
In Literature, *every card movement is public*: a successful ask names the
card, and a claim reveals all six locations. Therefore the current location
of every card is a deterministic function of the INITIAL DEAL plus the
public log, and all hidden-state inference reduces to constraints on the
initial deal:
- per-card candidate sets over initial owners,
- exact per-player deal counts (9 each),
- OR-constraints ("asker held at least one of that half-suit then").

This makes belief tracking **exact and sound** rather than approximate.
Verified by truth-in-support tests at every step for all six seats plus an
external spectator, and by independent replay-validation of sampled worlds.

**Honest limitation:** propagation is sound but NOT complete (no full
arc-consistency), and the sampler is not uniform over the consistent set.
Both are documented in `fish/beliefs.py` and remain open items.

### DEMONSTRATED - the baseline ladder separates cleanly
400 deal-pairs per cell (120 where probabilistic is involved):

| matchup | pair score (X) | 95% CI | set diff/pair |
|---|---|---|---|
| random vs heuristic | 0.000 | [0, .010] | -12.94 +/- 0.19 |
| random vs memory | 0.000 | [0, .010] | -16.38 +/- 0.11 |
| random vs probabilistic | 0.000 | [0, .031] | -16.59 +/- 0.19 |
| heuristic vs memory | 0.000 | [0, .010] | -11.86 +/- 0.20 |
| heuristic vs probabilistic | 0.000 | [0, .031] | -12.08 +/- 0.43 |
| memory vs probabilistic | 0.237 | [.170, .321] | -2.07 +/- 0.57 |

Logical bookkeeping alone is worth ~12 sets/pair over public-info
heuristics. Probabilistic inference adds a further 2.07 [1.50, 2.63].

### Ratings v1 RETRACTED (methodological failure worth recording)
An audit found `fit_ratings` never converged and had no handling for perfect
separation, so the published numbers were iteration-budget artifacts.
Rewritten as a regularized MAP Bradley-Terry fit (damped Newton,
full-covariance stderrs). Refit:

| agent | rating | note |
|---|---|---|
| probabilistic | 3156 +/- 599 | |
| memory | 2954 +/- 598 | |
| heuristic | 1586 +/- 454 | |
| random | 200 +/- 845 | bound only (winless) |

**LESSON:** when policies are separated by shutouts, pairwise ratings are
only BOUNDS. The maximum-likelihood gap is literally infinite and any finite
number is a prior artifact. The only precisely measured gap in this ladder is
memory -> probabilistic (~202 points). Ordering is trustworthy; magnitudes
below probabilistic are not. To get meaningful ratings across very unequal
policies we need intermediate rungs or explicit handicaps.

---

## Session 2 - the search failure, diagnosed and fixed

This is the most instructive result so far.

| search design | vs probabilistic prior (paired deals) |
|---|---|
| PIMC v1 (independent rollout batches) | **0.146** for search (24 pairs) |
| ISMCTS (UCT, per-iteration world resampling) | **0.062** for search (32 pairs, 1W/2T/29L) |
| PairedSearch (common random numbers + paired significance) | **0.562** [.410, .704], statistically NEUTRAL |
| ValueSearch with BELIEF-feature net | **0.150** for search (40 pairs, 6W/0T/34L) |

Both naive search designs were dramatically WORSE than the simple policy
they were built on. Rather than guess, `scripts/diagnose_search.py` measured:

- **D1: is the leaf eval informative?** corr(eval@depth200, true final
  differential) = **+0.73**. The evaluation function was fine.
- **D2: the actual culprit.** Standard deviation of ONE action's rollout
  value across sampled worlds = **0.698**. Mean gap between best and worst
  candidate action = **0.293**. **Noise/signal ~ 2.4.** Any search that
  evaluates different actions on *different* worlds (UCT's uneven
  allocation, independent PIMC batches) produces a ranking dominated by
  world luck.

**FIX 1 (worked):** common random numbers - evaluate every candidate on the
SAME worlds with the SAME rollout seeds - plus a paired significance test so
search only overrides the prior on evidence. The deficit vanished
(0.062 -> 0.562).

**FIX 2 (failed, then diagnosed):** a value net trained on BELIEF features
lost 34-6 when used inside determinized search. Cause: train/inference
distribution mismatch. Inside a sampled world every card location is
certain, so belief features (entropy, spread, expected share) take values
the net never saw during training.

**FIX 3:** train a PERFECT-INFORMATION evaluator, whose input distribution
matches its use (scoring fully-determined worlds sampled from the agent's
own beliefs). Results:

| evaluator | variance explained | corr with outcome |
|---|---|---|
| belief-feature net (mismatched) | 43.7% | 0.669 |
| perfect-information net | **58.7%** | **0.771** |

(146k samples from 2,500 self-play games.)

---

## Session 2 - exact ground truth

Built `fish/exact.py`, the project's only source of ABSOLUTE rather than
relative truth.

### DEMONSTRATED - the Fish state graph is CYCLIC
Discovered by the solver's own tests: two opponents can trade a card back
and forth and return to an identical position. Fish is a **loopy game**, so
naive backward induction never terminates. This is a genuine structural
property, not an implementation artifact.

Solution: solve in layers. Claims strictly reduce the number of unresolved
half-suits, so they always move to a simpler layer; asks and passes cycle
within a layer and are solved by **value iteration** to a fixpoint. Every
non-terminal in-layer state starts at 0, encoding the honest semantics of an
unbroken cycle: if play never progresses, nobody scores again. A side that
can only lose by claiming will correctly prefer to stall, which is exactly
the stalemate behavior real Fish exhibits.

### Tractability, measured
A layer with k live cards has up to 6^k placements. One half-suit (6 cards)
solves in ~1,800 states. Two half-suits (12 cards) is hopeless by
enumeration, so `solve_position` refuses loudly above 9 live cards rather
than hanging.

Example verified ground truth: P0 holds 2C 3C 4C, P1 holds 5C, P3 holds
6C 7C, P0 to move. Exact value +1, with THREE optimal actions (any
successful steal). This is the kind of position where "the engine agrees
with the optimum" is a real, checkable claim.

---

## Session 3 - absolute strength, and where the remaining gap actually is

### DEMONSTRATED - agreement with EXACT optimal play

The first metric in this project that is absolute rather than relative.
188 solvable endgame positions (one live half-suit, <= 8 live cards) drawn
from real games; each solved exactly; each agent asked for its action from
its legal observation only.

Two regimes are reported separately, because they mean different things:
- **resolved**: every remaining card's location is already publicly
  determined, so the perfect-information optimum IS the optimum and a strong
  agent should reach 100%.
- **uncertain**: genuine hidden information remains, so agreement is a
  comparative signal, not a target.

327 positions, 130 of them information-resolved:

| agent | resolved | uncertain | mean value loss |
|---|---|---|---|
| random | 48.5% (63/130) | 28.9% (57/197) | 0.465 sets |
| heuristic | 66.2% (86/130) | 47.7% (94/197) | 0.275 sets |
| **memory** | **100.0% (130/130)** | 69.0% (136/197) | 0.138 sets |
| **probabilistic** | **100.0% (130/130)** | **75.6% (149/197)** | **0.104 sets** |
| ev_claim | 100.0% (130/130) | 75.6% (149/197) | 0.104 sets |
| paired_search | 100.0% (130/130) | 73.6% (145/197) | 0.122 sets |
| **value_search** | **97.7% (127/130)** | 68.0% (134/197) | 0.177 sets |

**This is the strongest correctness result the project has.** When
information is fully determined, both belief-tracking agents play *exactly
optimally in every single position tested*. Not "beats the previous
version": provably right.

**And it localizes the search defect precisely.** `value_search` is the
only agent that fails information-resolved positions (127/130). Those are
positions with NO hidden information, where the right move is unambiguous
and its own prior already had it. The learned evaluation is overriding a
correct choice with a wrong estimate. That is direct, absolute evidence of a
defect rather than a preference, and it is exactly what this benchmark was
built to expose. Any fix must at minimum restore 130/130 before the agent
can be taken seriously.

`paired_search` shows the same effect in weaker form: identical on resolved
positions but slightly *worse* than its prior under uncertainty (73.6% vs
75.6%, value loss 0.122 vs 0.104), consistent with its neutral-to-slightly-
negative match results. Search is still subtracting, not adding.

`ev_claim` scores identically to `probabilistic` here, which independently
corroborates the bimodality finding: in endgames the claim confidence is
never in the band where the threshold rule differs.

### The key strategic implication
Because the strong agents are already optimal in solvable endgames, **the
remaining strength gap is NOT in the endgame**. It lives in midgame
positions that are too large to solve exactly. Any future search work should
be aimed there, and endgame-focused search has little headroom to win back.

This also explains the value-search failures below: in the regime where
search was being measured, there was very little left to gain, so added
estimation noise could only hurt.

### DEMONSTRATED - claim threshold sweep, and a falsified prediction

150 paired deals per cell, one variable changed:

| vs baseline 0.97 | pair score for 0.97 | set diff per pair | verdict |
|---|---|---|---|
| 0.60 | 0.590 [0.510, 0.666] | +0.71 [+0.34, +1.08] | 0.97 better |
| 0.70 | 0.570 [0.490, 0.647] | +0.45 [+0.18, +0.72] | 0.97 better (differential) |
| 0.85 | 0.497 [0.418, 0.576] | -0.01 [-0.09, +0.06] | indistinguishable |
| 0.999 | 0.500 [0.421, 0.579] | +0.00 [+0.00, +0.00] | identical play |

**The EV claim model's prediction was FALSIFIED.** It derived an optimal
threshold near 0.70; the experiment shows 0.70 is measurably *worse* than
0.97 (+0.45 sets/pair). The model's error is identifiable: `wait_ev` used
`p_improve = 0.55`, treating the resolution of an unknown teammate split as
roughly a coin flip. In real play continued asking localizes teammate
holdings far more reliably, so waiting is worth much more than modeled.
Correcting `p_improve` from data is a concrete follow-up.

**Structural finding:** 0.97 vs 0.999 produced a differential of *exactly*
0.00 across 150 pairs, i.e. the two never once diverged. Claim confidence is
**bimodal**: a strong agent either knows the split or does not, and almost
never sits in the 0.97-0.999 band. This means threshold tuning in that range
is not merely unhelpful, it is a no-op, and effort should go to *increasing
how often the split becomes known* rather than to when to pull the trigger.

Note on statistics: the pair-score Wilson CI and the differential t-CI
disagreed for the 0.70 cell (score CI straddles 0.5, differential CI
excludes 0). The differential is the more sensitive statistic because it
uses magnitude rather than only sign; both are reported to avoid
cherry-picking.

### DEMONSTRATED - the search defect was localized, then fixed

The three failures were dissected (`scripts/diagnose_value_search.py`).
**All 3/3 were search overriding a CORRECT prior**, and each time it chose an
action worth -1.00 when +1.00 was available. Example: P4 to move, P1 holding
only 8D, P5 holding 8C 8H RJ BJ. Every steal wins the set; value search
asked P1 for 8C, which provably fails, handing the turn to the opponents who
then held everything.

Root cause: in a fully-determined position every sampled world is identical,
so the paired difference has zero variance and the significance test degrades
to "trust the network". The network was extrapolating badly on lopsided
endgames that rarely appear in self-play training data.

FIX (`fish/agents/tablebase.py`): when an agent's own beliefs pin every live
card, the position contains no hidden information, so solve it exactly
instead of estimating. This is the Fish analogue of chess tablebases, and it
is leak-free by construction: the reconstruction uses only public events plus
the agent's own hand, and refuses unless every live card is pinned AND the
reconstruction reproduces every public fact.

Result: **every agent now scores 100.0% on information-resolved positions**,
value search included.

### DEMONSTRATED - search's overrides are net harmful, and the cause is the objective

With the tablebase in place, a threshold sweep on the exact benchmark
isolates what search actually contributes under genuine uncertainty:

| configuration | agreement (uncertain) | mean value loss |
|---|---|---|
| **prior, no search** | **76.0%** | **0.104** |
| paired search t=1.0 | 73.5% | 0.116 |
| paired search t=1.5 | 74.0% | 0.122 |
| paired search t=2.5 | 75.5% | 0.110 |
| paired search t=4.0 | 75.5% | 0.110 |
| paired search t=8.0 | 75.5% | 0.110 |
| paired search 24 worlds, t=2.5 | 75.5% | 0.110 |
| value search t=1.0 | 70.5% | 0.147 |
| value search t=2.5 | 72.0% | 0.141 |

Agreement rises monotonically as the override bar is raised, converging on
the prior **from below**. That is the exact signature predicted if search's
overrides were false positives from multiple comparisons. At t >= 2.5 search
essentially stops overriding and simply becomes the prior.

But the stronger reading is this: **no setting of the search makes it better
than not searching.** Doubling the world count changes nothing. So the
problem is not the search machinery, the sample size, or the statistics.
**The problem is the evaluation target.** Neither depth-limited rollouts nor
the learned value function ranks candidate asks better than the prior's
simple P(success). Until the thing being maximized is improved, more search
cannot help, and this is why the roadmap now points at the ask objective
rather than at deeper search.

### FAILED - quiescence extension for value search
Hypothesis: evaluating immediately after our own action cannot see
turn-retention value (the strongest measured skill statistic), so extend
until the turn leaves our team, then evaluate.

Result: **rejected**. Pair score for value search fell to 0.125 (34W/2T/4L
against it over 40 paired deals), worse than the 0.25 without quiescence.
Diagnosis: the perfect-information greedy continuation is too strong and too
uniform. Inside a determinized world almost any successful ask drains the
same cards, so all candidates converge to similar leaves and the comparison
loses discrimination. Kept behind `quiesce=False` as a documented negative
result.

### Standing score for search variants vs the probabilistic prior
| variant | pair score for search | reading |
|---|---|---|
| PIMC v1 | 0.146 | clearly worse |
| ISMCTS | 0.062 | clearly worse |
| value search (belief features) | 0.150 | clearly worse |
| value search (PI features) | 0.250 | worse |
| value search (PI + quiescence) | 0.125 | worse |
| **paired search (CRN)** | **0.387-0.438**, CI straddles 0.5 | **neutral** |

Common random numbers remain the only intervention that has removed the
search deficit. Nothing has yet produced a search that is significantly
BETTER than the belief prior. That is the honest current state.

---

## Performance

| component | before | after | how |
|---|---|---|---|
| belief world sampling | 736 us/world | **178 us/world (4.1x)** | cache the constraint scaffolding across draws; satisfy disjoint OR-constraints during construction instead of repairing afterwards |
| belief incremental update | 726 us | 352 us | fewer redundant propagation passes |

Profiling drove both: sampling was 30x the per-decision cost of belief
updates, and within sampling, OR repair was 66% of the time.

Simulator throughput (8 cores): random ~30 games/s/core; heuristic ~8/s;
memory ~11/s; probabilistic ~4/s. Python remains adequate through the
current phase; a compiled core is NOT yet justified because inference, not
rule application, dominates.

---

## Failed experiments (kept deliberately)

1. **PIMC v1** - lost 0.146 to its own prior. Cause: world-noise dominated
   action-gap. Superseded by paired search.
2. **ISMCTS** - lost 0.062. Same root cause, worse because UCT allocates
   different worlds to different actions by construction.
3. **Belief-feature value net inside determinized search** - lost 0.150.
   Cause: train/inference distribution mismatch. Superseded by the
   perfect-information evaluator.
4. **Naive backward induction for exact solving** - infinite recursion,
   because the state graph is cyclic. Superseded by layered value iteration.

---

## Bugs found by the test suite and audits (all fixed)

- Agent RNG seeds were a deterministic function of the deal seed, a genuine
  channel for reconstructing hidden hands. Seeds now come from an
  independent stream and are recorded rather than coupled.
- `fit_ratings` never converged and mishandled perfect separation.
- A gold-standard belief assertion ended in `or True` and could never fail.
- Timed-out games were silently counted as completed paired observations.
- Differential CI used population variance with a z critical value.
- `Pass(-1)` was accepted (negative indexing wrapped to seat 5) and
  corrupted `state.turn`; `Pass(7)` raised IndexError instead of
  IllegalAction.
- A factually exact claim submitted as a *list* rather than a tuple compared
  unequal and was scored as a wrong distribution, nulling a correct claim.
- The stall detector looked for runs of failed asks, missing the common
  livelock where cards shuttle between two opponents with successful asks.
  Now tracks resolution progress.
- The OR-seeded sampler could break a seeded constraint while repairing an
  overlapping one (caught by replay-validation).

## Infrastructure incident

The working tree was deleted by an external process mid-session (git
directory included; nothing in the recycle bin, no Defender entry). The
project was rebuilt from context and re-verified: 140+ tests pass. Datasets
and the trained checkpoint were regenerated. Commits are now made more
frequently as recovery points.

---

## Next experiments (highest expected information gain first)

1. **Decision-theoretic claim policy.** Replace the fixed confidence
   threshold with an expected-value comparison (claim now vs wait), using
   the value net for the continuation. The threshold is currently the least
   principled part of a strong agent.
2. **Ask objective beyond P(success).** Learn the value of an ask including
   turn retention, information gained, information leaked, and which
   opponent receives the turn on failure.
3. **Exact-solver agreement benchmark.** Measure how often each agent picks
   an exactly-optimal action in solvable endgames. This is the first
   absolute (not relative) strength metric.
4. **Sampler uniformity.** Quantify the bias from OR seeding; test
   importance weighting or MCMC refinement.
5. **Teacher/student loop.** Use paired search as a teacher to label
   difficult information states, train a policy head, put it back in search.
6. **Exploiter search.** Train a best response against the champion; feed
   its wins back into training.

---

## Session 2026-08-28 (second half) - what the corpus already knew

Four results, none of which cost a game to obtain, plus one ship and one
unresolved verdict.

### The deal decides nothing (DEMONSTRATED)

The 10,000-game head-to-head played every deal from both seat parities, which
identifies the deal's contribution: under that design the deal's share of a
game's variance is identically minus the correlation between the two parities'
margins. Measured, +0.0127 [-0.0150, +0.0404], so the share is -1.3% [-4.0%,
+1.5%]. `scripts4/deal_luck.py`.

Fish has no high cards -- every half-suit is worth one set -- so a hand can be
awkwardly distributed but not weak, and continuous card movement dissolves the
arrangement by the middlegame. The deal does leave a *symmetric* trace: our
ask hit rate correlates +0.087 [+0.060, +0.115] across the two parities, so
some deals are clumped enough that asks land more often for everybody. A deal
can be textured without being unfair.

I got the estimator wrong first and it is worth recording. The natural-looking
var(diff)/(var(sum)+var(diff)) is 0.5 whenever the correlation is zero, so it
reported "49.4% of the outcome is the deal" from data saying zero, and would
have reported about the same from any data. `tests4/test_deal_luck.py` now
builds synthetic corpora with a chosen deal effect and fails if the estimator
cannot tell zero from dominant.

### Pairing is worth 1.1x to 414x, and firing rate decides which (DEMONSTRATED)

Swapping seats on a deal buys 0.99x, because the antisymmetric advantage it
removes is not there. Holding the deal, seats and opponents fixed and moving
one knob is a different pairing and is the one every ship decision rests on.
Priced over every multi-arm journal (`scripts4/pairing_value.py`):

| knob | identical games | rho | efficiency |
|---|---|---|---|
| gamma (every decision) | 19.9% | 0.089 | 1.1x |
| signalling gate | 79.8% | 0.853 | 6.8x |
| doomed-ask gate | 88.1% | 0.899 | 9.9x |
| forced search vs v0.7 | 99.1% | 0.998 | 414x |

**The sample size a screen needs is set by how often its knob changes a
decision, not by how large the effect is.** This project has sized runs by
effect size alone. The forced-search secondary resolved +0.0180 to +-0.012 on
1,000 games; G1, same design, 1,600 games, could not resolve finer than +-0.19.

### A loss is not a day when they read better (DEMONSTRATED)

Of what separates the 1,959 games we lose, the rows that top the ranking are
terms of the score identity and are the scoreboard restated. Of the rest, the
largest is our ask hit rate, 0.535 against 0.460. But a game carries fifty
asks, so the binomial sd of that rate is 0.071 and the whole gap is 0.074.

Overdispersion against fifty coin flips at the pooled rate: our hit rate 1.72,
theirs 1.71, our declaration accuracy 1.07, theirs 1.03. **Declaration
accuracy has no game-level structure on either side.** "Their accuracy rises
from 0.754 to 0.925 in games we lose" is selection on coin flips. The camping
theory was refuted earlier this session; this says there was never a channel
for it to work through.

The hit rate is the one rate with structure, and it splits 58.3% binomial /
8.7% deal texture / **33.0% the position our own play built**. That last third
is the only part a policy can move.

### 95% of our wrong declarations are the teammate problem (DEMONSTRATED)

`results/margin_decomposition.json`: our 0.1759 wrong declarations a game are
0.1676 allocation and 0.0083 ownership. We essentially never claim a half-suit
an opponent still holds. What we cannot do is say which teammate has what --
and once our team holds all six, no opponent may legally ask there, so the
split is frozen to direct evidence: no ask will name those cards again. It is
NOT frozen to counting -- public hand counts keep tightening as teammates spend
their other cards, and `fish/beliefs.py::_propagate` uses them.

That makes it mostly a distributed-knowledge problem rather than an inference
one: every card is held by someone who knows they hold it, no one member knows
the split, and the game supplies no channel to say so. "Mostly", because the
counting channel is a real second route and I spent most of a session claiming
it did not exist.
The one free lever looked like *who* declares -- any teammate may, on their own
turn, and 30.4% of wholly-held declarations are made by someone a teammate
could have out-informed. **It is refuted, and it inverted.** Over 16,156
wholly-held declarations (`scripts4/declarer_holding.py`) the error rate rises
with the declarer's own holding: 0.017 at one card, 0.048 at two, 0.063 at
four, 0.068 at five, and trivially 0.000 at six. Selection, not skill: holding
one card you only declare when the other five are publicly pinned; holding five
leaves exactly one card unaccounted for, and if it never moved it is a coin
flip between two teammates.

What survives is a sharper statement of the problem. **The residual risk on a
wholly-held half-suit is not proportional to how much you are missing -- it is
about whether what you are missing has ever moved in public.** Five in hand and
one dealt-and-never-asked-for is worse than one in hand and five that have all
been seen, and it does not feel that way.


### The counting channel is not a footnote: it is half of every declaration

Registered as a caveat, then measured. 1,800 self-play games, 16,156
declarations of half-suits the declaring team wholly held
(`scripts4/declarer_holding.py` -> `results/declarer_holding_self.json`).

**The mediator holds.** Error rate by how many of the six have never been
publicly LOCATED -- never taken by a successful ask:

| never located | n | error rate |
|---|---|---|
| 1 | 4,980 | 0.000 |
| 2 | 4,234 | 0.006 |
| 3 | 2,990 | 0.032 |
| 4 | 2,344 | 0.055 |
| 5 | 1,266 | **0.111** |
| 6 | 342 | 0.088 |

That spans 0.000 to 0.111 where the declarer's own holding spanned only 0.005
to 0.068, so it is the stronger predictor by a distance -- and held at fixed
`unmoved` the k-effect flattens. In the best-populated stratum (`unmoved` = 4,
n = 2,344) the error rate across k = 0..5 runs 0.050, 0.068, 0.057, 0.057,
0.042, 0.077: no trend at all. The monotone k-curve was selection on this
variable, exactly as the refutation predicted.

**And the k-curve reproduced to the digit** across a rerun that added
`trace=True` to the opposing seats -- 0.0048, 0.0174, 0.0484, 0.0421, 0.0629,
0.0678, 0.0000 -- which is what confirms tracing is inert rather than assuming
it. The path table is now complete too: the 8,078 declarations that landed in
"other" were the untraced opposing team, and they are gone.

**The counting channel, measured.** Cards the propagator pinned to a specific
player over and above the declarer's own hand and the public record:

| derived | n | share | error rate |
|---|---|---|---|
| 0 | 7,530 | 46.6% | 0.046 |
| 1 | 5,364 | 33.2% | 0.011 |
| 2 | 2,438 | 15.1% | 0.006 |
| 3+ | 824 | 5.1% | 0.000 |

**53.4% of wholly-held declarations carry at least one card the propagator
derived**, and the error rate falls by a factor of four from zero derived to
one. So the claim I made and retracted -- that once a team holds all six
nothing further can inform the split -- was not slightly overstated. Deriving
cards after the freeze is what makes a declaration safe, and it happens in the
majority of them.

**A calibration table that is NOT a calibration finding.** The run also
captured what `best_for_half_suit` priced each declared split at, and every
gap is positive: claimed 0.777 to 0.920 against observed 0.932 to 1.000, so
+0.08 to +0.155 at every k. That reads as systematic under-confidence and it
is very likely an artefact instead. `best_for_half_suit` has two tiers, and
above its enumeration cap it returns a PRODUCT of per-card marginals rather
than a joint -- the same defect `api/_engine.py::claim_check` documents and
re-prices around. The table is a statement about the cheap estimator, not
about the engine's confidence, and it is recorded here so that nobody
(including me) later quotes it as the latter. The gap does not trend with k,
so it gives no reason to think `forced_claim`'s argmax is distorted.

### Teammate knowledge is worth 2.6x opponent knowledge, and I predicted the reverse

`prereg/information_ceiling_split.md`, 600 games per arm. **Every figure here is
a bound obtained by cheating** -- not strength, never in a ladder, never beside
an honest margin.

| arm | ceiling over honest |
|---|---|
| teammates' cards known | **+3.4100** [+3.1625, +3.6575] |
| opponents' cards known | **+1.3067** [+1.0070, +1.6063] |
| everything known | +6.6067 [+6.4004, +6.8129] |

I registered the opposite prediction, and the reasoning behind it: knowing
opponents' cards makes every ask land, while knowing teammates' cards only
improves a declaration on a set already assembled -- so the error ledger
measures where our mistakes are rather than where our headroom is. That was
wrong. **The error ledger's 95/5 split does translate into an information-value
split**, and the rank-1 entry in the table above is ranked correctly.

And the sharpest form of it, which was a registered secondary I nearly failed
to report: the two arms are told **almost exactly the same number of cards** --
40.7 against 40.4 pinned by the cheat per game -- and one is worth 2.6 times
the other. That controls for the quantity of information and isolates its kind.
What limits this engine is not how much it knows but what its knowledge is
about.

Two things about the mechanism table are worth separating.

**The teammate arm's zero allocation errors are definitional, not evidence.** A
seat that knows every teammate's cards and its own reads the split off rather
than inferring it. Registering that as a mechanism check was a design mistake:
a check that cannot fail cannot confirm.

**The opponent arm's 2.4950 allocation errors a game are the informative cell**
-- sixteen times the honest baseline. Perfect opponent knowledge zeroes
ownership errors as expected and leaves the split exactly as hidden, while the
engine assembles far more sets. A hypothesis for the rate rising, consistent
with this session's mediator result and NOT measured here: an engine that never
misses an ask assembles half-suits fast, before the public record has located
anything, so it declares sets whose cards have never moved.

And they are **sub-additive**: T + O = +4.7167 against F = +6.6067. The
registration braced for the opposite -- that the elimination effect would make
the halves over-count -- so the two kinds of knowledge are complementary rather
than overlapping. Knowing where a card is not only helps if you can act on it.

### Shipped

`claim_forced_exhaustive=1` into `V06_DEPLOYED`, per
`prereg/forced_exhaustive.md`: self-play +0.0233 [+0.0133, +0.0334], and
against v0.7 the last declaration goes 28/87 to 37/87 correct, paired +0.0090
[+0.0031, +0.0149], guard 2 passing exactly.

### The tempo term does not replicate, and the bar ambiguity is why that matters

The 1,000-game run gave B_free **+0.2280 [+0.0076, +0.4484]** with the
predicted mechanism intact and a monotone dose response. The 8,000-game
replication against the current champion gives **-0.0163 [-0.0973, +0.0648]**,
and C_half comes in at **-0.0985 [-0.1746, -0.0224]** -- worse than shipped
beyond noise. The dose response inverted: A < C < B at 1,000 games, B > A > C
at 8,000.

**Withdrawal condition 3 fired**: the hit rate fell (0.5195 -> 0.5104) and the
margin did not rise. Withdrawn.

The mechanism appeared again and bought nothing: turns 57.700 -> 58.899, asks
52.346 -> 53.518, cards landed 27.196 -> 27.314. **More asks, more cards, no
more sets** -- and slightly worse declarations, the gate path's error rate
rising 0.262 -> 0.309. The error-value decomposition agrees arithmetically: B
avoids -0.0030 errors a game, adding them on net, with 868 games avoiding one
at +1.6198 against 972 adding one at -1.4979.

**What survives.** Section tempo's measurement is untouched -- a turn really is
worth about nothing below p_best = 0.50 and about +0.45 above it, and the
objective really does charge a constant rate on 53% of decisions. What is
refuted is that correcting the mis-specification pays. Twice now, here and with
the signalling gate, the tempo table has correctly identified something the
engine gets wrong and the fix has bought no sets. A term can be mis-specified
against a measured scale and still be doing useful work for a reason the scale
does not capture -- `turn_risk` is minus the target's hand size, so it also
pushes asks toward players holding fewer cards.

**And the reason the run existed.** The 1,000-game result SHIPPED under the
pre-registration as written (+0.2280 >= +0.15, lower bound +0.0076 > 0) and did
not ship under the stricter rule the runner had implemented. Rather than pick
between two artifacts both written before the run, I disambiguated in advance
-- ship only if both readings agree -- and bought 8,000 games. Had I taken the
document's literal reading, the champion would now carry a knob whose true
effect is -0.0163. The ambiguity was not a nuisance to argue away; resolving it
with data is the only thing that stopped a shipped false positive.

### The one basis term that points at the error we make, and why its screen said nothing

`concent` has been in the ask basis since v0.4 and weighted zero since. It was
screened once -- 0.15, 160 pairs, -0.037 [-0.653, +0.578] -- and filed with a
dozen other speculative terms. Both halves of that screen were unable to find
anything.

**The formula could not express the preference.** v1 was
`team_concentration[hs]`: one number per half-suit, identical for every
candidate ask in it, independent of the target and of who would end up holding
the card. A term with the same value on every ask in a half-suit can only tilt
the choice of half-suit. And its sign is backwards in the case it exists for --
when the concentration sits with a TEAMMATE, my taking a card breaks it up, and
v1 scored that ask highest precisely because the half-suit was concentrated.
Same defect `claim` carried at v1, same remedy: corrected in place to the
expected CHANGE the ask causes, `TERM_VERSIONS["concent"]` bumped to 2, so
`stale_terms()` flags every harvest fitted against the old column.

**And the weight was inert.** `scripts4/concent_scale.py` over 596 decisions
with a real choice and 30,065 candidate asks: the corrected feature has median
magnitude 0.0299 and median within-decision spread 0.0677. At 0.15 it changes
which ask is taken on **1.7% of decisions**; it takes about 1.0 to reach 8%.
A 160-pair run of a knob acting on one decision in sixty, reporting an interval
four times the ship bar in each direction, is a statement about the harness.

Why it is worth reinstating rather than deleting: 0.1676 of our 0.1759 wrong
declarations a game are allocation class. A half-suit held entirely in one hand
has no split to name, and this is the only term in the basis that points there.

Registered at `prereg/concentration_v2.md`, 4,000 games, arms at 0.60 (equal to
`w_turn`, the largest existing weight) and 1.50. The mechanism -- allocation
errors falling, and concentration at declaration time rising -- is a
**withdrawal condition** rather than a secondary: a margin that rises without
them means the term is being paid for something other than the reason it was
reinstated, and shipping it would put the wrong explanation in the paper.
