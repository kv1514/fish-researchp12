# Fish Engine

A research engine for **Literature** (a.k.a. **Fish** / **Canadian Fish**),
working toward the strongest practical engine for six-player Literature and
toward understanding what near-optimal Fish actually looks like.

- Rules: [SPEC.md](SPEC.md) (Wikipedia baseline plus configurable house rules)
- Research log: [RESEARCH_LOG.md](RESEARCH_LOG.md)
- Strategy findings: [STRATEGY_BOOK.md](STRATEGY_BOOK.md)

## Main variant

54 cards: a standard deck plus two distinct jokers. Nine 6-card half-suits;
the ninth is `8C 8D 8H 8S RJ BJ`, where **RJ is the Red Joker and BJ the
Black Joker**, individually askable (you can ask specifically for the red
one). Six players, two teams (seats 0/2/4 vs 1/3/5), nine cards each. The
classic 48-card (no-8s) variant is also supported.

## Quickstart

```bash
py -m pytest tests -q
```

```bash
py -m fish.cli serve
```
Then open http://127.0.0.1:8777 to watch engine-vs-engine games live, step
or play through them, run the position analyzer, and run luck-controlled
matchups between any two policies.

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
                     search (PIMC), paired_search, value_search
  learning/          self-play datasets and the value network
  eval/              paired-deal tournaments, Bradley-Terry ratings, league
  web/               dependency-free simulation platform (stdlib HTTP + JS)
  cli.py, play.py    analysis CLI, interactive play, replays
tests/               rules, fuzz, leakage proofs, belief soundness,
                     statistics, exact solver  (140+ tests)
scripts/             tournaments, ablations, profiling, search diagnostics
```

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
