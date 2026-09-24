# Pre-registration: P55, the two knobs together — a coordinate optimum is not a joint one

Written before any P55 game.

## Why a joint search is not a re-run of P53 and P54

P53 swept `w_suit` alone and P54 swept `w_scarce` alone, 14,400 duel games
between them, and both found the shipped value at or just below a coordinate
optimum with the downward direction expensive. **That is coordinate-wise
optimality, and it does not imply joint optimality.** A function can be at a
maximum along every axis through a point and still rise along a diagonal.

There is direct evidence of interaction rather than a bare possibility:

* **P51** — the dose response was non-monotone in both populations, and the
  registration's own reading was "the term is interacting with `turn` or
  `scarce` rather than adding";
* **P52** — non-monotone again, and its best cell was disqualified for it;
* **P54** — non-monotone across the four doses (C4 best, C1/C2/C3 worse in
  order).

Three of the last four registrations failed a monotonicity condition. That is
what interaction looks like in a one-knob-at-a-time design.

And the direction is indicated rather than guessed: **the best arm on each axis
was the upward one.** P53's B4 (`w_suit = 0.12`) was the least bad of four and
better than the shipped value in neither population but close; P54's C4
(`w_scarce = 0.40`) was **+0.1200** in self-play, the only positive figure either
sweep produced. Both point away from the origin along the same diagonal, and
neither sweep could see that corner because each held the other knob fixed.

The 2026 ridge fit that moved all ten terms at once and lost −0.745 [−0.914,
−0.576] is **not** this: that vector was fitted to a rollout target and never
dueled cell by cell, and the paper is explicit that "the individual signs are not
findings". A screened grid scored by actual duels has never been run.

## The design, and the multiplicity it has to survive

**Eight cells are eight chances for noise to look like a winner.** So this is a
two-stage design and the second stage is on a **different seed block**:

* **Stage 1, screening.** `w_suit ∈ {0.06, 0.12, 0.24}` ×
  `w_scarce ∈ {0.20, 0.40, 0.80}`, minus the shipped cell (0.06, 0.20), at
  **100 deals × 2 parities** on block **17,900,000**.
* **Stage 2, confirmation.** Every cell whose self-play *and* SESTINA point
  estimates are both ≥ 0 at stage 1 is re-run at **300 deals × 2 parities** on
  block **18,100,000**. A different block, because P51 established that a
  cross-block comparison can invent an effect worth 0.117 sets.

**No cell advances on a stage-1 interval.** Screening at 100 deals is
underpowered by design and its intervals will cover zero; the rule is on the
point estimates only, and stage 1 confers nothing but the right to be measured
properly. **A cell that clears the bar at stage 2 has been selected once and
tested once, and that is the whole reason for the second block.**

If no cell passes the stage-1 rule, **P55 ends there** and reports a null. It
does not get re-scoped into a finer grid.

## Predictions, recorded before the run

1. **The best stage-1 cell is up in both knobs**, i.e. not on either axis. If
   the best cell is on an axis, the interaction hypothesis is wrong and the two
   single sweeps already answered the question.
2. **At least one cell beats both single-knob best arms** (P53's B4 at −0.060 /
   −0.103 and P54's C4 at −0.167 / +0.120). If none does, there is no diagonal
   to find and this whole line closes.
3. **Nothing clears the bar at stage 2.** Fifty-four registrations, one shipped
   change. What is different is only that the search space is two-dimensional for
   the first time; that is a reason to look, not a reason to expect.
4. **The ask hit rate falls in the good cells.** Three separate results now say
   hit rate is anti-correlated with margin here — P53's monotone sweep, P54's C4
   having the lowest rate of its four, and the champion sitting below the flattened
   arms. A good cell with a *rising* hit rate would contradict all three and
   should be treated as a harness fault until explained.

## The bar and the withdrawal conditions

Unchanged: **+0.15 sets/game with the interval clear of zero against SESTINA at
`BRIDGE_REV 3` AND in self-play**, paired within deal, cluster bootstrap over
deals. Stage 2 is 300 deals × 2 parities.

A cell is **withdrawn** if either population's stage-2 interval lies entirely
below zero. One population only is **opponent-specific and does not ship**.

Harness conditions: any arm whose `weights.suit` or `weights.scarce` does not
equal its registered cell at run time — the runner asserts both, and also that
the champion still reads (0.06, 0.20), because every dose here is defined
relative to that. `scripts4/arm_overlap.py` on both stages.
