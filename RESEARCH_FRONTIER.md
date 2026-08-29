# Where the strength actually is, and three ways nobody has tried

Written 2026-08-29, after two v1.1 directions were taken to pre-registered
conclusions and a third was measured. This is the map, not a plan.

## The one fact everything now points at

Perfect card-reading is worth **+6.61 sets/game** over the honest engine, and
the teammate half of that (**+3.41**) is more than twice the opponent half
(**+1.31**) at the same number of cards revealed. Meanwhile **95.3%** of the
engine's residual errors are *allocation* errors — our team held all six cards
of a half-suit and named the wrong split — and **every single misdeclaration
comes from a compelled declaration**: voluntary and exact-solver declarations
are perfect over 14,678 of them, while the gate path is 16.3% wrong and the
forced path 42.7% wrong.

So the engine does not have a card-reading problem with its opponents. It has a
**distributed-knowledge problem inside its own team**, and it only pays for it
when something forces it to answer.

## Why the last three attempts did not move it

| attempt | result |
|---|---|
| `gamma_team` — believe the teammate model harder | **refuted**; better NLL, worse top-1 |
| `unlocated_now` — give that model a better covariate | +3,143 nats on the fit; build licensed, not yet measured in a belief |
| declarer-holding lever — let the best-informed teammate declare | refuted; the covariate was a confound |

All three attack the **inference**: squeeze more out of the asks that happen.
None attacks the **channel**: how much the asks carry in the first place.

## Direction 1 — the card choice is an unused communication channel

**This is the new one, and it is measured.** Literature forbids communication
during play; it does not forbid agreement before it. The rules force an asker to
name a *specific card*, and within the chosen half-suit that choice is currently
made on expected value alone.

Measured over **3,883 asks in 40 self-play games** at the champion
(`scripts4/convention_cost.py`, `results/convention_cost.json`):

* an ask offers a mean of **3.57 legal cards** to choose between — **1.72 bits**
* spending *all* of it (naming a card at random) costs **0.131** probability of
  success per ask
* the engine currently spends **all** of those bits on expected value and
  **none** on telling its partner anything

**And most of the channel is free.** The cost of using it is wildly skewed:
median **+0.022** when the convention card differs from the chosen one, but p90
**+0.616**. Split the asks by how far apart the best and worst legal card are:

| best-to-worst spread | share of asks | bits each |
|---|---|---|
| ≤ 0.01 | 16.2% | 0.91 |
| ≤ 0.02 | 19.7% | 1.01 |
| ≤ 0.05 | 31.4% | 1.25 |
| ≤ 0.10 | 44.7% | 1.41 |

At a spread of 0.02 — where naming any legal card costs under two percentage
points of success probability — there are **19.3 bits per game** going spare.
Locating one card among six players is about 2.6 bits, so that is roughly
**seven cards' worth of free location information per game**, in a game whose
defining constraint is that teammates may not communicate.

Compare the channel the engine *does* use for this: a deliberately **dead** ask,
which throws away a whole turn to locate one card, fires only when the turn was
nearly worthless, and measured **+0.122** sets/game — real, and declined only
because the ship bar was +0.15 (`prereg/deadline_signalling.md`).

The card-choice channel is available on **every ask** rather than on rare dead
turns, which is roughly two orders of magnitude more often.

**The first encoding tried is a bad one, and that is recorded.** "Name the
lowest card of the half-suit you do not hold" locates a mean of **0.358** cards
for **0.098** probability, because a holding-prefix is usually short. The engine
already names that card 34.2% of the time by accident, so a third of the
information is being sent and nobody is listening. The channel is worth having;
that is not the code to put in it.

One error in the first cut of this measurement is worth recording, because it
inverted the answer. It decoded the *incumbent's* ask with the *convention's*
decoder — counting the cards below the named index as located — and so reported
1.753 cards per ask for the incumbent against 0.215 for the convention, i.e.
that the convention destroys information. The incumbent follows no convention,
so its index carries no prefix guarantee and reading one invents information the
ask never sent. An incumbent ask locates **zero** cards positively.

**What follows.** An encoding should be *adaptive*, spending the bits only where
they are cheap and valuable at once: where the success probabilities of the legal
cards are close together (cheap), and where the half-suit is at risk of freezing
with its split unresolved (valuable). Both conditions are computable from the
belief the engine already builds. This is the smallest concrete thing in this
project that would approximate TMECor, which `\S`limitations names as the right
solution concept and records that nothing here approaches.

## Direction 2 — signalling that aims

The shipped signalling gate fires on *cheapness*: signal when the best ask is
unlikely to land anyway. It does not consider **what the team needs to know**.
Its own path ledger shows the mechanism working — gate-path errors fall from
26.7% to 9.3% — and it still missed the bar by 0.028 sets.

Aim it instead at the half-suit whose allocation is most likely to be forced
unresolved, and the same channel should carry more per turn spent. This is a
cheaper piece of work than Direction 1 and starts from an effect already known to
be real and positive.

## Direction 3 — policy iteration over the belief

Every objective in this engine is fitted against one-ply values or hand-argued.
There has never been a **policy-improvement loop**: play, fit a value function on
the outcomes, search against that value, re-play, iterate. That is how every
strong engine in every other game got strong, and the paper records that v0.3's
value network was abandoned rather than superseded.

This is the largest and least certain of the three. It is listed last because
the other two are aimed at a defect that is *measured*, and this one is aimed at
a method that is *missing*.

## What is deliberately NOT on this list

* **Extending the exact solver.** Ground truth covers 2.6% of decisions, all in
  the last 3% of the game, and the paper measures that extending it to three
  live half-suits would move that by approximately zero.
* **A per-seat opponent exponent.** Fitted on v0.7 and validated on v0.7 is
  circular, and this project already has one case where a gain measured that way
  evaporated against a third engine.
