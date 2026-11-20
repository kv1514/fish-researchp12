# Pre-registration: refuse a declaration no complete deal allows

Written 2026-08-25, before the arm exists and before any pair is played.

## The error, and why it is provable

`fish/engine.py::_apply_claim` awards NULL only when the whole half-suit sits
with the claiming team and the declared split is wrong. `claim4`'s own
docstring names the failure that produces one:

> the product of marginals is not the joint: cards compete for the same quota
> slots, so per-card modes can be jointly impossible

Measured over 120 games and 1,080 claims (`results/impossible_claims.json`):

| | count | scored |
|---|---|---|
| declaration puts a card outside its own holder mask | **0 / 1080** | — |
| declaration matches no complete consistent deal (m=1) | **11 / 120 = 9.2%** | won 0, nulled 11, **+0.000 sets/claim** |
| all other claims | 1069 | won 1038, nulled 28, foe 3, **+0.968 sets/claim** |

The zero on the first line matters as much as the 9.2%. No individual card is
misplaced; it is the joint that fails. Eleven of the thirty-nine nulls in that
sample — 28% — could not have been right, and the exact constraint system knew
it at the moment the sampled posterior was asked instead.

## The arm

`claim_feasibility`: before returning a declaration, test it with
`fish4.feasible.declaration_feasible` — a max-flow feasibility over the live
cards, exact and general, cross-checked 40/40 against brute-force enumeration
at m=1 where enumeration is available. If the declaration is infeasible, take
the best feasible candidate instead; if none is feasible, do not claim.

The filter can only ever remove declarations that **cannot win**. It cannot
reject a correct claim, which is the property the test in
`tests4/test_feasible.py` exists to hold.

## Sizing, honestly

0.092 impossible claims per game. Each costs the 1 differential between a null
and a correct claim, so the ceiling is **+0.183 per deal-pair** — and only if
the substituted split is right. Possible claims are right 97% of the time, but
these are exactly the positions where the posterior was confused enough to pick
an impossible split, so the substitute is likely less reliable than a typical
claim and the realistic effect is below the ceiling.

Six blocks of 1,000 pairs at `base_seed` 74,000,000 upward gives an MDE of
about **0.137** at the A/A per-pair sd of 3.796. If the true effect is near the
ceiling this resolves; if it is a third of the ceiling it will not, and that is
stated here rather than discovered later.

**Coverage limit.** The 9.2% is measured at m=1, where the enumeration needed to
detect it is cheap. The rate at higher layers is **unmeasured**. The arm applies
the feasibility filter at every layer, so if impossible claims also occur above
m=1 the effect will exceed what this sizing assumes — and if they do not, it
will fall short. Nothing here assumes the rate carries.

## Outcomes, fixed in advance

- **Interval entirely above +0.05** — adopt. A provable error was costing
  measurable sets.
- **Interval entirely below −0.05** — the filter is harmful, which would mean
  the substituted claims are worse than the impossible ones they replace. Since
  an impossible claim scores exactly 0 and a wrong-but-feasible claim can score
  −1 by handing the half-suit to the opponents, this is possible and is the
  outcome I would learn most from.
- **Interval containing zero** — not resolved. The pairs needed to settle get
  stated, and the arm is not quietly kept.

## The prediction, recorded so it can be wrong

**+0.03 to +0.10.** Below the +0.183 ceiling because the substitute is drawn
from the same confused posterior, and possibly below the +0.05 bar. I expect
the sign to be positive and the size not to clear adoption.

Five pre-data predictions have missed this session: value_keep by 0.167,
gamma_schedule by the sign, the COMBINED block-0 replay outright,
avoid_doomed_asks by its whole range, and the m=1 disagreement shape (I said
same-target/different-card from a four-decision smoke; at scale it was 49/12/35
across three categories). This one is recorded in the same spirit.

---

## AMENDMENT, 2026-08-25: the coverage gap, closed after the run

The pre-registration above said the 9.2% was measured at m=1 and that the rate
at higher layers was **unmeasured**, while the arm applied everywhere. The
max-flow check built for the arm answers that at every layer, so it was
measured rather than left open:

| | claims | jointly impossible |
|---|---|---|
| m = 1 | 60 | **7 (11.7%)** |
| m = 2 … 9 | 480 | **0** |

**Impossible claims happen only at m=1.** That is structural rather than
lucky: at m=1 the hand counts are tight — six live cards and exact hand sizes,
so a declaration that mis-splits them is detectably infeasible — while at m≥2
there are enough live cards and enough slack in the counts that almost any
team-only declaration fits some deal.

So the +0.183 ceiling was computed from the right rate after all, and the arm's
+0.028 is not explained by missing opportunity at higher layers. It is
explained by the other half of the sizing, which the pre-registration stated:
the substituted split comes from the same confused posterior, so repairing an
impossible claim converts it to a *feasible* one that is often still wrong.
Measured in the smoke: five impossible claims repaired, two became wins.

Nothing about the verdict changes. Recorded because a pre-registration that
names a gap and never closes it is a pre-registration that got the benefit of
the doubt for free.
