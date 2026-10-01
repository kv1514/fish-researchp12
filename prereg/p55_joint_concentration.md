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

---

## OUTCOME, `results/p55_joint_stage1.json` — a null, and P55 ends at stage 1

4,800 games on block 17,900,000, 100 deals × 2 parities per cell, zero
fallbacks, zero unfinished, dose check passed at run time.

| `w_suit` | `w_scarce` | vs SESTINA | self-play | hit rate |
|---:|---:|---|---|---:|
| 0.06 | 0.40 | **+0.1300** [−0.322, +0.582] | −0.0900 [−0.429, +0.249] | 0.5033 |
| 0.06 | 0.80 | +0.0700 [−0.407, +0.547] | −0.3600 [−0.740, +0.020] | 0.4663 |
| 0.12 | 0.20 | −0.2500 [−0.643, +0.143] | −0.2400 [−0.612, +0.132] | 0.5087 |
| 0.12 | 0.40 | −0.0400 [−0.566, +0.486] | −0.2100 [−0.615, +0.195] | 0.4958 |
| 0.12 | 0.80 | −0.0800 [−0.575, +0.415] | −0.2400 [−0.615, +0.135] | 0.4547 |
| 0.24 | 0.20 | −0.1700 [−0.626, +0.286] | −0.2900 [−0.718, +0.138] | 0.5050 |
| 0.24 | 0.40 | −0.2900 [−0.761, +0.181] | −0.4300 [−0.839, −0.021] | 0.4774 |
| 0.24 | 0.80 | −0.3400 [−0.836, +0.156] | −0.4100 [−0.779, −0.041] | 0.4509 |

**Every cell is negative in self-play. Not one has both point estimates ≥ 0, so
the advance rule admits nothing and P55 ends here** — as registered: *"If no cell
passes the stage-1 rule, P55 ends there and reports a null. It does not get
re-scoped into a finer grid."* There is no stage 2.

### Prediction 1 failed, which refutes the interaction hypothesis

> *"The best stage-1 cell is up in both knobs, i.e. not on either axis. If the
> best cell is on an axis, the interaction hypothesis is wrong and the two single
> sweeps already answered the question."*

The two best cells by SESTINA margin — **+0.1300** and +0.0700 — are both at
`w_suit = 0.06`, the shipped value. They sit **on the `w_scarce` axis**. So there
is no diagonal, and P53 and P54 had already answered this.

Worse for the hypothesis: raising `w_suit` is bad at *every* `w_scarce`. The
`0.24` row is the worst row and the `0.06` row the best, monotonically. The grid
is not interacting; it is close to separable, and the shipped `w_suit` is simply
right.

### Prediction 2 failed

No cell beats both single-knob best arms. P54's C4 was −0.167 / **+0.120**; the
best cell here is +0.130 / **−0.090** — better against SESTINA, worse in
self-play. The sign flips between populations *and* between blocks for what is
nominally the same region of the space, which is what noise around zero looks
like rather than a signal.

### Prediction 4 held, and sharpened

**Every one of the eight cells has a lower hit rate than the champion**
(0.4509–0.5087 against 0.5169), and the rate falls monotonically as `w_scarce`
rises. So the anti-correlation between hit rate and margin is not global: hit
rate falls in *both* directions away from the shipped cell, while margin is
maximal near it. The champion sits near a margin optimum that is **not** a hit
rate optimum, which is the sharpest statement of that relationship this project
has.

### What P53, P54 and P55 establish together

**19,200 duel games** across two single-axis sweeps and one 3×3 grid, both signs
on both knobs: **the ask objective's concentration parameters are at a joint
optimum, not merely a coordinate one.** The interaction I inferred from three
monotonicity failures is not there — the grid is nearly separable. Those
failures have some other cause, and finding it is not the same as finding a
better cell.
