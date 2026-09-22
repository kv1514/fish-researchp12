# Pre-registration: P50, the contest term at revision 3, and the tally hedge

Written before any P50 game. Two fronts, registered together because they come
from one reading of the opponent's source and must not be quietly re-scoped
into one arm if the other fails.

## Why this is a reopening and not a second look

`03877d9` ported the contest term and rejected it: 4,000 games, five doses
(−1.0, −0.3, +0.3, +1.0, +3.0), every arm negative, monotone in the wrong
direction, **against a baseline margin of +2.732 sets a game.** That baseline
is `BRIDGE_REV 2`. `prereg/kraken_v12_vs_sestina.md` fixes the rule that
governs this: *a knob rejected for failing the bar against a handicapped
opponent has not been tested against this one.* Every figure in that sweep is
a measurement of a game where we were wrongly ahead by 2.7.

Two things are also known now that were not then, and both bear on the sign:

* the deficit is **the contested middle** — at a matched deal we convert worse
  at 4-2, 3-3 and 2-4 and **better** at 6-0, 5-1 and 1-5, and that band is
  80.4% of all half-suits (`results/contest_ledger_12700000.json`);
* SESTINA's shipped spec turns on **exactly one** of its eighteen extra ask
  terms, `oppCertDonate = 25.0`, whose formula is `(1−p)·oppFrac·(uS/6)` —
  the same quantity `fish4/adaptive.py:contest_bonus` computes — and its score
  is maximised, so it *seeks* those asks.

Futility is already excluded and does not need `term_bite`: the rev-2 sweep
moved margins by up to 1.124 sets, so the term has ample bite. What is
untested is its **sign and size against an opponent we are behind**.

## C1 — the contest dose, three arms

`w_contest` on `KRAKEN_V1`, one flag, bit-identical at 0.0.

| arm | weight | the reading it tests |
|---|---:|---|
| C1a | **+0.3** | fight harder in the contested band, their direction, small dose |
| C1b | **+1.0** | the same at the largest dose the rev-2 sweep did not drive to −1.1 |
| C1c | **−0.3** | the off-limits reading: avoid contested half-suits unless the ask is a certain steal (the term vanishes at p = 1, so certain steals are exempt under either sign) |

**Both signs are registered because both are live, and the measurement does
not pick one.** It says we lose the middle. That is consistent with *fight it
better* and equally consistent with *stop fighting it and bank the extremes* —
and the second reading is weaker only because the middle is 80% of the game,
which is an argument and not a result.

## C2 — the tally hedge, two arms

`count_mode` on `KRAKEN_V1`. It is shipped at `"linear"`, which weights the
raw per-half-suit ask tally; `fish4/oppmodel.py`'s own docstring says asks in
one half-suit are plainly not independent and calls `sqrt` and `capped` the
two obvious hedges. **It appears in no registration, no results file and no
line of the paper.** Arms: `sqrt` and `capped`.

Registered here rather than on the strength of the exploit their header
describes, because **that exploit is not live**: `selfTally` and `tallyLie`
are zero in the shipped spec, so this opponent does not inflate tallies at us.
C2 is therefore a test of whether linear over-counting costs anything *by
itself*, and a negative result does not mean the exposure is safe against an
opponent that would use it.

## The bar, unchanged

**+0.15 sets/game with a 95% interval clear of zero against SESTINA v1.0 at
`BRIDGE_REV 3` AND in self-play against the v1.1 champion**, both paired within
deal. An arm clearing one population only is opponent-specific, is reported
prominently as such, and does not ship. Screen at 300 deals × 2 parities on
block **12,900,000** (agent base 129,000); anything clearing re-runs at 600
deals on a fresh block and must clear again. Never pooled.

## Multiplicity

Five arms at 95% is roughly a 23% chance of one false positive, which is why
the confirm stage exists and is not optional. C1 and C2 are scored as separate
families; a C2 arm clearing does not license a C1 arm and vice versa.

## Expected outcome, written down in advance

**That none of the five clears.** For C1: the rev-2 sweep's monotone negative
was measured in the wrong game, but the mechanism it found — the term buys
contest tempo with own ask accuracy — is not obviously re-signed by our being
behind, and four arms in this project have now raised the ask hit rate without
buying a set, which cuts against accuracy being the currency that matters. For
C2: `sqrt` and `capped` throw away information the belief currently uses, and
no opponent at this table is feeding it poison.

The reason to run anyway is that C1 is the only knob this engine exposes that
points at the band the deficit is actually in, and C2 costs two arms to close
a knob that has never been looked at.

## Withdrawal conditions

- Any arm with a non-zero fallback count is void, not adjusted.
- Any arm whose journal rows carry a `BRIDGE_REV` other than 3 is void.
- An arm whose self-play interval lies entirely below zero is dropped
  immediately, whatever it does against SESTINA — the condition that fired on
  P49's N1.
- If C1a and C1b disagree in sign with intervals clear of zero, neither
  advances: a dose response that changes sign inside one family is a defect in
  the term or the harness, not a result.

## Analysis discipline

Paired per deal, intervals clustered on the deal. Every runner pins
`wrong_distribution_outcome="opponent"` and records the engine digest and
`BRIDGE_REV`. No arm is inspected before its block completes.
