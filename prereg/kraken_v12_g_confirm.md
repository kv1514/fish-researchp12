# P47 — KRAKEN v1.2, fifth attempt: the licensed arm at confirm scale

Written 2026-09-19, after P46's Stage 1 (`results/p46_screen_G.json`) was on
disk and before any P47 game was played. One arm, one fresh seed block, one
prediction. Nothing in this document is amended after the run starts.

## Why there is a fifth attempt, and why it is this one arm

P46 (`prereg/kraken_v12_belief_grid.md`) scored the belief about SESTINA's
cards at twenty cells of the model exponent and found, against its own
prediction, that the belief improves monotonically with the exponent on both
sides of the table. Its licensing rule — fixed before a position was scored,
and allowed to promote exactly one cell — licensed (0.7, 0.7) in both blocks
at both budgets, and the arm it licensed, **G = `opponent_gamma = 0.7`** on
their seats and ours, read **+0.2433 [−0.051, +0.537]** against SESTINA and
**+0.1567 [−0.055, +0.368]** in self-play at 600 pairings: the first arm in
four programmes and fourteen dueled arms whose point estimate is positive in
both populations, and the first above the +0.15 bar in both, and neither
interval clear of zero. P46's Stage 2 was allowed only for an arm that
cleared both halves at Stage 1, so it was not run, and P46 is closed with G
recorded as not clearing.

The honest way to find out whether G is worth anything is a new registration,
not a re-reading of the old one: one arm, a seed block no experiment has
touched, confirm scale, its own prediction written before the run, and never
pooled with the 600 pairings of 10,700,000. That is this document.

One point about selection, since the winner's curse is the usual reason a
confirm disappoints. G was not chosen on its play value from a menu of arms.
It was the only cell P46's belief-level rule could license, the rule was
fixed before Stage 0, and the play value was measured once, afterwards. The
Stage 1 reading is one arm's 600-pairing estimate, and its regression to the
mean is whatever one reading's is — not the regression of the best of
fourteen.

## What is deliberately not registered, and why

| candidate | why not | record |
|---|---|---|
| G at more draws (`n_draws = 720`, restoring the effective sample: P46 measured G's ESS ratio at 0.68, so at 480 nominal draws G has about 330 effective where the champion has 480) | a two-knob arm; the draws door was closed in P46 on the self-play half of the bar (480 → 1,440 is +0.0945 [−0.002, +0.191] at 6,000 pairs), and a combined arm's self-play half cannot separate the exponent from the draws. If G ships, a draws follow-up on top of it is a separate registration with its own bar. | P46, `jobs/PREREGISTRATION_precision2.md` |
| (1.0, 0.7), (0.35, 0.7), (0.7, 0.35) | closed by P46's rule: the one-sided cells on the top-1 guard, (1.0, ·) on budget robustness and an ESS ratio of 0.59. No cell is promoted after the fact, whatever it reads. | `results/p46_belief_grid.json` |
| G with `sis_tilt` or `depth_mode` changed | not part of the licensed cell; P46's grid held both at the champion's values, and P43 measured `depth_mode` as a null. | P43, P46 |
| a second population beyond the two | the ship bar is what it has been since P43; adding a third population after a near-miss would be moving the bar. | P43–P46 |

## Standing discipline, unchanged

* **Ship bar**: +0.15 sets/game with the 95% interval clear of zero in **both**
  populations — against SESTINA v1.0 through `BRIDGE_REV 3`, and against the
  v1.1 champion in self-play — paired within deal. An arm clearing one
  population only is opponent-specific and does not ship.
* Every knob bit-identical to the champion at its default, asserted by
  `tests4/` (`gamma_team = None` ≡ `gamma_team = 0.35` at `opponent_gamma =
  0.35`, so G's `opponent_gamma = 0.7` sets both sides to 0.7, which is the
  licensed cell).
* Screen and confirm never pooled. The 600 pairings of P46 Stage 1 are the
  screen; this is the confirm; the verdict is this block alone. A reader who
  wants the pooled 1,800-pairing estimate can compute it from the two files,
  and it is not the verdict.
* `wrong_distribution_outcome = "opponent"`; `BRIDGE_REV` recorded per row.
* Void conditions: any fallback, any unfinished game, any zero-width interval,
  any `IllegalAction`.

## Seeds, all new

* **Deal seed base 11,100,000**: 600 deals × 2 parities = 1,200 pairings,
  3,600 games (champion and G each against SESTINA on the same deal, plus G
  against the champion in self-play on the same deal). Barred from every
  block on the record: the v1.2 programme's 10,000,000–10,800,000; the
  signal programme's 9,300,000–10,900,000, 11,300,000, 11,700,000 and
  12,100,000; and everything below 9,300,000.
* **Agent seed base 111,000**: seat *p* in deal *d* seeds at 111,000 + 13*d* + *p*.
* Neither 10,800,000 (P46's unrun Stage 2) nor 108,000 is used, so that no
  file can be mistaken for a P46 result.

## Design

`scripts4/p47_confirm.py`: `scripts4/p46_screen.py`'s `_one` and `report`
imported, not copied — the same dual-population design as P43–P46, the same
scoring, the same deal-clustered second interval — with one arm and these
constants. It refuses to run until `results/p46_screen_G.json` is on disk.
There is no futility screen: P46's Stage 1 was the screen. Output
`results/p47_confirm.json`: `arms.G_gamma_07.vs_sestina`, `.self_play`,
`.cand_ask_hit`, `.champ_ask_hit`, `.fallbacks`, `.unfinished`, `.verdict`,
and every per-pairing row.

## The bar, and what each outcome does

* **Clears both halves** → G ships as **KRAKEN v1.2**: `V06_DEPLOYED` gets
  `opponent_gamma = 0.7` (with `gamma_team` following it, as the licensed
  cell requires), the bit-identity tests move to the new default, and the
  paper's v1.2 sections are written from this file and P46's.
* **Clears one half** → opponent-specific; does not ship; recorded.
* **Clears neither** → recorded. The programme then has no licensed arm left,
  and the paper's closing paragraph is written with G's two readings on the
  record: the belief can be sharpened, and the sharpened belief does not play
  measurably better at the power this project can buy.

## The predicted outcome, committed before the run

vs SESTINA **+0.18 [−0.03, +0.39]**; self-play **+0.11 [−0.04, +0.26]**.
The self-play half fails on the mean as well as on the interval; the
vs-SESTINA half fails on the interval alone. **Predicted: G does not clear
both halves and does not ship**, with the vs-SESTINA point estimate positive
for a second time. Ask hit rate: G above the champion by about a point again.

The reasoning, so that a wrong prediction can be traced: shrink the
600-pairing reading toward zero by about a quarter — it is one reading, no
arm in four programmes has read positive before, and P46 measured the
sharper belief as bought with a thinner sample (ESS ratio 0.68 at 480 draws,
about 330 effective where the champion has 480) — and expect the self-play
half to pay for the thinner sample on all six seats rather than on three.
The intervals are the Stage 1 standard errors scaled to 1,200 pairings.

If both halves clear, this document is wrong in the direction it would
prefer to be wrong, G ships, and P46's licensing rule will have done, at the
first attempt, what four programmes of play-level arms did not.

## Withdrawal conditions

The arm is void, not reported, if: `opponent_gamma = 0.7` is not the
licensed cell (0.7, 0.7) — i.e. `gamma_team` does not follow it; the arm is
byte-identical to the champion on any deal; any interval is zero-width; any
fallback or unfinished game occurs; either side raises `IllegalAction`.
