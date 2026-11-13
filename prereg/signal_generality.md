# Is signalling a property of the convention, or an exploit of one opponent?

Registered 2026-08-31, **before any pair of the 12,100,000 bank is played**.
The arms, the opponents, the seed base, the sample size, the primary contrast,
the verdicts and the power limits are fixed here and chosen nowhere else.

## What is at issue

Every margin this project reports is against `dylan_v07`. The signalling
mechanism's value, +0.1435 sets a game, is now understood: by the identity in
`scripts4/margin_identity.py` it is almost entirely an **opponent-error**
intervention. Against `dylan_v07` it moves their declaration error rate from
21.87% to 24.37%, and 83% of the +0.2400 theirs channel is that rate change
rather than a change in how often they declare.

That leaves the question the measurement cannot answer from one opponent: is
the mechanism confusing *a reader of the public record*, or is it exploiting
one particular declaration policy? A convention that only works against the
one engine we test against is not a finding about Fish.

## Opponents

Two, chosen **from `results/opponent_error_screen.json`, after it ran**. The
first grid written into the code was `("probabilistic", "memory", "self")`,
picked before the screen existed; the screen refuted it, and this document
records the replacement rather than the original.

The screen's relevant columns, over 60 deals x 2 parities each:

| opponent | declaration error | declares/game | theirs headroom |
|---|---|---|---|
| `dylan_v07` | 21.78% | 4.02 | 6.28 |
| `heuristic` | 72.51% | 1.09 | 0.60 |
| `ev_claim` | 10.76% | 3.72 | 6.63 |
| `probabilistic`, `tuned` | 6.73% | 3.59 | 6.70 |
| `search` | 6.69% | 2.87 | 5.35 |
| `paired_search` | 6.19% | 3.63 | 6.82 |
| `memory` | 4.45% | 3.18 | 6.08 |
| `self` | 3.33% | 4.50 | 8.70 |
| `value_search` | 3.07% | 3.53 | 6.83 |

`ev_claim` is the only other honest opponent with error volume for the
mechanism to move. `heuristic` errs far more often but declares a quarter as
much, so its whole theirs channel is 0.60 sets against `dylan_v07`'s 6.28 and
it cannot carry the effect whatever the rate does. Everything else sits in a
3-7% band that is the floor, not a target.

`oracle` and `oracle_gated` are barred by name in the instrument. They read
hidden state; nothing played against them is a strength figure.

## Arms

Two, each played once per deal on the **identical** deal, one invocation per
opponent with `--vs=`.

| arm | parameters |
|---|---|
| `A_shipped` | `{}` — the champion, and the identity's base |
| `B_signal` | `signal_mode="stuck"`, `signal_max_p=0.50` — the incumbent |

The deals are **shared across opponents on purpose**: the three readings
(including the published `dylan_v07` one) then differ by the opponent and by
nothing else.

## Sample and seeds

800 deals x 2 parities = 1,600 games an arm, 3,200 games per opponent. Seed
base **12,100,000**, barred from 2,400,000, 3,600,000, 9,300,000, 9,700,000,
9,900,000, 10,100,000, 10,500,000, 10,900,000, 11,300,000 and 11,700,000.
Agent seed base 121,000. Clustered on the deal, t at k-1 df, k = 800.

## Power, stated before the run and not flattering

The published effect is +0.1435 +-0.0464 on 2,000 deals. At 800 deals the
half-width projects to **+-0.0734**.

Take the mechanism's measured behaviour against `dylan_v07` — a rate increase
by a factor of 1.114 — and apply it to each opponent's own baseline. That is
what "the mechanism generalises fully" predicts:

| opponent | rate move | margin effect | z against +-0.0734 |
|---|---|---|---|
| `dylan_v07` | +2.49pp | +0.2000 | 5.34 |
| `ev_claim` | +1.23pp | +0.0914 | 2.44 |
| `self` | +0.38pp | +0.0343 | 0.92 |

So, said in advance:

**`ev_claim` is the test.** A full-strength generalisation clears zero on the
margin at z = 2.4, and its rate move of +1.23pp is comfortably outside the
+-0.79pp Wilson interval that 5,947 declarations give. This opponent can
answer the question.

**`self` cannot answer it, and is not asked to.** Its 3.33% error rate is in
the same floor band the screen was built to catch. A full-strength
generalisation would move it +0.38pp, which is *inside* the +-0.41pp interval
1,600 games buy, and would be worth +0.0343 sets against a half-width of
0.0734. **A null against `self` is predicted here, in advance, by arithmetic
rather than by the run, and will not be reported as evidence about
generality.** No sample size this project can afford changes that: resolving
+0.0343 on the margin needs about 3,800 deals.

## What `self` is for

A control that can refute rather than confirm. The identity says this margin
is bought out of the opponent's declaration errors. Against `self` there are
almost none to buy: at most +0.0343 sets of movement exists. **If `B_signal`
beats `A_shipped` against `self` by more than the +-0.0734 half-width, the
margin is coming from somewhere the identity does not account for, and the
reading of the mechanism in this paper is wrong.** That is the one outcome
here that would change a published claim.

## Verdicts, fixed now

Read on `ev_claim` unless stated otherwise.

- **GENERAL** — the margin effect clears zero and the declaration error rate
  rises outside its Wilson interval. Signalling is a property of the
  convention. It still does not enter `V06_DEPLOYED`; the deployed opponent
  is `dylan_v07` and this run does not re-price that.
- **DYLAN-SPECIFIC** — the margin effect covers zero *and* the rate does not
  rise outside its interval, with a half-width at or below 0.0734. The
  mechanism is an exploit of one declaration policy, and the paper's
  signalling section acquires that limit.
- **PARTIAL** — the rate rises but the margin covers zero, or the reverse.
  Reported as partial, with the channel decomposition, and not as either of
  the above.
- **CONTROL VIOLATED** — `self` shows a margin effect clear of zero in either
  direction. This overrides every other reading in this document: the
  identity's account of where the margin lives is refuted and the run becomes
  a diagnosis rather than a generality test.
- **UNDERPOWERED** — the realised half-width exceeds 0.0734 by enough that
  +0.0914 would not have cleared zero. Reported as a failure of the design,
  not as a null.

## Withdrawal conditions

1. **The identity must close** on the counted opponent ledger for every arm
   and opponent, as `scripts4/margin_identity.py::verify` checks it. The rule
   must be `wrong_distribution_outcome="opponent"`; under any other rule the
   `NULL_TEAM` branch is reachable, a half-suit can be awarded by no
   `ClaimEvent`, and the decomposition is not an identity.
2. **`A_shipped` must be bit-identical to the champion** in each opponent's
   run. It is the base of every contrast here.
3. **No unfinished games and no bridge fallbacks.** A substituted move is a
   different policy.

Any of the three failing withdraws the run. Its primary is then not read, and
the file is kept under a `_withdrawn_` name rather than deleted, because a
withdrawn run is where a defect was found.

## What this cannot do

It cannot say the mechanism generalises to *human* declarers, or to any
policy outside this repository's roster. It measures three engines. It also
cannot separate "the convention confuses readers of the public record" from
"the convention confuses this family of readers", because every opponent here
descends from the same codebase. `dylan_v07` is the only independently
written one, and it is the opponent the question is about.
