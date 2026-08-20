# Research Log

This log separates measurements from hypotheses. All reported experiments must
include ruleset, seed, policy versions, deal-pairing method, sample size, and an
uncertainty estimate.

## 2026-08-20 — Reference foundation

### Setup

- Host: Intel Core i7-1195G7, 4 physical / 8 logical cores, 16 GB RAM, Intel Iris
  Xe integrated graphics.
- Main ruleset: 54 cards, nine six-card half-suits, six players, alternating
  teams, nine initial cards each.
- Secondary ruleset: standard 48-card game, eight six-card half-suits.
- Implementation decision: build an inspectable Python reference engine first;
  consider a compiled core only after profiling verified workloads.

### Work attempted

- Formalized normal asks, distributed claims, three claim outcomes, endgame
  handling, and configurable house rules.
- Built an observation boundary intended to prevent policy access to hidden
  hands.
- Added deterministic agents, belief reconstruction, sampled search, duplicate
  evaluation, randomized invariant tests, and command-line workflows.

### Results

- Automated suite: 60 tests passed, including transition legality, all three
  claim outcomes, endgame administrative phases, information noninterference,
  coherent beliefs, duplicate evaluation, CLI parsing, storage, and self-play.
- Random invariant campaign: seeds across both 48/54 profiles, 1,000 completed
  games, 50,119 debug-validated actions, zero invariant failures. The core-only
  campaign measured about 77 games/s and 3,861 decisions/s.
- End-to-end 54-card RandomAgent benchmark: seed range starting 400000, 100
  games, 43.98 games/s, 6,446 decisions/s, mean 146.56 plies, zero truncations.
- Duplicate evaluation, BasicHeuristic vs Random: seed 500000, 100 deal pairs /
  200 games, heuristic point rate 100%, Wilson 95% CI [98.12%, 100%], paired
  half-suit margin +6.13, 95% CI [+5.98, +6.28]. This demonstrates that the
  evaluation detects a deliberately large baseline strength gap.
- Preliminary duplicate evaluation, Probabilistic(16 particles) vs Heuristic:
  seed 700000, 30 deal pairs / 60 games, probabilistic point rate 86.67%, Wilson
  95% CI [75.83%, 93.09%], paired half-suit margin +2.97, 95% CI [+2.43,
  +3.50]. The sample is modest and the policies differ in more than one feature;
  treat this as a signal motivating a larger belief ablation, not a settled
  strategy conclusion.
- Machine-readable results: `results/baseline_20260820.json`.

### Profile

- A profiled 16-particle probabilistic game spent roughly 85% of runtime in
  randomized-backtracking ownership sampling; state transition was well under
  1%. Candidate generation and action scoring were rebuilding the identical
  belief twice per decision.
- Observation-signature caching now reuses that belief. On seed 600010, the
  unprofiled probabilistic-vs-heuristic run completed at about 358 decisions/s;
  the post-fix profile still places most time in new-information backtracking.
- Conclusion: optimize incremental particle filtering/proposals before moving
  the Python rule core to Rust/C++. The measured bottleneck is belief inference,
  not card transfer.

### Failures and limitations

- No deep-learning result is claimed. A neural policy trained before simulator
  and information-boundary validation would produce uninterpretable evidence.
- Marginal card probabilities do not fully represent ownership correlations;
  sampled consistent worlds are the initial remedy, not a complete solution.
- The reference search is a baseline for measurement, not full ISMCTS or CFR.
- Non-random baselines can enter legal ask cycles. A public, reproducible
  stalemate policy now makes one speculative claim after 256 moves without a
  resolved set. This is a policy decision and must be ablated; it is not a hidden
  environment adjudication.
- Exact belief sampling has heavy-tailed late-game latency. Duplicate evaluation
  is statistically efficient but still slow at high particle counts.
- A five-deal Search-vs-Probabilistic smoke tournament at 12 particles / 8
  determinizations exceeded 150 seconds and was cancelled without a result.
  Root and rollout action pruning (12/4 defaults) was added afterward; full
  shared-tree ISMCTS and batched rollouts remain required before a large search
  tournament.
- A post-pruning single-game smoke (seed 800001, 12 particles, 8
  determinizations) completed 258 plies in 35.43 seconds, or 7.28 decisions/s.
  This is suitable for analysis demonstrations, not million-game self-play.

### Next experiments

1. Differential-test a future optimized core against reference transition
   traces.
2. Measure heuristic, memory, probabilistic, and sampled-search policies using
   duplicate deals and team/seat swaps.
3. Ablate public-history memory and belief constraints separately.
4. Compare acquisition-probability asks with information-gain-weighted asks.
5. Implement information-set MCTS with a shared public tree and belief-consistent
   re-determinization.
6. Add a population/checkpoint registry before any neural self-play.

### Self-play foundation

Implemented a runnable pre-neural evolutionary population baseline. Each
generation keeps the incumbent, mutates a population of linear asking policies,
evaluates them on duplicate deals against a fixed heuristic and recent historical
champions, and writes immutable generation checkpoints. This validates league
sampling and reproducibility plumbing. No strength result is claimed from the
tiny test run; scalable ISMCTS/MCCFR/neural self-play remains future work.

### Large-scale simulation platform

- Added deterministic game-index-to-seed mapping and six-seat lineups.
- Added paired deal replay, within-team rotation, and team swapping.
- Added multi-process sharding, atomic aggregate checkpoints, strict experiment
  fingerprints, resumability, and zero verbose per-game logs.
- Verified a 10,000,000-game dry plan: 1,000 shards and about 1.03 MB of
  aggregate metadata.
- Verified a four-worker 400-game execution and zero-replay resume with the
  worker count changed to two. The run measured 24.37 games/s while the host was
  already at 100% CPU from unrelated eight-process work, so it is recorded as a
  contention test rather than a clean scaling benchmark.
