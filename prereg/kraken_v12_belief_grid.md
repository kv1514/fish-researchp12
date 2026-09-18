# P46 — KRAKEN v1.2, fourth attempt: the belief about SESTINA's cards, and the two halves of C1b

**Written before any instrument position was scored and before any candidate
game was played. Cells, arms, seeds, bars, order and the expected outcome are
fixed here and are not amended afterwards.**

## Why there is a fourth attempt, and why it is this one

Three programmes put ten arms at a deficit of **−0.5250 [−0.6886, −0.3614]**
sets a game against SESTINA v1.0 through `BRIDGE_REV 3`, and none cleared
either half of the bar (`prereg/kraken_v12_vs_sestina.md`,
`prereg/kraken_v12_declaration_latency.md`, `prereg/kraken_v12_free_message.md`).
Two findings replicated across them: raising the ask hit rate makes the engine
worse (P44 D1, P45 F1), and a deterministic tie-break costs 0.86 sets a game in
self-play (P45). The ownership closure (`results/ownership_estimators.json`)
left only the split standing, and the split's one mechanism lost (P45).

What has **never been measured against SESTINA at `BRIDGE_REV 3`** is the belief
itself. No value of the opponent-model exponent has been scored on
SESTINA-held cards against the dealt truth; no Kish ESS has been recorded off
`gamma = 0.35`; and P43's most-quoted sentence — *"the mis-signed opponent model
is an asset: being wrong about an opponent's propensity beats having no
opinion"* — rests on a **two-knob** difference. P43's C1b (`opponent_gamma =
0.0`) switched the model off on SESTINA's three seats *and* on our two
teammates, because `gamma_team` defaults to `opponent_gamma`
(`fish4/oppmodel.py`, teammate slots keyed on `key[0] % 2 == me % 2`). Whether
the −0.59 / −1.07 it cost is a fact about the opponent or about the teammates
has not been separated.

P46 measures the belief first, plays the single-knob decomposition second, and
registers exactly one conditional path to a shipping arm.

## What is deliberately not registered, and the record that closes each door

Recorded so that the omission is a decision and not an oversight:

| candidate | why not | record |
|---|---|---|
| the draws budget (`n_draws = 1920`) against SESTINA | an arm's only ship route is the dual bar, and the self-play half is already measured: 480 → 1440 is **+0.0945 [−0.002, +0.191]** at 6,000 pre-registered pairs, *not demonstrated*, with log-linearity broken at $z = -3.54$. A 600-pairing half cannot overturn that, so the arm's verdict is null-or-opponent-specific before a game is played. The located deficit is flat in draws on the champion's own decisions: split-joint bias −0.219 / −0.244 / −0.237 at 480 / 1920 / 5760. | `jobs/PREREGISTRATION_precision2.md`, `results/precision2_verdict.json`, `results/split_why.json` |
| `n_worlds` | **inert on the act path by construction**: `Posterior.worlds()` has no caller in `agent4.py`, `askfeat.py`, `claim4.py` or `lookahead.py`; `n_worlds` reaches play only through the SIS-failure fallback. A 3-game probe at 64 and 128 worlds reproduced the champion's games byte for byte. Not a null — a no-op. | `fish4/posterior.py` |
| `lookahead_depth = 4`, `lookahead_beam = 8` | changed no decision in a 320-decision probe against SESTINA at 2.0× and 1.15× the cost. Not closed, but not the place to spend 1,800 games either. | this document |
| a joint-scored split for **voluntary** claims (extending `claim_forced_exhaustive`) | closed by proof: the shortlist's first entry is the per-card marginal argmax and is always joint-scored, and $P_{\text{joint}}(A) \le \min_c M[c, A_c]$ holds exactly because both come from the same weighted batch; so any split with joint above $0.5$ has every marginal above $0.5$, *is* the shortlist head, and is already scored. | `fish4/claim4.py`, `fish4/posterior.py` |
| swapping or recalibrating the ownership estimator | closed by measurement: all three cross $0.99$ on $4.17\%$ of owned half-suits; the gate is flat in ownership from $0.77$ to $0.20$. | `results/ownership_estimators.json` |
| the convention, either half | closed in play: receiving is a null at 3,000 pairs; sending loses at every gate ever tried. | P8, P45 |

## Standing discipline, unchanged

* **Ship bar**: +0.15 sets/game with the 95% interval clear of zero in **both**
  populations — against SESTINA v1.0 through `BRIDGE_REV 3`, and against the
  v1.1 champion in self-play — paired within deal. An arm clearing one
  population only is opponent-specific and does not ship.
* Every knob bit-identical to the champion at its default, asserted by
  `tests4/` (`gamma_team = None` ≡ `gamma_team = 0.35` at `opponent_gamma =
  0.35`; `opp_lambda = 0.0` off).
* Screen and confirm never pooled; nothing added to any cell or arm list after
  Stage 0 has been written to disk.
* `wrong_distribution_outcome = "opponent"`; `BRIDGE_REV` recorded per row.
* Void conditions: any fallback, any unfinished game, any zero-width interval,
  any cell byte-identical to the incumbent where it should differ, any
  `IllegalAction`.

## Seeds, all new

Grep-clean across `scripts4/`, `jobs/`, `prereg/`, `results/*.json`, `fish4/`,
`tests4/` at the time of writing. Last block used by this programme was
10,300,000 (P45 confirm, never run).

| stage | deal seeds | agent seeds | per-decision sampler seeds |
|---|---|---|---|
| 0, block A (cross-engine) | 10,600,000 – 10,600,059, each at both parities | 106,000 + deal·13 + seat | 7,200,000 + 977·d at 720 draws; 7,250,000 + 977·d at 2,880 |
| 0, block B (self-play twin) | 10,600,500 – 10,600,559, one game each | 106,000 + deal·13 + seat | same two streams, d continuing |
| 1, screen | 10,700,000 – 10,700,299, each at both parities, per arm | 107,000 + deal·13 + seat | — |
| 2, confirm | 10,800,000 – 10,800,599, each at both parities | 108,000 + deal·13 + seat | — |

`d` is the global index of the frozen decision. The two sampler streams are
disjoint from every recorded instrument (6,100,000 `gamma_split`; 6,400,000
`channel_precision`; 7,100,000 `precision_generality`).

## Stage 0 — the instrument. Ships nothing.

`scripts4/p46_belief_grid.py`, ported from `scripts4/gamma_split.py`, output
`results/p46_belief_grid.json` with **every per-decision row kept**.

**Play is the champion throughout.** Block A: `KRAKEN_V1` on one parity,
`("dylan_v07", {})` on the other, 60 deals × 2 parities = 120 games. Block B:
six `KRAKEN_V1` seats, 60 games. At every 4th decision of the scored seats
(block A: our three seats; block B: the even team's three seats) the position
is frozen **after `act()` and before `apply()`**, so the belief has absorbed the
public history up to that decision, and the transcript stays the champion's
game byte for byte (the agent's RNG state is saved and restored around every
instrument posterior).

**Exclusion, fixed now.** Decisions at which the incumbent takes the exact DP
— no non-self ask on record, so `oppmodel.build` returns no model and
`use_exact` is true — are excluded from every paired contrast: on them the
cells are not the same particles re-weighted but two different inference
methods, and the comparison would be about the method. Cell (0.0, 0.0) takes
the DP at *every* decision and is therefore a **reference row only**, never
paired.

**Cells, 20, fixed now.** `gamma_opp ∈ {−1.1055, −0.5, 0.0, 0.35, 0.7, 1.0}` ×
`gamma_team ∈ {0.0, 0.35, 0.7}` (18), plus `opp_lambda ∈ {0.3, 0.9}` at
(0.35, 0.35). The incumbent is (0.35, 0.35). −1.1055 is SESTINA's fitted
exponent at `BRIDGE_REV 3` (`results/choice_curve_foreign.json`, P43 R0); 0.7
rather than 0.6 so the upward cells are the exact twins of
`results/gamma_split.json`'s self-play (0.7, 0.35) and (0.7, 0.7); 0.9 is the
SESTINA-derived silence weight and 0.3 the same derivation on the champion's
own latency, so the pair is population-neutral.

**Two budgets, fixed now.** Every cell at every frozen decision is rebuilt at
**720 and 2,880 draws**, with the same sampler seed in every cell at a budget.
At `sis_tilt = 0` and `depth_mode = "initial"` the model enters the importance
weights only, so cells at one budget share particles and differ only in
weights — a paired comparison in the strict sense. The two budgets exist
because the record (`results/channel_precision_plateau.json`) shows the
*sign* of an opponent-pool NLL contrast can be a function of effective budget:
a cell that spreads the log-weights thins the sample, and a thinner sample
pays a finite-sample penalty of unknown size at a fixed nominal budget.

**Scored per cell, per decision, per budget.** Cards not pinned by the
propagator, in two pools by the arbiter's truth: **opp** (true holder an
opponent — in block A, a SESTINA seat) and **team** (true holder a teammate).
NLL, Brier and top-1 per pool, paired against the incumbent cell over the same
decisions, intervals **clustered by game** with `fish4.clustered.cluster_ci`
($t$ at $k-1$ df; $k = 120$ in block A, $60$ in block B). Kish ESS of each
cell's batch, recorded per row. Plus: the incumbent cell scored **once at 480**
in block A, the live champion agents' `PosteriorStats.mean_ess` at game end,
and the `opp_lambda` calibration number — the incumbent's mean $P(\text{all six
with the opponents})$ over live half-suits in which the acting seat holds none,
split by truth, deal-clustered.

### Bars, fixed now

1. **Licensing rule** (dual, mirroring the ship bar). A cell licenses a play
   arm only if, in block A, its **opp-pool paired NLL interval lies entirely
   below zero at both 720 and 2,880** *and* neither pool's paired top-1
   interval lies entirely below zero at either budget, *and* the same rule
   holds in block B. **The only cell that can become an arm is (0.7, 0.7) =
   arm G below.** No other cell is promoted after the fact, whatever it reads.
2. **Calibration clause.** Cells (0.0, 0.0) and (−1.1055, 0.35) are the belief
   twins of P43's dueled C1b and C1c, which lost −0.59 and −0.90 in play. If
   the licensing rule licenses either, or fails to fail (−1.1055, 0.35), the
   rule is recorded as **uncalibrated in this population** and the grid is
   reported as descriptive, closing nothing. (0.0, 0.0) is checked on its
   reference reading, not paired.
3. **Validity.** The incumbent cell at 480 must reproduce the live champion's
   mean ESS/480 within **10%** (10 rather than 5 because the live counter mixes
   in claim-time posteriors). Every non-incumbent cell must differ from the
   incumbent with a non-zero-width interval on at least one pool at 720 — the
   P43 C3 lesson, where an unrecognised value fell through to the default.
4. **H2 statistic.** Mean ESS/n of each cell relative to the incumbent at the
   same nominal n; **bar 0.70**, below which sample degeneracy is live for
   that cell. A cell whose ESS/n at 720 is under **0.25** of the incumbent's is
   reported *not budget-robust* — neither closed nor licensed — because 2,880
   nominal draws do not then reach the incumbent's 720 effective.
5. **Budget robustness.** A cell is *closed* or *licensed* only if its opp-pool
   NLL sign agrees at 720 and 2,880; disagreement is reported as a statement
   about a budget, with the 2,880 − 720 difference given as the sampling
   component.
6. **`opp_lambda` gate.** Closed at the belief level unless rule 1 holds in
   both blocks *and* the calibration mean on truth-"no" cells exceeds 0.10. No
   `opp_lambda` duel exists in P46 either way.

## Stage 1 — the registered arms

`scripts4/p46_screen.py`, the dual-population design of `scripts4/v12_screen.py`
verbatim (champion and candidate each play the same deal against SESTINA on
both parities, plus candidate-versus-champion self-play on the same deal), with
its own `ARMS` and constants. **Runs only after Stage 0 has been written to
disk.** 300 deals × 2 parities per arm.

| arm | change from `V06_DEPLOYED` | what it separates |
|---|---|---|
| **E0** | `opponent_gamma = 0.0` | P43's C1b replicated on this block, so every contrast below is within deal |
| **E1** | `opponent_gamma = 0.0, gamma_team = 0.35` | model **off on SESTINA's seats only**; teammates keep the champion's |
| **E2** | `opponent_gamma = 0.35, gamma_team = 0.0` | model **off on our teammates only**; SESTINA's seats keep the champion's |
| **G** | `opponent_gamma = 0.7` | the upward cell, **licensed only by Stage 0 rule 1** for cell (0.7, 0.7) in both blocks at both budgets; otherwise recorded as *not licensed* and no game is played |

E0–E2 carry no futility screen — a belief-level screen on them cannot fail,
and their purpose is a within-deal decomposition rather than a ship — so their
gates are the void conditions. Paired contrasts **E1 − E0** and **E2 − E0** are
reported (expected SE ≈ 0.144 from the recorded per-pair SD of P43's
candidate contrasts). **No equivalence claim is made at any margin**: an
equivalence at 0.15 would need roughly 2,450 pairings.

**Reading rule for the paper's P43 sentence, fixed now.** *"Being wrong about an
opponent's propensity beats having no opinion"* is retained only if E1's
vs-SESTINA interval lies entirely below −0.15. Otherwise it is weakened to:
*the model on all five seats is an asset against SESTINA; the part on their
seats, teammates held, costs E1 [interval] when removed, consistent with a small
asset and with zero at this power* — and *"a result about opponent modelling
and not about this opponent"* is removed.

Order: E0, E1, E2 in one job; then G if licensed.

## Stage 2 — confirm

10,800,000, 600 deals × 2 parities, **only** for an arm that clears both halves
of the bar at Stage 1, never pooled with Stage 1. Predicted not to run.

## The predicted outcome, committed before the run

**Stage 0.** No cell with `gamma_opp` outside {0.0, 0.35} licenses.
(−1.1055, 0.35): opp-pool NLL **+0.015 [+0.005, +0.025]** at 720 and
**+0.010 [+0.002, +0.018]** at 2,880 — sign agrees, smaller at the high
budget because part of the 720 figure is ESS penalty — top-1 lower by about
0.005, ESS/n ratio about 0.55 at both budgets: **H2 live and H1 true**, the
fitted exponent is both a worse belief about their cards and a thinner sample.
(0.0, 0.35): opp-pool NLL within ±0.005 of zero at both budgets, a null;
team-pool NLL +0.010 worse at both, from the quota coupling. (0.7, 0.35) and
(1.0, 0.35): opp-pool NLL +0.005 and +0.012 at 2,880, monotone, top-1 lower.
(0.7, 0.7): team-pool NLL −0.010 as in self-play but opp-pool NLL ≥ 0, so it
**fails the licensing rule and G is not played**. (0.35, 0.7): team top-1 worse.
`opp_lambda = 0.9`: opp-pool NLL −0.002 [−0.006, +0.002] at both budgets, a
null; calibration mean on truth-"no" cells about 0.04, under 0.10, so the knob
closes at the belief level. Block B reproduces `results/gamma_split.json`'s
signs with game-clustered intervals three to five times wider. Calibration
clause satisfied.

**Stage 1**, vs SESTINA / self-play, 600 pairings each:
E0 −0.55 [−0.85, −0.25] / −1.05 [−1.27, −0.83] (C1b replicates);
E1 −0.25 [−0.55, +0.05] / −0.60 [−0.85, −0.35];
E2 −0.40 [−0.70, −0.10] / −0.45 [−0.70, −0.20];
E1 − E0 = +0.30 [+0.02, +0.58]; E2 − E0 = +0.15 [−0.13, +0.43].
**Nothing clears either half of the bar. Stage 2 is not run. There is no v1.2,
and the champion is unchanged.** The P43 sentence is weakened as above.

**Most likely outcome: nothing ships**, for the fourth time, and the value of
the programme is the first belief-level table against SESTINA at two budgets
with ESS, the closure of the gamma sweep in the SESTINA population, the H1/H2
decomposition of C1c, a measured rather than footnoted `opp_lambda` result, and
the single-knob decomposition of C1b.

## Withdrawal conditions

A cell or arm is void, not reported, if: a knob is not bit-identical at its
default; a cell is byte-identical to the incumbent where it should differ; any
interval is zero-width; any fallback or unfinished game occurs; the validity
check (bar 3) fails, in which case the whole grid is void and re-run only after
the cause is found; either side raises `IllegalAction`.

## What would close the programme

The "beat SESTINA" programme closes honestly when three things are on the
record together. The deficit is measured, located and sized (it is). Every
one-knob lever the engine's own diagnostics nominate has been registered and
lost or stopped (the ask channel, P43; the declaration gate, P44 and the
ownership closure; the convention, P45; and the two replicated findings that
make the obvious fixes wrong). And — what P46 adds — that the belief about
SESTINA's cards cannot be improved by re-weighting the depth heuristic at any
exponent, on either side, at any budget up to 2,880 draws, with the sign robust
across budgets and the calibration clause satisfied; that the silence term does
not move it either; and that the one asset the model *is* decomposes into a
part about them and a part about us. If P46 returns that, the paper is allowed
to conclude that the residual half set is not reachable by any single knob this
engine exposes, and that the next attempt would have to change what the engine
computes rather than what it is told.
