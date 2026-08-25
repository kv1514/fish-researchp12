# Pre-registration: never throw the turn away when you do not have to

Written 2026-08-25, before any pair of this arm has been played.

## The decision this changes

`agent4.act` scores every legal ask and plays the highest-scoring one. The
score carries P(success) at weight 1.0 alongside depth, turn-risk, scarcity and
exposure terms, so an ask with **zero** probability of landing can outrank one
with a real chance. When that happens the agent surrenders the turn for
certain.

Measured over 15,542 decisions in 150 games
(`results/doomed_ask_diag.json`), with the champion's own posterior and its own
weights:

| | count | share |
|---|---|---|
| decisions | 15,542 | |
| top-scoring ask has p = 0 | 575 | 3.7% |
| ...and the claim branch declines, so a doomed ask is played | 269 | 1.7% |
| ...and another ask COULD have landed | **229** | **1.5%** |

On those 229 the best available success probability has median **0.385** and
mean 0.382; 31 of them had an ask at p ≥ 0.5 available. So one and a half
percent of all decisions give up the turn with certainty when a
better-than-one-in-three chance of keeping it was on the table.

`avoid_doomed_asks` restricts the choice to asks that can land and ranks them
by the same objective. The claim gate above it still sees the unfiltered order,
so claiming behaviour is bit-identical and this ablates exactly one idea.

## Why it might well lose

The objective ranked the doomed ask top *for reasons*, and one of them is real.
Under the no-bluff rule a failed ask publicly proves the asker holds another
card of that set, which is exactly the fact a partner needs to place a split.
The paper already measures the shape of this: a half-suit that is provably ours
but unplaceable is nulled 17.5% of the time against 2.8% otherwise, and such
half-suits are 27% of all nulls. `signal_mode` exists to make that trade
deliberately and is shipped **off**.

So the champion may be signalling by accident, and this arm would stop it. The
session's other structural finding cuts the same way: under the no-bluff rule
signal is welded to move, so deception costs what it buys. This is a
hypothesis, and I am recording before the run that I do not know the sign.

## Design

- Six blocks of 1,000 duplicate deal-pairs, `base_seed` 64,000,000 upward,
  disjoint from every seed in `results/v04_duels.jsonl`.
- Challenger: `fishbot4 {opponent_gamma: 0.35, avoid_doomed_asks: true}`.
- Champion: `fishbot4 {opponent_gamma: 0.35}`.
- Pooling: fixed effect across the six blocks. Cochran's Q reported as a
  diagnostic and not as a gate.

### Sizing

At the per-pair sd of 3.796 measured in the A/A pool, 6,000 pairs gives an
**MDE of about 0.137** at 80% power. This is the same size as the
gamma_schedule settle, chosen for the same reason: it is what this project can
afford to run twice if it has to.

There is no screen to decay from. This arm was never selected out of a batch
for looking good -- the diagnostic that motivated it measured a frequency
(1.5% of decisions) and a mechanism, not an effect size, and no version of this
arm has ever been played. That removes the winner's curse that took
`value_keep` from +0.320 to −2.884 and flipped `gamma_schedule`'s sign, and it
also removes any excuse for a favourable prior.

## Outcomes, fixed in advance

- **Interval entirely above +0.05** — adopt. Turn preservation beats accidental
  signalling, and the next question is whether deliberate signalling
  (`signal_mode`) beats both, which is a separate pre-registered run.
- **Interval entirely below −0.05** — the doomed asks were doing work. That is
  the more interesting outcome and it makes `signal_mode` the immediate next
  arm, because it would mean the accidental version is worth something and the
  deliberate one has never been given a fair test.
- **Interval containing zero** — not resolved. Reported as a failure to
  resolve, with the pairs needed to settle it stated, and NOT quietly kept.

## The prediction, recorded so it can be wrong

I predict **+0.05 to +0.15**, i.e. positive but possibly not clearing the bar.
Reasoning: 229 firings in 150 games is 1.53 per game, each converting a certain
turn loss into a 0.385 chance of keeping it, so about 0.59 retained turns per
game. Set against that, some of those asks were buying information the partner
used. I am more confident of the sign than of the size, and the honest summary
is that a null result would not surprise me.

Three of my last three pre-data predictions in this project have missed —
value_keep by 0.167, gamma_schedule by the sign, and the COMBINED block-0
replay outright. This one is recorded in the same spirit.
