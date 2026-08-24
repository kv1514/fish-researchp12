# `fish4.evalx` - evaluation infrastructure for FishBot v0.4

Four modules, each written against a specific way the v0.3 pipeline could
mislead us.

| module | what it does | the failure it prevents |
|---|---|---|
| `harness.py` | paired-deal play, optional seat rotation, resumable log | silently dropped timeouts; lost long runs; unstated variance |
| `sequential.py` | always-valid stopping rules (e-value / confidence sequence) | peeking at a fixed-n interval and calling it significance |
| `ablation.py` | decision-for-decision identity checking | a "one-term ablation" that silently changes two things |
| `registry.py` | append-only, atomically-written experiment records | un-rerunnable results; wrong results quietly deleted |

Every number below was measured by code in this package or in `scripts4/`,
on this machine, at 4 worker processes. Nothing here is an estimate unless it
says so.

---

## 1. The measured constants

Matchup: **`tuned(w_turn=0.6, w_scarce=0.2)` vs `probabilistic`** - the
current champion against its own baseline. That is the right pair to
calibrate on, because the standard deviation that matters is the one between
policies of the strength we will actually be comparing.

| quantity | value |
|---|---|
| paired deals | 300 (0 dropped, 0 timeouts) |
| **per-pair SD of the set differential** | **3.869 sets** |
| mean set differential | +1.263 [+0.824, +1.703] (95% t) |
| paired score | 0.623 [0.567, 0.676] (Wilson) |
| observed range of the differential | -11 to +11 (theoretical bound ±18) |
| **wall clock per paired deal, 4 workers** | **1.201 s** (1.67 games/s) |
| CPU per paired deal (single process) | 4.78 s |
| sets: champion / baseline / null | 2754 / 2375 / 271 |

Source: `results/v04_eval_calibration.json`, produced by
`py scripts4/measure_calibration.py 300 120`. The wall-clock figure was
measured with 4 workers on an 8-core machine that had other jobs running, so
it is a realistic operating cost rather than a best case; the observed rate
drifted between 0.83 and 1.03 pairs/s over the run. The CPU-per-pair figure
is recorded per pair by the worker itself and is not affected by contention.

Two things worth noticing. The differential distribution is *wide*: an SD of
3.87 sets on a mean of 1.26 means a single pair says almost nothing, and a
"quick 50-deal check" of a strategy tweak can resolve nothing smaller than
1.5 sets/pair. And the deck bound of ±18 is nowhere near tight - real pairs
stayed inside ±11 - which matters because the sequential procedures are
stated for bounded observations and pay a (second-order) price for a loose
bound.

## 2. How many paired deals do I need?

Fixed-n, two-sided, `alpha = 0.05`, at the measured SD of 3.869:
`n = ((z_{0.025} + z_beta) * sd / delta)^2`. Hours assume 1.201 s/pair at 4
workers.

| effect (sets/pair) | pairs @ 80% power | pairs @ 90% power | hours @ 80% |
|---|---|---|---|
| 0.10 | 11 751 | 15 731 | 3.9 |
| 0.20 | 2 938 | 3 933 | 0.98 |
| **0.30** | **1 306** | 1 748 | **0.44** |
| 0.50 | 471 | 630 | 0.16 |
| 0.75 | 209 | 280 | 0.07 |
| 1.00 | 118 | 158 | 0.04 |
| 1.50 | 53 | 70 | 0.02 |
| 2.00 | 30 | 40 | 0.01 |
| 3.00 | 14 | 18 | 0.005 |

Read the other way: the 600-pair cells of the v0.3 champion search could
resolve effects down to about **0.44 sets/pair** at 80% power, and every
"no significant difference" it reported below that size was uninformative
rather than negative. The champion's own margin (1.26) was comfortably
inside range; a plausible next refinement at 0.3 needs roughly twice the
deals the whole v0.3 search used per cell.

## 3. Sequential testing: measured type-I error and power

Procedures: an empirical-Bernstein **confidence sequence** and a pair of
one-sided **betting test supermartingales** (Waudby-Smith & Ramdas), both
anytime-valid for bounded observations. `naive_t` is the comparator, not a
candidate: it is the fixed-n 95% t-interval peeked at after every deal.

### Type-I error under continuous monitoring

4000 synthetic null experiments per cell, each monitored after **every one**
of 4000 paired deals (16 million monitored decisions per cell). Nominal
`alpha = 0.05`. Intervals are exact Clopper-Pearson.

| null distribution | `betting` | `eb_cs` | `naive_t` (peeking) |
|---|---|---|---|
| bootstrap of the real measured differentials | **2.08%** [1.66, 2.57] | **0.48%** [0.29, 0.74] | 68.78% [67.31, 70.21] |
| truncated Gaussian, sd 3.869 | **2.43%** [1.97, 2.95] | **0.30%** [0.16, 0.52] | 69.73% [68.28, 71.15] |
| skewed two-point, sd 3.869 | **2.33%** [1.88, 2.84] | **0.53%** [0.33, 0.80] | 92.08% [91.19, 92.89] |

Both procedures hold at or below the nominal 5% against all three nulls,
including the deliberately nasty skewed one. Peeking at the fixed-n interval
rejects a true null **69%** of the time against the real distribution and
**92%** against a skewed one, with a median false stop after **11** and **3**
deals respectively. That is the entire justification for this module: the
undisciplined procedure is not slightly optimistic, it is wrong almost every
time.

The two valid procedures are *conservative* (2.1-2.4% and 0.3-0.5% against a
nominal 5%). That is the price of nonparametric anytime validity with a loose
range bound, and it shows up as lost power, not as a false claim.

### Power against the realistic alternative

Effect **0.3 sets/pair** at the measured SD of 3.869, noise resampled from
the real per-pair differentials, `n_max = 20 000`, 4000 repetitions:

| effect | method | power (correct sign) | median stop | mean stop | fixed-n @ 80% |
|---|---|---|---|---|---|
| 0.15 | betting | 98.6% | 5 791 | 6 432 | 5 223 |
| 0.15 | eb_cs | 91.1% | 7 882 | 8 567 | 5 223 |
| **0.30** | **betting** | **100.0%** | **1 330** | 1 562 | 1 306 |
| 0.30 | eb_cs | 100.0% | 1 963 | 2 236 | 1 306 |
| 0.50 | betting | 100.0% | 469 | 561 | 471 |
| 0.50 | eb_cs | 100.0% | 781 | 859 | 471 |
| 1.00 | betting | 100.0% | 177 | 189 | 118 |
| 1.00 | eb_cs | 100.0% | 308 | 320 | 118 |

Not one rejection in any power cell pointed the wrong way.

The betting test is the default because at the effect this project cares
about it stops **32% sooner** than the confidence sequence for the same
alpha. Against the fixed-n plan it is close to free: the same 1330 pairs, but
with ~100% power instead of 80%, the option to stop far earlier when the
effect turns out to be larger, and no obligation to pick `n` before knowing
the answer. At large effects (1.0 sets/pair) it costs about 50% more deals
than a correctly-sized fixed-n test - the premium for not having had to
guess the size in advance.

Source: `results/v04_sequential_calibration.json`, produced by
`py scripts4/run_typeI_simulation.py 4000 4000 20000` (244 s). A reduced
version (1500 reps x 600 monitored steps) runs in `tests4/test_evalx.py` on
every test run and asserts on the Clopper-Pearson *upper* limit, so it fails
when the procedure is invalid rather than when the simulation is unlucky.

## 4. Antithetic seat rotation: it does not pay

The harness can replay each deal from several rotated starting seats and
average. This is guaranteed to reduce variance *per deal*. The question that
decides whether to use it is whether it reduces variance *per game played*,
since R seats cost R times as many games. With intra-deal correlation `rho`:

```
Var(deal mean) = sigma^2 (1 + (R-1) rho) / R
compute-matched efficiency = 1 / (1 + (R-1) rho)      # > 1 means it wins
```

Measured on the champion-vs-baseline matchup, 120 deals per spacing:

| seat offsets | R | sd/seat | sd/deal | per-deal variance | intra-deal corr | compute-matched efficiency |
|---|---|---|---|---|---|---|
| (0, 2, 4) | 3 | 3.576 | 2.009 | x0.316 | **-0.027** | **1.056** [0.87, 1.31] |
| (0, 3) | 2 | 3.472 | 2.631 | x0.574 | **+0.149** | **0.871** [0.75, 1.05] |

**Verdict: no measured benefit.** Neither bootstrap interval excludes 1 and
the two point estimates straddle it. The large-looking per-deal variance
reduction (x0.32 at R=3, close to the x1/3 you get from three *independent*
observations) is arithmetic, not a discovery - it is what averaging three
near-uncorrelated replicates does, and you would get the same by playing
three times as many independent deals for the same cost.

The interesting by-product is `rho ~ 0`: after the team swap has already
removed the deal's advantage, replaying the *same cards* from a different
starting seat produces an essentially uncorrelated outcome. Which seat leads
matters about as much as which cards were dealt.

Seat rotation is therefore **off by default** (`seat_offsets=(0,)`, which also
makes the harness byte-identical to v0.3). It is kept because it does make
each pair a lower-variance observation, which matters in the one case where
deals rather than games are the scarce resource - for example replaying a
fixed archived set of deals.

## 5. The ablation guard

`py scripts4/run_ablation_guard.py 8` audits every `TunedAgent` term over 8
real games, at all six seats, driven by the baseline's own play (855 audited
decisions):

- `tuned{}` reproduces `probabilistic{}` at **855 / 855** decisions. The
  ablation is not confounded.
- Divergence rate of each term when switched on:

| term | decisions changed |
|---|---|
| `w_turn=1.6` | 25.7% (220/855) |
| `w_turn=0.6` | 12.5% (107/855) |
| `w_scarce=0.2` | 11.9% (102/855) |
| `w_reveal=0.15` | 8.4% (72/855) |
| `w_deplete=0.3` | 7.1% (61/855) |

Both halves matter. A candidate that fails the first check makes every cell
of a study compare two changes at once - the exact v0.3 failure, which ran to
n=1000 and produced tight, confident, wrong intervals. A candidate that fails
the second can only ever report "no significant difference", which reads like
evidence of no effect and is not.

The failure message names the first diverging position in full:

```
ABLATION IS CONFOUNDED: ('tuned', {'w_suit': 0.01}) does not reduce to ('probabilistic', {}).
first divergence at game 0 (deal_seed=1100033), ply 0, seat p0
    hand            : 3C 6C 6H TC JC QH KH QS RJ
    hand counts     : [9, 9, 9, 9, 9, 9]
    unresolved suits: [0, 1, 2, 3, 4, 5, 6, 7, 8]
    legal asks      : 81
    baseline chose  : ASK p3 for 7C
    candidate chose : ASK p1 for BJ
Every cell of an ablation built on this pair would compare two changes at once.
```

## 6. Using it

```python
from fish4.evalx import HarnessConfig, run_paired, SequentialTest
from fish4.evalx.registry import record_paired_result

cfg = HarnessConfig(
    spec_x=("tuned", {"w_turn": 0.6, "w_scarce": 0.2}),
    spec_y=("probabilistic", {}),
    n_pairs=1400,                 # from the table in section 2
    base_seed=4_040_000, agent_seed_base=40_400,
    n_workers=4,                  # 4 is the cap on this machine
)
res = run_paired(cfg, log_path="results/logs/my_run.jsonl")
res.check_drops()                 # refuses to report if timeouts biased it
print(res.summary())
record_paired_result("my experiment", res, evidence_tier="DEMONSTRATED")
```

Interrupt it and re-run the same call: the log is replayed and only the
missing deals are played, and the result is identical to an uninterrupted run
(asserted by test). Change any field that affects the numbers and it refuses
to append rather than mixing two experiments in one file.

Stopping early:

```python
test = SequentialTest(alpha=0.05, lower=-cfg.diff_bound, upper=cfg.diff_bound,
                      n_max=4000)
for d in stream_of_per_pair_differentials:
    out = test.update(d)
    print(out.summary())
    if out.stopped:
        break            # decision is "x_better" / "y_better" / "inconclusive"
```

Ablation pre-flight, before spending any CPU on a duel:

```python
from fish4.evalx.ablation import assert_ablation_is_clean
assert_ablation_is_clean(("probabilistic", {}), ("tuned", {}),
                         ("tuned", {"w_turn": 0.6}), n_games=8)
```

Registry:

```
py -m fish4.evalx.registry --list
py -m fish4.evalx.registry --show <id>
py -m fish4.evalx.registry --verify
py -m fish4.evalx.registry --retract <id> --reason "confounded ablation"
```

Retraction appends a retraction record; the original line is never rewritten
or removed, and `load_all` folds the retraction in so a reader cannot miss
it.

## 7. What is NOT claimed

- **The SD is for one matchup.** 3.869 sets/pair was measured between
  `tuned(0.6, 0.2)` and `probabilistic`. Duels between more similar policies
  will have a smaller SD (more shared decisions) and duels across a large
  strength gap a larger one. Re-measure before planning a study on a very
  different pair; `scripts4/measure_calibration.py` is a two-line edit.
- **The sequential procedures are conservative, not exact.** Measured
  type-I is 2.1-2.4% (betting) and 0.3-0.5% (CS) against a nominal 5%. They
  are valid, and they leave power on the table. A tighter declared range than
  ±18 would recover some of it; the observed range was ±11, but narrowing the
  declared bound to something the data merely *happened* to respect would
  trade a real guarantee for a smaller interval, so it has not been done.
- **The rotation verdict is "no measured benefit", not "proven useless".**
  120 deals per spacing leaves the efficiency interval wide ([0.87, 1.31] and
  [0.75, 1.05]). What is established is that there is no *large* win to be
  had, which is enough to leave it off by default.
- **Power numbers assume i.i.d. per-pair differentials.** That follows from
  the pairing construction (independent deals, independent agent seeds), and
  is the same assumption v0.3's t-intervals rest on.
- **This package does not evaluate the v0.4 inference layer.** It deliberately
  does not import `fish4.counting` or `fish4.posterior`, so it can be used to
  judge them.

## 8. Reproducing

```
py scripts4/measure_calibration.py 300 120      # ~15 min at 4 workers
py scripts4/run_typeI_simulation.py 4000 4000 20000   # ~4 min, numpy only
py scripts4/run_ablation_guard.py 8             # ~1 min
py -m pytest tests4/test_evalx.py -q            # 49 s idle, 97 s under load
```

Outputs: `results/v04_eval_calibration.json`,
`results/v04_sequential_calibration.json`, `results/v04_ablation_guard.json`,
resumable pair logs under `results/logs/`, and experiment records in
`results/experiments_v04.jsonl`.
