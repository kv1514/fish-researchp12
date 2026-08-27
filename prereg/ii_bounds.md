# Pre-registration: bounding the m = 2 positions the solver cannot reach

Written before the 60-game run. A pilot has been seen; what it showed and how
that constrains this document is in **Pilot** below.

## The claim under test

`paper/fishbot_v04.tex`, section "Both gains are lower bounds", says the
reported exact gain at m = 2 -- **+0.3250 over 109 solved positions** -- is a
lower bound on the gain over the whole layer, because the positions the solver
cannot reach are the wide-support ones and the gain rises with support.

That argument is a slope fitted over supports 2-24, extrapolated across a gap
that runs to 60,480 deals. It is an argument. This replaces it with two
quantities that hold by construction on every position, reachable or not.

## The two bounds

For a position with belief support {d} and weights {w_d}, champion value C:

* **Upper.** `U = sum_d w_d V_PI(d)`, where `V_PI(d)` is `ExactII` solving the
  single deal d. Perfect information is a relaxation -- an imperfect-information
  policy is one the relaxation may also play -- so `V_II <= U`.
* **Lower.** `L = max_a sum_d w_d champion_value(d after a)` over root actions
  legal in every deal. Any single policy is attainable, so `V_II >= L`. The
  champion's own root action is evaluated first, so `L >= C` always.

Both are computed by `scripts4/ii_bound_unsolved.py` at fingerprint recorded in
`results/ii_bound_journal.jsonl`.

## What each outcome means, decided in advance

Let `Lbar` and `Ubar` be the mean lower and upper bounds on the gain over the
positions this run does **not** solve exactly, and `H = +0.3250`.

1. **`Ubar <= H`** -- the claim is **refuted**. The unsolved positions cannot
   average more than `Ubar`, so the whole-layer mean is below the reported one
   and the reported figure is an upper bound, not a lower one. The paragraph
   comes out and says so.
2. **`Lbar > H`** -- the claim **holds by attainment**. A policy achieving
   `Lbar` exists and is exhibited, so no trend, no slope and no extrapolation
   is needed. The paragraph is rewritten to lead with the bound and to keep the
   slope only as corroboration.
3. **`Lbar <= H < Ubar`** -- **not settled**. The bounds are real but too loose
   to decide. The paragraph keeps its current caveat and gains a sentence
   saying the interval was computed and straddles the figure.

Outcome 2 is the one the pilot points at. It is written here so that if the
full run lands in 3 instead, the write-up cannot quietly become "the bounds are
consistent with the claim".

## The control, and what fails the run

Every position at support <= 12 is also solved exactly **in the same run, on
the same state object** -- not joined to `results/ii_endgame_m2.json`, whose
rows are keyed by game alone with several per game, so lining them up would be
a guess. The exact gain must satisfy `L <= V <= U`.

The run refuses to write a result if any of these happen:

* an exact value falls outside its own bounds (a bound that excludes the truth
  is not a bound);
* any `L > U`;
* any `L < C`, which cannot happen because the champion's move is a candidate;
* no position was solved exactly at all, leaving the instrument unchecked.

## What is assumed, stated because it is now load-bearing

`_claim_candidates` offers only declarations true in some candidate deal, on
the argument that a false declaration scores -1 for that half-suit, the least
it can score, and so is weakly dominated. The **lower** bound does not need
this -- dropping actions only lowers `L`. The **upper** bound does: if a
genuinely optimal move were excluded, `V_PI(d)` would understate the relaxation
and `U` would stop bounding. The assumption was previously a speedup; it is now
load-bearing for a bound.

## Budgets, and which direction they err

Per position: 400,000 nodes / 90 s for the upper stage, 120 s for the lower.
Both fail **towards a looser interval, never towards a wrong one** -- a deal
the upper stage cannot solve takes the trivial `_upper` bound, and an action
the lower stage does not reach is simply not in the max. Positions where either
budget bit are counted and reported, so a wide interval is never read as a
statement about the game when it is a statement about the clock.

Positions with support above 400 are counted as `too_wide` and excluded. That
is a coverage limit and will be reported as one.

## Pilot

Twelve positions over three games were run before this was written, and the
lower bounds on the three widest -- supports 36, 40 and 18 -- came back at
**+0.611, +0.425 and +0.556**, all above H. Six narrow positions were also
solved exactly and every exact value fell inside its bounds.

That is why outcome 2 is anticipated above, and it is disclosed rather than
presented as a prediction. The pilot rows were discarded: the script's
fingerprint changed when the lower-bound budget was added, so they are not
reused, and the full run recomputes them.

## Amendments

None yet. Any change to the bounds, budgets or decision rule after the run
starts gets appended here with its reason, before the numbers are read.
