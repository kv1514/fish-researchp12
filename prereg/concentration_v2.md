# Pre-registration: the one term in the basis that points at the error we actually make

Written before any game of this program is played, and before the runner
exists. Every input below is a figure this project already holds.

## The error we actually make

Over 10,000 games against v0.7 (`results/margin_decomposition.json`):

| | per game |
|---|---|
| our wrong declarations | 0.1759 |
| ... of which **allocation** class: our own team held all six and we named the wrong split | **0.1676** |
| ... of which ownership class: an opponent still held one | 0.0083 |

**95.3% of what we get wrong is the split, not the reading.** We essentially
never claim a half-suit an opponent still holds. What we cannot do is say which
of our own teammates has what --- and once our team holds all six,
`GameState.legal_asks` bars every opponent from asking there, so no public
event can ever inform it again. The split is frozen at the moment the last card
arrives, and every misplaced card in the disclosure probe was one that had
never moved in public (398 of 398, `results/margin_decomposition.json`).

A half-suit held entirely in one hand has no split to name. Concentration is
the only term in the ask basis that points at this.

## What the term does now, and why its one screen said nothing

`concent` exists. It is weighted $0.0$ in the champion and was screened once:
**$0.15$, 160 pairs, $-0.037$ $[-0.653, +0.578]$** (paper, the
everything-else-we-tried table). Two independent reasons that run could not
have found anything.

**It was the wrong quantity.** v1 was `ctx.team_concentration[hs]`, one number
per half-suit, identical for every candidate ask in it and independent of the
target and of who would end up holding the card. A term with the same value on
every ask in a half-suit cannot express a preference *between* asks. Worse, its
sign is backwards in the case the term exists for: when the concentration sits
with a **teammate**, my taking a card breaks it up, and v1 scored that ask
highest precisely because the half-suit was concentrated. This is the same
defect `claim` carried at v1 and gets the same remedy --- corrected in place,
`TERM_VERSIONS["concent"]` bumped to 2, so `stale_terms()` flags every harvest
fitted against the old column.

**And the weight was inert.** Measured over 596 decisions with a real choice
and 30,065 candidate asks (`scripts4/concent_scale.py`,
`results/concent_scale.json`), the corrected feature has median magnitude
$0.0299$ and a median within-decision spread of $0.0677$. At the screened
weight of $0.15$ it changes which ask is taken on **1.7%** of decisions:

| weight | decisions whose pick changes |
|---|---|
| 0.05 | 0.3% |
| 0.15 | **1.7%** |
| 0.30 | 3.2% |
| 0.60 | 4.5% |
| 1.00 | 8.1% |
| 2.00 | 13.9% |

A 160-pair run of a knob acting on one decision in sixty, reporting an interval
four times the ship bar in each direction, is a statement about the harness.

## Arms

- **A** = `V06_DEPLOYED` (which as of 2026-08-28 carries
  `claim_forced_exhaustive=1`).
- **B** = A + `w_concent = 0.60`. Chosen because it equals `w_turn`, the
  largest weight in the existing basis, so it is "the same order as the biggest
  term we already trust" rather than a number picked to win. Changes 4.5% of
  picks.
- **C** = A + `w_concent = 1.50`. The dose rung, at 11% or so of picks.

$0.15$ is deliberately **not** an arm. It is now known to be inert and
re-running it would only reproduce a null that means nothing.

## Design and size, fixed now

Duplicate-deal paired, both seat parities, fresh seed block, award rule pinned,
opponent `dylan_v07` at `BRIDGE_REV = 2`. **4,000 games per arm.**

The size is not a guess. `scripts4/pairing_value.py` established that a paired
run's precision is governed by how often its knob changes a decision: a knob
firing on $0.9\%$ of games gets $414\times$ from pairing, one firing on most
decisions gets $1.1\times$. This knob flips several picks per game, so pairing
will remove essentially nothing and the paired sd will sit near the unpaired
one, about $2.75$. At 4,000 games that is a standard error near $0.044$ and a
95% interval of about $\pm 0.086$ --- enough to separate an effect at the
$0.15$ bar from zero, which is what a first screen has to do. Analysed once, at
the end. No interim looks.

## Primary outcome, fixed now

Paired difference of set margins against v0.7, B minus A.

## Secondary outcomes, fixed now

1. **Wrong declarations per game, split by class.** Allocation and ownership
   reported apart, because the whole argument is about the first.
2. **The concentration actually achieved.** `scripts4/declarer_holding.py`
   already records, for every declaration of a wholly-held half-suit, the
   declarer's own cards of it and the largest holding on the team. The arm must
   move that distribution or the term did not do what it is named for.
3. The declaration path ledger per arm.
4. Ask hit rate, asks and turns per game --- concentration is bought by
   choosing worse asks by success probability, so the price should be visible.

## Ship bar

Point estimate $\geq +0.15$ **and** interval lower bound $> 0$. Stated in both
halves explicitly, and the runner will print both this reading and the stricter
whole-interval-above-the-bar reading, because
`prereg/tempo_regime.md` ran into exactly this ambiguity between its document
and its code and the fix is to say which is which in advance. **Here the
document governs**, and the stricter reading is reported alongside.

## Withdrawal conditions, fixed now

1. **Allocation errors do not fall.** This is the mechanism, and it is a
   withdrawal condition rather than a secondary: if the margin rises while
   allocation errors are flat, the term is being paid for something other than
   the reason it was reinstated, and shipping it would put the wrong
   explanation in the paper. Report and withdraw.
2. **Concentration at declaration time does not rise.** Same argument one level
   further down. If the arm does not concentrate holdings, the feature is not
   doing what its formula says and the defect is in the implementation, not
   the idea.
3. **C is worse than B beyond noise.** More of a good thing being worse means
   the story is wrong; report and withdraw rather than tuning the weight to
   whatever wins.
4. **Ask hit rate falls without the margin rising.** Buying concentration with
   worse asks and getting nothing for it.

## Expected outcome, written down in advance

I expect a small positive that does not clear the bar, and I expect the
mechanism check to pass --- allocation errors falling by something like 0.01 to
0.02 a game. At the measured $+1.7898$ sets an avoided error
(`results/error_value.json`) that is $+0.018$ to $+0.036$ sets, well under
$0.15$, and the tempo cost of choosing worse asks would eat into even that.

If that is what happens, the useful output is not the null. It is the first
measurement of what concentration is worth per unit, which is the number a
learned objective would need and which no fit has ever had, because every
harvest in the repository was taken against the v1 column.

The way this could surprise me: a wholly-held half-suit in ONE hand is
declarable with certainty rather than merely more cheaply, so the payoff in
allocation errors may be convex in concentration rather than linear. If it is,
C should beat B by more than the dose ratio, and that --- not the margin --- is
the signature to look for.
