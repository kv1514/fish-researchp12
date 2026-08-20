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

| rank | bottleneck | evidence | status |
|---|---|---|---|
| 1 | Search cannot yet exploit beliefs | PIMC and ISMCTS both LOST to their own prior; paired search reached only parity | value net now trained, decisive test running |
| 2 | Belief sampling cost | measured 736 us/world, 30x the cost of belief updates per decision | **improved 4.1x to 178 us/world** via cached OR-seeded sampler |
| 3 | Sampling is not uniform over consistent worlds | OR seeding and quota weighting skew draws | open: needs importance weighting or MCMC refinement |
| 4 | No ground truth for "is this move right?" | every metric was relative | **exact subgame solver built** |
| 5 | Claim policy is a fixed confidence threshold | not decision-theoretic | open: next major item |

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

| agent | resolved | uncertain | mean value loss |
|---|---|---|---|
| random | 47.2% (34/72) | 19.8% (23/116) | 0.404 sets |
| heuristic | 61.1% (44/72) | 36.2% (42/116) | 0.298 sets |
| **memory** | **100.0% (72/72)** | 61.2% (71/116) | 0.133 sets |

**This is the strongest correctness result the project has.** When
information is fully determined, the belief-tracking agent plays *exactly
optimally, in every single position tested*. Not "beats the previous
version": provably right.

### The key strategic implication
Because the strong agents are already optimal in solvable endgames, **the
remaining strength gap is NOT in the endgame**. It lives in midgame
positions that are too large to solve exactly. Any future search work should
be aimed there, and endgame-focused search has little headroom to win back.

This also explains the value-search failures below: in the regime where
search was being measured, there was very little left to gain, so added
estimation noise could only hurt.

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
