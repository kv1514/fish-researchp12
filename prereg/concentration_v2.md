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
ask can ever NAME one of those cards again (public hand counts still constrain it). The split is frozen to direct evidence at the moment the last card
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

---

# Outcome: withdrawn on condition 1, and the theory is wrong rather than weak

Run 2026-08-28, `scripts4/concent_confirm.py 2000 3`, 4,000 games per arm on
identical deals, both parities, `BRIDGE_REV = 2`, zero fallbacks, zero
unfinished. `results/concent_confirm.json`.

| arm | margin | vs A |
|---|---|---|
| A `w_concent` 0 | +2.4405 | — |
| B `w_concent` 0.60 | +2.3975 | $-0.0430$ $[-0.1369, +0.0509]$ |
| C `w_concent` 1.50 | +2.2960 | $-0.1445$ $[-0.2490, -0.0400]$ |

## Withdrawal condition 1 fires

| arm | allocation/game | ownership/game | mean best share |
|---|---|---|---|
| A | **0.1557** | 0.0077 | 0.8106 |
| B | **0.1772** | 0.0073 | 0.8115 |
| C | **0.1827** | 0.0067 | 0.8168 |

Allocation errors were required to fall. They **rose**, monotonically in the
weight. **Withdrawn.**

Condition 2 is satisfied and it is the least interesting thing here:
concentration at declaration time did rise, $0.8106 \to 0.8168$. So the feature
computes what it says it computes, and the theory attached to it is wrong. That
is a better outcome than a null — a null would have left the idea alive.

## Why it fails, which is the opposite of the argument for it

The path ledger, per game:

| arm | exact | voluntary | gate | **forced** | wrong/game |
|---|---|---|---|---|---|
| A | 0.793 | 3.751 | 0.312 | **0.167** | 0.1635 |
| B | 0.795 | 3.702 | 0.313 | **0.197** | 0.1845 |
| C | 0.813 | 3.652 | 0.305 | **0.218** | 0.1895 |

Forced declarations rise monotonically with the weight, by $30\%$ from A to C,
and the forced path is $47$–$49\%$ wrong. That is where the extra allocation
errors come from.

The mechanism is visible once stated, and it is exactly the resource the
argument for the term ignored. `GameState.legal_asks` requires the asker to
**hold a card of the half-suit**. Concentrating a team's holding into one hand
therefore narrows the set of half-suits that hand can ask in — and being unable
to ask is the definition of being forced. The term buys a marginally better
split and pays for it in the one currency that keeps a seat able to act at all.

Stated as consistent-with rather than proven: this run does not instrument the
count of askable half-suits per seat, so the chain from concentration to
narrowed options to forced declarations is inferred from the ledger's shape.
The dose response is monotone in the harm, which is the strongest evidence
available here.

## Against the registered expectation

The registration predicted "a small positive that does not clear the bar" and
"the mechanism check to pass — allocation errors falling by something like 0.01
to 0.02 a game". Both halves are wrong: the effect is negative and allocation
errors rose by $0.02$ to $0.03$ instead.

It also named the way it could be surprised: if the payoff were convex in
concentration, C would beat B by more than the dose ratio. C is *worse* than B,
monotone in the wrong direction, so the surprise arrived from the other side.

## What survives

The v1 formula really was broken and the v2 correction really does compute the
change rather than the level — `tests4/test_concent_v2.py` pins that
independently of any of this. What is refuted is the strategic claim that
concentrating a team's holding is worth anything, and it is refuted for a
concrete reason rather than for want of power.

`w_concent` stays at $0$ and the term should be regarded as understood rather
than untested. The next person to notice that $95\%$ of our errors are
allocation class and reach for this feature now has a measured answer.
