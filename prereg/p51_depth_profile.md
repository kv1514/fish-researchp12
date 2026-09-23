# Pre-registration: P51, the depth profile — the shape, not the exponent

Written before any P51 game.

## What P49 N1 settled, and the one thing it left open

`results/p49_n1.json` dueled `(gamma_opp, gamma_team) = (0.35, 1.4)` at 300
deals × 2 parities: **−0.1433 [−0.452, +0.166]** against SESTINA at
`BRIDGE_REV 3` and **−0.2533 [−0.478, −0.028]** in self-play. The withdrawal
condition fired. `prereg/gamma_split.md` had named that branch in advance — "if
1 is true and 3 shows no gate movement, the calibration is real and worth
nothing, which is also an answer" — so the partner **exponent** is closed.

What that duel could not distinguish is a wrong exponent from a wrong
**functional form**. Both were varied together, because `gamma_team` is the only
handle the model exposes: the log-linear tilt makes the likelihood
`depth ** (gamma · n_asks)`, a power law with no shape parameter at all. If the
exponent is right and the shape is wrong, moving the exponent cannot find it.

## The measurement that says the shape is wrong

`results/partner_choice_likelihood_14800000.json`, 300 games, 13,801 partner
asks. `P(partner asks in a half-suit | cards of it they hold)`, estimated
directly — no fitted form, no policy replay, the partner's own policy generated
the choices.

| k | pairs | chosen | P(chosen \| k) | 95% CI | weight | `k**1.4` | error |
|---:|---:|---:|---:|---|---:|---:|---:|
| 0 | 31,022 | 0 | 0.0000 | [0.0000, 0.0000] | 0.00 | 0.00 | — |
| 1 | 30,317 | 3,434 | 0.1133 | [0.1097, 0.1169] | 1.00 | 1.00 | — |
| 2 | 15,062 | 4,402 | 0.2923 | [0.2824, 0.3031] | 2.58 | 2.64 | +2.3% |
| 3 | 5,216 | 3,264 | 0.6258 | [0.6005, 0.6514] | 5.52 | 4.66 | −15.7% |
| 4 | 2,265 | 1,758 | 0.7762 | [0.7420, 0.8133] | 6.85 | 6.96 | +1.6% |
| 5 | 1,249 | 943 | 0.7550 | [0.7122, 0.7998] | 6.67 | 9.52 | **+42.8%** |

The self-test is the `k = 0` row: Fish forbids asking in a half-suit you hold no
card of, so a single k=0 choice among 31,022 pairs would mean the harness is
misreading the hand. It is exactly zero.

**`k = 6` never occurred.** Hold all six and this engine declares rather than
asking elsewhere, so the domain is `k ∈ 0..5`.

The best-fit power law is **1.40** over all k and **1.44** over `k ≤ 4`. So
`gamma_team = 1.4` is very nearly the right exponent — which is why it took the
calibration bias from −0.171 to −0.016 — and the residual error is not spread
evenly. It is **+42.8% at k = 5**, because the measured profile flattens and
turns over at the top while a power law keeps climbing.

`k = 4` and `k = 5` are where declarations live and the gate reads 0.97 on the
joint. Over-weighting exactly those worlds makes the gate fire on worlds that
are over-weighted, and `fish/engine.py::_apply_claim` awards the half-suit to
the **opponents** whenever a revealed holder is on the other team. A 43%
over-weight at the top is therefore paid at −2 a miss, which is a mechanism for
a self-play loss at an exponent whose calibration is otherwise good.

The analogous correction already exists one dimension over. `oppmodel`'s
`ALPHA_FLAT` holds the schedule profile at its vertex because "past it the fit
turns upward; the measurements do not, they flatten." The depth dimension never
got it.

## The arms

The tilt currently contributes `gamma · n_asks · log(depth)` per slot. Each arm
replaces `log(depth)` with a profile `L(depth)`, table-driven over `depth ∈
0..6`, and is applied **to teammate slots only** — opponent slots keep the
shipped power law, because the opponent exponent was measured costly
(−0.035 at 1.4) and nothing here is evidence about SESTINA's policy.

* **D1 — flattened.** `L(d) = 1.4 · log(min(d, 4))`. The minimal change: the
  measured exponent, held flat past the last count where the power law is
  accurate. One constant, no new table.
* **D2 — measured table.** `L(d) = log(weight[d])` from the table above, with
  `weight[0] = 0` handled as the hard constraint it already is and `d = 6`
  held at the `d = 5` value. The full shape.
* **D3 — measured table, opponent slots too.** D2 plus the same profile on
  opponent slots. Registered to be **demoted** on D2's result: if D2 fails,
  D3 is not run, because a profile fitted on our own policy is not evidence
  about theirs and running it anyway would be a fishing expedition.

`gamma_opp` stays at the shipped 0.35 in every arm.

## Predictions, recorded before the run

1. **D1 beats `gamma_team = 1.4` in self-play.** 1.4's self-play result was
   −0.2533; D1 differs from it only above k=4, so if the top-end over-weight is
   the mechanism, D1 recovers most of that loss. If D1 lands at −0.25 too, the
   over-weight is **not** the mechanism and the shape hypothesis is dead —
   which is the outcome that matters most, because it is the one I expect least.
2. **D2 ≥ D1**, but by little: they differ only at k=3 (−15.7%), and k=3 is
   5,216 pairs against 30,317 at k=1.
3. **Neither clears the bar.** The partner channel's measured effect runs
   through the declaration gate, and `scripts4/margin_identity.py` bounds the
   OURS channel at **+0.2017** sets a game — above the +0.15 bar but not by
   enough that a shape correction inside it should be expected to clear.
   Registered explicitly so that a null is not read as a surprise.

If 1 and 3 both hold — D1 recovers the loss and still does not ship — the
honest conclusion is that the partner channel is understood and exhausted, and
the deficit in the contested middle is not a belief problem at all.

## The bar and the withdrawal conditions

Unchanged and not negotiable: **+0.15 sets/game with the interval clear of
zero against SESTINA at `BRIDGE_REV 3` AND in self-play**, paired within deal,
300 deals × 2 parities, cluster bootstrap over deals.

An arm is **withdrawn** if either population's interval lies entirely below
zero. An arm that clears in one population only is **opponent-specific and does
not ship**, and will be reported as such rather than as a win.

`count_mode`, `gamma_schedule`, `silence_delta`, `opp_lambda` and every
convention knob stay at their shipped values in every arm. Nothing in this
registration is permitted to become a grid search: three arms, one of them
conditional, and no promotion of a cell that was not named here.
