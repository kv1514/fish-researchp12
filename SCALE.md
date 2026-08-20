# Large-Scale Simulation Platform

The `fish simulate` command is the batch platform for experiments ranging from a
few games to 10,000,000 or more. It runs six independently configurable policy
seats, partitions work into deterministic shards, uses multiple processes, and
can resume after interruption without replaying completed shards.

## Ten-million-game fast-policy run

Plan the experiment without writing or simulating anything:

```powershell
fish simulate `
  --games 10000000 `
  --policy random `
  --rules 54 `
  --workers 4 `
  --shard-size 10000 `
  --seed 20260820 `
  --output runs/random-10m `
  --dry-run
```

Remove `--dry-run` to start. If interrupted, issue the identical command with
`--resume`. Worker count may change when resuming; all strategy, seed, rules, and
shard parameters must still match the manifest.

The plan creates 1,000 aggregate shard checkpoints and approximately 1 MB of
metadata. It does not create ten million JSON game logs.

## Six-engine “Stockfish league” lineup

Every seat can run a different current engine:

```powershell
fish simulate `
  --games 10000 `
  --lineup search probabilistic search probabilistic search probabilistic `
  --paired `
  --particles 32 `
  --determinizations 8 `
  --workers 4 `
  --shard-size 100 `
  --seed 41000000 `
  --output runs/search-league-v1
```

Team A occupies seats 0, 2, and 4; Team B occupies 1, 3, and 5. In paired mode,
adjacent games share a deal, rotate policies within each team, and swap the two
teams. `--games` therefore must be even.

## Important performance distinction

The platform accepts 10M+ games, but policy strength determines whether such a
run is practical:

- Random and basic heuristic games are fast enough for large rule, fairness, and
  coarse-strategy sweeps.
- Correlated probabilistic beliefs are hundreds of times more expensive than a
  random decision in difficult late-game states.
- The current sampled-search policy is an analysis baseline, not a million-game
  rollout engine. A measured small search game ran at about 7 decisions/s.

Calling six instances `search` does not magically make them Stockfish-strength.
The path to a genuine six-engine Stockfish league is:

1. use large fast-policy runs to validate rules, data, scheduling, and feature
   extraction;
2. use expensive search as a teacher on a much smaller position sample;
3. train a fast policy/value student with batched inference;
4. use the fast student for millions of population games;
5. periodically evaluate champions with deeper search and duplicate deals.

## Reproducibility and crash recovery

Each experiment directory contains:

- `manifest.json`: immutable strategy/rules/seed identity and SHA-256
  fingerprint;
- `shards/shard-NNNNNNNN.json`: atomically written aggregate results for one
  contiguous game range;
- `summary.json`: aggregate scores, null sets, plies, wins, and throughput.

Existing shards are never overwritten. A corrupt or mismatched shard fails
loudly. A changed strategy, seed, rule profile, total game count, or shard size
cannot be resumed into the same experiment accidentally.

## Seeds and duplicate games

Without paired mode, game `i` uses `base_seed + i`. With paired mode, games
`2i` and `2i+1` use `base_seed + i`. The second game swaps the team lineups. The
three policies within each team rotate once per deal pair, controlling both deal
luck and seating position.

## Verified behavior

- A 10M dry run produced a 1,000-shard plan without materializing game records.
- A four-worker 400-game run completed every shard, and a second invocation with
  a different worker count resumed instantly without replaying a game.
- During that benchmark the host CPU was already at 100% from unrelated
  eight-process workloads, so its measured 24.37 games/s is a contention test,
  not a clean capacity estimate.

For a reliable completion-time forecast, run 10,000–100,000 representative games
when the host is otherwise idle, then divide the target count by the reported
`invocation_games_per_second`.
