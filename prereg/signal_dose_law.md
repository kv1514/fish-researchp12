# Multiplicative or logistic? The one opponent that can tell them apart

Registered 2026-09-01, **before the 14,900,000 bank is played** and before the
instrument accepts `heuristic` in any grid. The opponent, the dose, the
predictions, the sample size and the verdicts are fixed here.

## What the matched-dose run did and did not settle

`results/matched_dose_scored.json` established that the signalling effect
transfers to a second engine at equal dose, and that it is **not** a fixed
number of percentage points: the same rate rise transferred additively predicts
+0.0423 at `ev_claim` against an observed +0.0172 [+0.0048, +0.0296].

The paper first said the effect is therefore a constant *fraction* of the
opponent's baseline errors. That was one candidate too few. Fitting the same
reference point with a constant **log-odds shift** -- the natural law for a
rate bounded by one -- predicts **+0.0188** at `ev_claim`, also inside the
interval. Both survive, and no run in this project can separate them, because
for small p the odds p/(1-p) are approximately p:

    opponent      baseline   multiplicative   logistic   ratio
    self             3.33%          +0.0081    +0.0100    0.81
    memory           4.45%          +0.0076    +0.0093    0.82
    ev_claim        10.76%          +0.0215    +0.0245    0.88
    dylan_v07       21.78%          +0.0471    +0.0467    1.01
    heuristic       72.52%          +0.0426    +0.0143    2.97

Every engine in the registry but one sits below 22%, where the two laws differ
by less than a fifth. `heuristic` sits at 72.5% and separates them by a factor
of three. That is the whole reason this registration exists.

## The opponent, and why it was excluded before

`prereg/signal_generality.md` barred `heuristic` on the ground that it declares
1.09 times a game against `dylan_v07`'s 4.02, so its whole opponent channel is
0.60 sets and "it cannot carry the effect". That reasoning was about the
CEILING and is still right about the ceiling. It is not an argument against
this test: both laws predict an effect far below 0.60, and what is being
compared is which of the two predictions the measurement lands on, not whether
the arm wins.

`heuristic` is honest -- it reads no hidden state -- and is refused by nothing
in `signal_vs_defer._opponent`.

## Predictions, computed before the run and not adjustable after

Fitted on `dylan_v07`'s own measured rise at the common dose, +1.136 points on
a 21.08% baseline: a multiplicative factor of x1.0539, or a log-odds shift of
+0.0670. Applied to `heuristic`'s 72.52% baseline over 1.092 declarations a
game:

| law | predicted extra wrong declarations a game |
|---|---|
| **multiplicative** (constant fraction) | **+0.0426** |
| **logistic** (constant log-odds shift) | **+0.0143** |
| additive in points (already excluded at `ev_claim`) | +0.0124 |

The logistic and additive predictions are close here by coincidence, not by
construction; at 72.5% a bounded law and a small additive shift happen to
nearly agree. So this run separates MULTIPLICATIVE from the other two, and
does not re-test additive, which `ev_claim` already excluded.

## Dose

The same **D = 3.1** the matched-dose study used, so the new point joins the
existing two on one operating curve rather than starting a third. `heuristic`
must be calibrated to it by the same procedure and the same code: sweep
`signal_max_p` over (0.50, 0.70, 0.85, 1.00), take the smallest value reaching
D, cap with `signal_budget` if it overshoots.

**If `heuristic` cannot reach D at `signal_max_p = 1.00`, this study is
ABANDONED and not run at a lower dose.** Comparing it to the other two at a
dose they did not share is the defect the matched-dose design exists to
prevent, and re-deriving D to fit whatever `heuristic` can reach would be
choosing the operating point after the data.

## Sample and seeds

Seed base **14,900,000**, barred from every base used before it: 2,400,000,
3,600,000, 9,300,000, 9,700,000, 9,900,000, 10,100,000, 10,500,000, 10,900,000,
11,300,000, 11,700,000, 12,100,000, 12,500,000, 13,100,000, 13,900,000 and
14,300,000. Agent seed base 149,000. Calibration on **14,700,000**, which
scores nothing. 2,500 deals x 2 parities, clustered on the deal.

## Power

`heuristic` declares 1.092 times a game against `ev_claim`'s 3.728, so its
count carries less variance per game and its half-width should be no worse than
the 0.0124 `ev_claim` returned at this sample size. The two live predictions
are 0.0283 apart, more than two such half-widths, so the design separates them
if the half-width lands anywhere near expectation.

**If the realised half-width exceeds 0.0142** -- half the gap between the
predictions -- the run cannot separate the laws and is reported UNDERPOWERED
rather than read.

## Verdicts, fixed now

- **MULTIPLICATIVE** -- the interval covers +0.0426 and excludes +0.0143.
- **LOGISTIC** -- the interval covers +0.0143 and excludes +0.0426.
- **NEITHER** -- the interval excludes both. The transfer is not a one-parameter
  function of the baseline rate, and the paper's account of it is wrong rather
  than merely under-determined. This is the outcome that would matter most and
  it is named in advance.
- **UNDERPOWERED** -- the interval covers both, or the half-width exceeds
  0.0142.
- **ABANDONED** -- `heuristic` cannot be calibrated to D.

## Withdrawal conditions

1. **The margin identity closes** on both arms, checked from the recorded
   ledger. The matched-dose run could not check this because the instrument did
   not record our own declarations; it does now, and this run has no excuse.
2. **`A_shipped` is bit-identical to the champion.**
3. **The realised dose is within 15% of D**, as in the matched-dose study.
4. **No unfinished games and no bridge fallbacks.**

## What this cannot do

It puts a third point on a curve fitted from one. Three points across 3% to
72.5% is a better constraint than two across 8% to 22%, and it is still a
one-parameter family chosen from two candidates rather than a mechanism. A law
that fits three points is not thereby explained, and this document does not
claim that the opponent's error rate is the only thing the transfer depends on
-- only that at these three baselines it is enough to predict the effect, or
that it is not.

Nothing enters `V06_DEPLOYED` on any outcome.
