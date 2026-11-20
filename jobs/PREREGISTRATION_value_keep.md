# Pre-registration: does crediting the turn rescue the value objective?

Written **before a single pair of the screen had reported**, let alone the
settling run. `results/v04_duels.jsonl` contains no cell whose label matches
`value_keep` at the moment this file is committed, and the commit that adds this
file precedes the commit that adds those cells. That ordering is the only thing
that makes anything below worth reading, so it is stated as a checkable claim
rather than a promise.

## The question

`fish4/hsvalue.py`'s objective scores an ask as the expected change in
`V(H) = P(our team scores H) - P(theirs does)`, in sets. Played pure it loses
**-7.355** sets per duplicate deal-pair against the champion, 95% CI
[-7.875, -6.835] over 200 pairs.

The diagnosis, measured over 3236 real decisions
(`results/value_objective_diag.json`), is that it never credits a successful ask
with **keeping the turn** — and prices losing the turn on the failure side only,
as `turn_weight * (1 - p) * turn_risk`, which is largest exactly where `p` is
smallest. It picks asks whose success probability is **0.0946 ± 0.0043** below
the champion's picks, and deleting its turn term makes its picks *better*.

`keep_value` adds the missing credit as `keep_value * p`. This run asks whether
that is worth anything **in play**, which no sweep over decisions can answer.

## Why a screen first, and what the screen is not

Five values (0.10, 0.20, 0.30, 0.50, 0.80) at 400 pairs,
`jobs/j24_value_keep_screen.json`, fresh seeds from 31 000 000 checked by
`scripts4/check_seeds.py`.

A screen is **selected on**, and this project has already measured what that
costs: a cell chosen from 103 for excluding zero decayed from **+0.035 to
+0.002** when re-run unselected at five times the size, a drop of 2.1 SE. So the
screen's winning number is not an estimate of anything and will not be reported
as one. It selects a value; this run estimates it.

## Selection rule, fixed now

The cell with the **highest point estimate** is carried forward. Ties broken by
the smaller `keep_value` (the weaker intervention).

I am fixing the naive rule deliberately rather than something cleverer, because
a rule invented after seeing five numbers is not a rule. Its cost is a known
upward bias in the screen, which the settling run exists to remove.

## The settling run

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds, base
  **32 000 000** and **32 200 000**, disjoint from the screen and from every
  recorded and queued cell.
- Challenger: `fishbot4` with `objective="value"`, `value_turn=0.15`,
  `value_keep=` the selected value, `hsvalue_path=checkpoints/hsvalue_v1.json`.
- Reference: `V04_CHAMPION`, `fishbot4 {"opponent_gamma": 0.35}`. The same
  reference every other cell in this project is measured against, so the number
  is comparable to all of them.

### Sizing

Per-pair sd taken as the **A/A 3.796**, not from the divergence model. The
divergence model is fitted on arms differing by one knob; these arms differ by a
whole objective and agree on only ~53% of decisions, which is outside anything
it was fitted for. The A/A figure asks for more pairs than needed rather than
fewer.

- MDE at 80% power ≈ **0.238** sets/pair.
- 95% half-width ≈ **0.166**.

## The three quantities, and what each would mean

**1. Recovery.** How much of the -7.355 the credit gives back:

    recovery = estimate - (-7.355)

The baseline is a published interval on disjoint deals, so the two are
independent and the errors add in quadrature. This is the quantity the run is
really about, and it is informative whether or not the estimate crosses zero.

**2. Does it beat the champion?** Adoption requires the 95% interval to lie
**entirely above +0.05**. That threshold is fixed here, before any data, and is
deliberately just above zero: this is a *replacement* for the ask objective, not
an increment on top of it, so "indistinguishable from the champion but built on
a principled objective" is a scientific result and not a reason to ship. A
result inside [0, +0.05] is reported as a tie.

**3. Does it beat what the site plays?** It does not, and this run does not ask.
`V04_COMBINED` is +0.357 over the champion, so a challenger would have to clear
that as well. Adoption on the public table needs a further pre-registered run
against `V04_COMBINED` and will not be inferred by chaining from this one.

## Outcomes, all of them fixed in advance

- **Above +0.05, interval excluding it.** The corrected objective beats the
  champion. The line reopens; the next run is against `V04_COMBINED` and the
  paper gets the result, not before.
- **Inside [0, +0.05], or interval containing +0.05.** A tie. Reported as: the
  omission explained the whole of a seven-set deficit, and the objective is now
  competitive with the incumbent without beating it.
- **Below zero but far above -7.355.** The expected outcome, honestly. The
  diagnosis is confirmed — the missing turn credit was most of the deficit — and
  the objective is still not good enough, which points at the value model
  (held-out corr 0.414) rather than at the objective's shape.
- **Still near -7.355.** The diagnosis is refuted. The turn credit fixes the
  decisions it was measured to fix and does not fix the play, which would mean
  something else dominates and the decision-level diagnostic was measuring a
  symptom.

Note which way the expectation points. I am recording **"below zero"** as the
most likely single outcome before running it, because the value model is weak
independently of the objective's shape, and because a term this large moving the
result all the way across zero would be surprising. If it does clear zero, that
is the surprising outcome and it earns a replication on fresh seeds before it
earns a paragraph.

## What is not being decided here

Nothing about the public table. `api/_engine.py` keeps `V04_COMBINED` regardless
of this result, and the default `value_keep` stays 0.0, so the champion and
every published cell are untouched.
