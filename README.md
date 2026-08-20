# Fish Research Engine

This repository is a correctness-first foundation for a strong six-player
Literature / Canadian Fish engine. It supports the standard 48-card game and the
main 54-card variant whose ninth half-suit is `8C 8D 8H 8S JK1 JK2`.

It is not presented as solved Fish. Version 0.1 supplies the audited simulator,
information boundary, belief/search baselines, controlled evaluation, CLI, data
and checkpoint infrastructure, and a small population self-play baseline needed
to begin the longer research program.

## What is implemented

- Compact bitmask simulator with deterministic deals and aggressive invariants.
- ASK and exact-distribution CLAIM actions with correct/null/opponent-held
  outcomes.
- Explicit successor-selection and forced-claim endgames.
- Configurable claim timing, immediate personal claims, post-claim control,
  owned-card bluffing, bad-claim awards, reveal behavior, and cardless claims.
- Immutable observation-only policy API and noninterference/leakage regression
  tests.
- Correlated feasible-world belief particles enforcing exact hand counts,
  successful transfers, failed-ask exclusions, own hand, and resolved sets.
- Random, basic heuristic, memory, probabilistic, and sampled-world search agents.
- Hierarchical/compact claim candidates instead of a distorted flat `9 * 3**6`
  action mask.
- Duplicate-deal team swaps, within-team seat rotation, Wilson and paired
  confidence intervals, round-robin ratings, and uncertainty tracking.
- CLI match, benchmark, evaluation, tournament, observed-state analysis, and
  evolutionary population self-play commands.
- Resumable, deterministic multiprocessing simulations with six configurable
  seats, duplicate team swaps, atomic shards, and 10M+ experiment planning.
- SQLite experiment summaries with opt-in compressed traces, plus append-only
  hashed checkpoint/champion registry.

The normative rule decisions and source conflicts are in [GAME_SPEC.md](GAME_SPEC.md).
The source rules are [Pagat](https://www.pagat.com/quartet/literature.html) and
[Wikipedia](https://en.wikipedia.org/wiki/Literature_%28card_game%29).

## Quick start

Python 3.11 or newer is required. The engine itself has no third-party runtime
dependency.

```powershell
cd outputs/fish_engine
py -3.13 -m pip install -e .
py -3.13 -m pytest -q
```

Run one game:

```powershell
fish play --team-a heuristic --team-b random --seed 7 --debug
```

Benchmark randomized games:

```powershell
fish benchmark --agent random --games 1000 --seed 400000
```

Use duplicate deals and team swaps:

```powershell
fish evaluate probabilistic heuristic --deals 100 --particles 64
fish tournament random heuristic memory probabilistic --deals 50
```

Analyze a legal information state:

```powershell
fish analyze examples/state.json --agent search --particles 256 --determinizations 256
```

The analyzer deliberately reports an **uncalibrated sampled search value**, not a
fabricated win probability. Calibrated team-win estimates require a trained value
model and out-of-sample calibration.

Run the pre-neural population self-play baseline:

```powershell
fish selfplay --population 6 --generations 3 --deals 20 --output runs/selfplay-v1
```

This evolves a small linear asking policy against a fixed heuristic and a league
of historical champions using duplicate deals. It validates the population and
checkpoint workflow; it is not a substitute for future ISMCTS/MCCFR/neural
self-play.

Run a resumable ten-million-game experiment:

```powershell
fish simulate --games 10000000 --policy random --workers 4 `
  --shard-size 10000 --output runs/random-10m --dry-run
# Remove --dry-run to start; add --resume after an interruption.
```

Configure all six engine seats independently:

```powershell
fish simulate --games 10000 --paired `
  --lineup search probabilistic search probabilistic search probabilistic `
  --workers 4 --output runs/search-league-v1
```

See [SCALE.md](SCALE.md) for throughput limits and recovery semantics, and
[HUMAN_STRATEGY_GUIDE.md](HUMAN_STRATEGY_GUIDE.md) for the findings translated
into practical play advice.

## Observed-state JSON

`examples/state.json` is a template. Required fields are the ruleset, observing
player, own hand, and all six public card counts. Resolutions and scores must
conserve cards. Optional public history entries have `type` equal to `ask`,
`claim`, `successor`, or `forced_claims`. The parser creates legal actions from
this observation only and never asks for an initial deal, seed, or hidden owner
map.

Card names use `TC`, `JH`, `AS`, `JK1`, and `JK2`. Half-suits may be named (for
example `Low Clubs`) or indexed from zero.

## Project map

- `fish/core.py`: rules, state transitions, observations, invariants.
- `fish/belief.py`: constraints and coherent ownership particles.
- `fish/agents.py`: baseline through sampled-world search policies.
- `fish/evaluation.py`: duplicate evaluation, confidence intervals, ratings.
- `fish/analysis.py`: observation JSON and ranked move analysis.
- `fish/selfplay.py`: historical-population evolutionary baseline.
- `fish/scale.py`: 10M+ sharding, multiprocessing, resume, and aggregation.
- `fish/storage.py`, `fish/league.py`: efficient records and checkpoints.
- `tests/`: rules, fuzzing, leakage, belief, evaluation, CLI, and infrastructure.
- `RESEARCH.md`, `STRATEGY.md`: evidence log and evidence-gated strategy book.

## Current limitations

- The sampled search models retained-turn ask chains, not full information-set
  tree search with opponent/team responses.
- Exact belief particles are rebuilt by randomized backtracking after new public
  information. They are coherent but currently dominate probabilistic-policy
  runtime and have heavy-tailed late-game cost.
- No neural policy/value model, CFR learner, GPU batcher, replay viewer, or web
  dashboard is included yet.
- Non-random baselines make a documented speculative claim after 256 public
  moves without a resolved set to prevent cyclic benchmark games. This threshold
  must be controlled in serious ablations.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [RESEARCH.md](RESEARCH.md) for the next
research stages.
