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

---

# OUTCOME, recorded 2026-09-19

## Stage 0 — the grid, read as registered

`results/p46_belief_grid.json`: 120 games in block A (60 deals on both
parities, KRAKEN v1.1 against SESTINA v1.0 through `BRIDGE_REV 3`) and 60 in
block B (self-play); **1,657 and 868 frozen decisions**, of which 106 and 77
are excluded from every paired contrast because the incumbent took the exact
DP there; 197,704 scored rows; 540 s at three workers. Pass 2 replayed every
game action for action identical to pass 1, so the instrument touched no
decision. **No withdrawal condition fired**: no fallback, no unfinished game,
no zero-width interval, no `IllegalAction`, no bit-identity failure, no cell
byte-identical to the incumbent.

One choice the registration did not fix, stated here so that it is on the
record: the incumbent's 480-draw validity scoring has its own sampler stream,
`7,300,000 + 977 d`. Those rows enter bar 3 only and touch no paired figure.

**Bar 3, validity: holds.** The incumbent at 480 draws has mean ESS/n
**0.6284** over its 1,551 non-excluded block-A decisions; the 360 live
champion agents report **0.6169** at game end; relative gap **1.9%**, under
the 10% tolerance. Every non-incumbent cell differs from the incumbent with a
non-zero-width interval at 720 on at least one pool.

**Bar 2, calibration clause: satisfied.** The reference (0.0, 0.0) reads a
higher opp-pool NLL than the incumbent at every block and budget (block A at
720: 1.3713 against 1.3471). The C1c twin (−1.1055, 0.35) is licensed nowhere
and fails to fail nowhere: its block-A opp-pool paired interval lies entirely
above zero at both budgets. The rule is calibrated in this population.

**Bar 1, the licensing rule: exactly one cell licenses, and it is the one the
registration allowed to become an arm.** Opp-pool paired NLL against the
incumbent (lower is a better belief about their cards), with the block-A
team-pool figure and the ESS ratio at 720; game-clustered 95% intervals.

| γ_opp | γ_team | A, 720 | A, 2,880 | B, 720 | B, 2,880 | team A, 720 | ESS/inc. A, 720 | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| −1.1055 | 0.0 | +0.0751 [+0.0590, +0.0913] | +0.0737 [+0.0577, +0.0897] | +0.1174 [+0.0946, +0.1403] | +0.1165 [+0.0941, +0.1390] | +0.0634 | 0.95 | closed |
| −1.1055 | 0.35 | **+0.0620 [+0.0476, +0.0764]** | +0.0602 [+0.0461, +0.0743] | +0.1063 [+0.0851, +0.1274] | +0.1037 [+0.0836, +0.1239] | +0.0421 | **0.86** | closed (C1c twin) |
| −1.1055 | 0.7 | +0.0533 [+0.0400, +0.0666] | +0.0485 [+0.0356, +0.0614] | +0.1043 [+0.0825, +0.1261] | +0.0943 [+0.0752, +0.1133] | +0.0278 | 0.71 | closed |
| −0.5 | 0.0 | +0.0470 [+0.0387, +0.0553] | +0.0468 [+0.0385, +0.0551] | +0.0799 [+0.0650, +0.0947] | +0.0814 [+0.0667, +0.0961] | +0.0444 | 1.09 | closed |
| −0.5 | 0.35 | +0.0337 [+0.0269, +0.0404] | +0.0333 [+0.0266, +0.0400] | +0.0672 [+0.0538, +0.0806] | +0.0675 [+0.0547, +0.0802] | +0.0227 | 0.99 | closed |
| −0.5 | 0.7 | +0.0245 [+0.0180, +0.0309] | +0.0218 [+0.0153, +0.0283] | +0.0617 [+0.0477, +0.0758] | +0.0559 [+0.0436, +0.0682] | +0.0076 | 0.80 | closed |
| 0.0 | 0.0 | reference row, never paired | | | | | | (C1b twin) |
| 0.0 | 0.35 | **+0.0121 [+0.0096, +0.0146]** | +0.0125 [+0.0099, +0.0150] | +0.0268 [+0.0209, +0.0326] | +0.0285 [+0.0228, +0.0343] | +0.0083 | 1.08 | closed |
| 0.0 | 0.7 | +0.0031 [+0.0002, +0.0061] | +0.0014 [−0.0017, +0.0045] | +0.0206 [+0.0141, +0.0272] | +0.0164 [+0.0104, +0.0224] | −0.0069 | 0.86 | closed |
| 0.35 | 0.0 | +0.0127 [+0.0102, +0.0152] | +0.0130 [+0.0104, +0.0156] | +0.0134 [+0.0093, +0.0175] | +0.0152 [+0.0112, +0.0192] | +0.0212 | 1.10 | closed |
| 0.35 | 0.35 | incumbent | | | | | | |
| 0.35 | 0.7 | −0.0083 [−0.0101, −0.0064] | −0.0108 [−0.0128, −0.0088] | −0.0045 [−0.0088, −0.0002] | −0.0111 [−0.0141, −0.0082] | −0.0144 | 0.81 | closed: team top-1 below zero |
| 0.7 | 0.0 | +0.0056 [+0.0026, +0.0085] | +0.0045 [+0.0014, +0.0075] | −0.0003 [−0.0060, +0.0054] | −0.0044 [−0.0100, +0.0012] | +0.0161 | 0.89 | closed |
| 0.7 | 0.35 | −0.0064 [−0.0086, −0.0041] | −0.0082 [−0.0103, −0.0060] | −0.0115 [−0.0161, −0.0069] | −0.0186 [−0.0232, −0.0140] | −0.0043 | 0.83 | closed: opp top-1 below zero |
| **0.7** | **0.7** | **−0.0131 [−0.0163, −0.0100]** | **−0.0185 [−0.0215, −0.0155]** | **−0.0128 [−0.0208, −0.0048]** | **−0.0271 [−0.0327, −0.0216]** | **−0.0173** | **0.68** | **LICENSED** |
| 1.0 | 0.0 | +0.0058 [+0.0013, +0.0102] | +0.0019 [−0.0023, +0.0062] | +0.0063 [−0.0027, +0.0154] | −0.0089 [−0.0167, −0.0011] | +0.0168 | 0.75 | a statement about a budget (bar 5) |
| 1.0 | 0.35 | −0.0053 [−0.0094, −0.0012] | −0.0102 [−0.0140, −0.0064] | −0.0030 [−0.0117, +0.0058] | −0.0217 [−0.0289, −0.0146] | −0.0028 | 0.70 | closed |
| 1.0 | 0.7 | −0.0104 [−0.0154, −0.0053] | −0.0199 [−0.0242, −0.0155] | −0.0010 [−0.0138, +0.0118] | −0.0271 [−0.0350, −0.0191] | −0.0143 | 0.59 | closed |
| 0.35 | 0.35, λ = 0.3 | +0.0003 [−0.0001, +0.0006] | +0.0004 [+0.0000, +0.0008] | +0.0009 [+0.0002, +0.0015] | +0.0013 [+0.0006, +0.0019] | +0.0019 | 1.00 | closed at the belief level (bar 6) |
| 0.35 | 0.35, λ = 0.9 | **+0.0014 [+0.0003, +0.0026]** | +0.0016 [+0.0005, +0.0027] | +0.0036 [+0.0017, +0.0054] | +0.0041 [+0.0024, +0.0059] | +0.0074 | 0.97 | closed at the belief level (bar 6) |

Cell (0.7, 0.7) satisfies rule 1 in both blocks at both budgets: the opp-pool
interval is entirely below zero four times over, and no top-1 interval on
either pool lies entirely below zero (opp top-1 +0.0087 [+0.0031, +0.0143] in
block A at 720; team top-1 −0.0024 [−0.0080, +0.0031]). Bar 5 holds for it:
the sign agrees at both budgets and is larger at 2,880. **Arm G is licensed and
is played**, at 10,700,000, after this file was on disk.

## The prediction was wrong about the direction

This document predicted that the opp-pool NLL would *rise* with the exponent
above 0.35 — +0.005 at (0.7, 0.35) and +0.012 at (1.0, 0.35) at 2,880,
monotone — that (0.7, 0.7) would fail the rule on the opp pool, and that G
would not be played. Every part of that is wrong. **The belief about their
cards improves monotonically with γ_opp at every γ_team, at both budgets, in
both blocks, from −1.1055 through 1.0 at 2,880.** The incumbent's 0.35 is not
the sharpest belief about SESTINA's cards the engine can hold; 0.7 is a better
one on both pools at once, and 1.0 is better still at 2,880 and pays for it at
720.

The C1c twin was predicted at +0.015 [+0.005, +0.025] with an ESS ratio of
about 0.55 — "both a worse belief and a thinner sample". It reads **+0.0620
[+0.0476, +0.0764]** at 720 and +0.0602 at 2,880, four times the prediction,
with an ESS ratio of **0.86**, above the 0.70 degeneracy bar. **H1 true, H2
false: the fitted exponent is not thin, it is wrong.** The exponent that best
describes how SESTINA *asks* is the worst belief in the grid about what SESTINA
*holds*, at every budget, in both populations. That is the belief-level twin of
P43's "a correct measurement of an opponent does not license a change to us",
and it now has a mechanism: the fitted exponent is a fact about their choice
curve, and their choice curve is not their hand.

(0.0, 0.35) — the model off on their three seats only — was predicted a null
within ±0.005. It reads **+0.0121 [+0.0096, +0.0146]** at 720 and +0.0125 at
2,880 in block A, clear of zero: having no opinion about their seats is a
measurably worse belief about their cards than the incumbent's, and (+0.0083
on the team pool) about ours too, from the quota coupling. Predicted right:
the silence term is a null-or-worse (λ = 0.9: **+0.0014 [+0.0003, +0.0026]**),
its calibration mean on truth-"no" half-suits is **0.068**, under the 0.10
bar, and the knob closes at the belief level. Block B reproduces the signs of
`results/gamma_split.json` at (0.7, 0.35) and (0.7, 0.7) with game-clustered
intervals about 1.8× wider — not the 3–5× predicted.

## Why exactly one cell licenses

(0.35, 0.7) and (0.7, 0.35) both read below zero on the opp pool at all four
(block, budget) readings and both fail rule 1 on the top-1 guard: sharpening
one side alone lowers top-1 on the *other* pool — team top-1 −0.0124 [−0.0170,
−0.0078] at (0.35, 0.7), opp top-1 −0.0045 [−0.0085, −0.0006] at (0.7, 0.35).
The guard exists because a belief can win NLL by spreading mass while naming
the holder less often, and a one-sided sharpening does exactly that to the
side it does not sharpen. Raising both exponents together keeps every top-1
interval off the negative side. The price is the sample: the licensed cell's
ESS ratio is **0.68** in block A and **0.64** in block B, under the 0.70 bar,
so **degeneracy is live at the licensed cell** — part of what a sharper model
buys in belief it pays back in effective draws, and at γ_opp = 1.0 the account
overdraws: (1.0, 0.7) at an ESS ratio of 0.59 crosses zero in block B at 720
and reads −0.0271 at 2,880, and (1.0, 0.0) flips sign between the budgets in
block B — bar 5's "statement about a budget", recorded as such.

## What Stage 0 does not say

A better belief is not a better player. P43's C1c was a *correct* measurement
of SESTINA and lost −0.90 in play; the belief grid can license a cell, and only
the dual-population duel can promote it. G is played because the rule fixed
before the run says so, not because the grid predicts it wins, and this
document made no prediction about G's play value because it predicted G would
not be played.

## Stage 1 — the two halves of C1b, and the licensed arm

`results/p46_screen.json` (E0, E1, E2; 2,096 s) and `results/p46_screen_G.json`
(G; 2,085 s, started after the grid was on disk): 600 pairings per arm on the
same 300 deals at seed base 10,700,000, agent base 107,000, 7,200 games,
**zero fallbacks, zero unfinished**, no zero-width interval, no
`IllegalAction`. No withdrawal condition fires and the numbers are read as
they stand. Intervals are 1.96 SE over the 600 pairings; the deal-clustered
intervals in the files agree to the third decimal.

| arm | change from `V06_DEPLOYED` | vs SESTINA | self-play | verdict |
|---|---|---:|---:|---|
| E0 | `opponent_gamma = 0.0` (off, their seats and ours) | −0.4400 [−0.730, −0.150] | −1.0200 [−1.247, −0.793] | no |
| E1 | off on their three seats only | **−0.2500 [−0.536, +0.036]** | −1.0000 [−1.226, −0.774] | no |
| E2 | off on our two teammates only | **−0.0500 [−0.297, +0.197]** | **−0.0967 [−0.328, +0.135]** | no |
| G | `opponent_gamma = 0.7`, their seats and ours | **+0.2433 [−0.051, +0.537]** | **+0.1567 [−0.055, +0.368]** | **no** |
| E1 − E0 | what our teammates' model is worth, theirs off | +0.1900 [−0.098, +0.478] | +0.0200 [−0.255, +0.295] | |
| E2 − E0 | what their seats' model is worth, ours off | **+0.3900 [+0.095, +0.685]** | **+0.9233 [+0.606, +1.241]** | |

Ask hit rates on the same deals: champion 0.5173; E0 0.5036; E1 0.5171;
E2 0.5085; **G 0.5289**.

**Nothing ships. There is no v1.2, and the champion is unchanged.** The bar
wants +0.15 with the interval clear of zero in both populations. G's point
estimate is above +0.15 in both and neither interval clears zero, so G does
not clear the screen, and Stage 2 at 10,800,000 is **not run under this
registration**, which allows it only for an arm that clears both halves at
Stage 1. Screen and confirm are never pooled; 10,800,000 stays unused.

## C1b replicates, and its cost is on their side of the table

E0 reproduces P43's C1b on an independent block: −0.44 / −1.02 against
−0.59 / −1.07 (predicted −0.55 / −1.05). The decomposition was predicted the
wrong way round. This document expected the split to fall mostly on our side
— E1 − E0 at +0.30, E2 − E0 at +0.15, E2 at −0.40 / −0.45. **Switching the
model off on our two teammates alone costs nothing measurable**: E2 is a
null in both populations. Switching it off on their seats alone reproduces
the whole two-knob loss in self-play (−1.00 against −1.02) and most of it
against SESTINA (−0.25 against −0.44). With our model off, keeping theirs is
worth +0.39 [+0.095, +0.685] against SESTINA and +0.92 [+0.606, +1.241] in
self-play, both clear of zero; with theirs off, keeping ours is worth +0.02
in self-play and +0.19 [−0.098, +0.478] against SESTINA. The cost P43 could
not place belongs to their seats, and P43's two-knob number was, in effect,
a one-knob number.

Why the prediction had it backwards is worth a sentence. The model on our
teammates enters through the same quota coupling that makes the team pool
move with the opp pool at the belief level, and Stage 0 showed the coupling
is real (every cell that sharpens their side also moves ours). But a belief
about a teammate's cards is a belief the teammate will shortly make moot by
asking, and a belief about an opponent's cards is what our next ask is
priced on. The belief-level grid cannot see that asymmetry; only play can.

**The reading rule fires as written.** E1's vs-SESTINA interval,
[−0.536, +0.036], does not lie entirely below −0.15, so the P43 sentence
*"being wrong about an opponent's propensity beats having no opinion"* is
weakened, in the paper's P43 section and in its appendix row, to: *the model
on all five seats is an asset against SESTINA; the part on their seats,
teammates held, costs −0.25 [−0.536, +0.036] when removed, consistent with a
small asset and with zero at this power.* The other registered contrast puts
the same quantity with our model off at +0.39, clear of zero, and the two
readings agree in size; the registered one decides the sentence. The phrase
*"a result about opponent modelling and not about this opponent"*, which the
rule said to remove, does not occur in the paper, so there was nothing to
remove.

## The licensed arm is the first to read positive in both populations

G — `opponent_gamma = 0.7` on their seats and ours, the one cell Stage 0
licensed — reads **+0.2433 [−0.051, +0.537]** against SESTINA and **+0.1567
[−0.055, +0.368]** in self-play. Across four programmes and fourteen dueled
arms (the ten of P43–P45 by the paper's own count, and the four here) it is
the first whose point estimate is positive in both populations and the first above the bar in
both; and at 600 pairings neither interval clears zero, so it does not
clear. This document made no prediction about G's play value, because it
predicted G would not be played; the record should say so rather than
retrofit one.

Its ask hit rate is 0.5289 against the champion's 0.5173 on the same deals.
That is the third arm to raise the hit rate by about a point — P44's D1 and
P45's F1 did and each lost a third of a set — and the first of the three not
to lose. Nothing here separates whether the hit rate has anything to do with
G's margin; no rule was attached to it and none is added now.

## What this closes, and what it does not

P46 set out to close the belief: to put on the record that the belief about
SESTINA's cards cannot be improved by re-weighting the depth heuristic at any
exponent, at any budget, so that the paper could conclude the residual half
set is not reachable by any single knob this engine exposes. **It cannot
conclude that.** The belief improves at 0.7 on both sides, the rule licensed
the cell it was written for, and the arm it licensed is the first to read
positive in both populations.

Closed: the fitted exponent at the belief level (a worse belief, not a
thinner sample, at every budget in both populations — H1 true, H2 false);
the silence term (`opp_lambda`), at the belief level, calibration 0.068 under
the 0.10 bar; the one-sided cells (0.35, 0.7) and (0.7, 0.35), on the top-1
guard; the question of which side of the table C1b's cost belongs to; and
the prediction that the belief was already as sharp as it could be.

Open: one arm. What happens to G is a decision for a new registration, not
an amendment to this one: `prereg/kraken_v12_g_confirm.md` (P47) puts G, and
only G, at confirm scale on a fresh seed block with its own prediction, never
pooled with the 600 pairings here.

`V06_DEPLOYED` is byte-for-byte unchanged. KRAKEN v1.1 still loses to
SESTINA v1.0 by −0.5250.
