# Fish Engine

A research engine for **Literature** (a.k.a. **Fish** / **Canadian Fish**),
working toward the strongest practical engine for six-player Literature and
toward understanding what near-optimal Fish actually looks like.

- Rules: [SPEC.md](SPEC.md) (Wikipedia baseline plus configurable house rules)
- Research log: [RESEARCH_LOG.md](RESEARCH_LOG.md)
- Strategy findings: [STRATEGY_BOOK.md](STRATEGY_BOOK.md)
- Research paper: [PAPER.md](PAPER.md)
- Roadmap: [ROADMAP.md](ROADMAP.md)

## Main variant

54 cards: a standard deck plus two distinct jokers. Nine 6-card half-suits;
the ninth is `8C 8D 8H 8S RJ BJ`, where **RJ is the Red Joker and BJ the
Black Joker**, individually askable (you can ask specifically for the red
one). Six players, two teams (seats 0/2/4 vs 1/3/5), nine cards each. The
classic 48-card (no-8s) variant is also supported.

## Quickstart

```bash
py -m fish.cli serve
```

Then open two pages:

- **http://127.0.0.1:8777** — the simulator. Watch engine-vs-engine games
  live, step through them, analyze any position, and run luck-controlled
  matchups between any two policies.
- **http://127.0.0.1:8777/coach** — the **live coach**. Playing a real game?
  Enter your seat and your dealt hand, then log each ask as it happens at
  the table. It tells you what to play, with success probabilities, claim
  confidence, which cards it can *prove* are where, and the deductions
  behind them. It also catches typos in a way you can act on ("You are
  holding 2C, so you could not have said no to P1").

```bash
py -m pytest tests -q
```

Other entry points:

```bash
py -m fish.cli replay 3 --engine memory
```

```bash
py -m fish.cli play --seat 0 --engine probabilistic
```

```bash
py -m fish.cli solve
```

```bash
py scripts/run_tournament.py baseline
```

## Architecture

```
fish/
  cards.py           card/half-suit encoding (bitmask hands, colored jokers)
  rules.py           RuleConfig (house rules as data, not code)
  engine.py          GameState: legality, application, invariants
  observation.py     the information boundary (policies see ONLY this)
  beliefs.py         exact belief tracking + consistent-world sampling
  exact.py           exact subgame solver: absolute ground truth
  features.py        belief-space and perfect-information feature sets
  benchmark_exact.py agreement-with-optimal benchmark
  analysis.py        offline strategy analytics
  runner.py          game loop connecting agents to the engine
  agents/            random, heuristic, memory, probabilistic,
                     search (PIMC), paired_search, value_search,
                     tuned (current champion), ev_claim
  learning/          self-play datasets and the value network
  eval/              paired-deal tournaments, Bradley-Terry ratings, league
  web/               dependency-free simulation platform (stdlib HTTP + JS)
  coach.py           live coaching from a player's legal view
  registry.py        append-only experiment manifests
  gamelog.py         byte-packed transcripts (<1KB/game)
  cli.py, play.py    analysis CLI, interactive play, replays
tests/               rules, fuzz, leakage proofs, belief soundness,
                     statistics, exact solver, coach  (193 tests)
scripts/             tournaments, ablations, profiling, search diagnostics
```

## What the engine learned

The current champion (`tuned-v1`) beats the previous best belief policy by
**+1.28 sets per duplicate deal-pair** (95% CI [1.03, 1.52], 800 pairs). It
gets there from two considerations the old policy ignored completely:

1. **Which opponent gets the turn when your ask fails.** Prefer the ask that,
   if it misses, hands the turn to the opponent holding fewer cards.
2. **Fight hardest for suits your team is already winning.**

Both are **tie-breakers**, not primary criteria: they help when weighted
lightly and actively hurt when weighted heavily enough to override a
materially better chance of getting the card.

Notably, no search was involved. Two search designs (PIMC and ISMCTS) each
lost decisively to the very policy they were built on, for a measured
reason: the spread of a position's value across possible hidden layouts is
about 2.4x the gap between the best and worst candidate move, so evaluating
different moves against different guessed layouts ranks luck. See
[PAPER.md](PAPER.md).

## Three things this engine gets right that are easy to get wrong

**Information integrity.** Agents never receive engine state, only an
`Observation` (own hand + public log + public derived state). Tests prove
observations are identical to reconstructions built from public data alone,
and that features derived from them are invariant under any consistent
permutation of hidden cards. Agent RNG seeds come from a stream independent
of the deal, so randomness cannot encode the hidden layout.

**Exact beliefs.** Every card movement in Literature is public, so hidden
state reduces exactly to constraints on the initial deal (candidate sets,
per-player deal counts, half-suit OR-constraints). The tracker is sound (the
true world is never excluded) and sampleable. It is deliberately documented
as *not* complete, and the sampler as *not* uniform.

**Absolute, not just relative, evaluation.** Small endgames are solved
exactly, giving a ground-truth answer to "was that the right move?" rather
than only "did it beat the previous version". Fish turns out to be a *loopy*
game (positions can repeat forever), so the solver uses layered value
iteration rather than backward induction.
