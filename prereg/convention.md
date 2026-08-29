# Pre-registration: can a pre-play naming agreement beat the depth heuristic?

**Registered 2026-08-29, before the posterior instrument was written or run.**
What had been looked at when these conditions were fixed is listed under "What
is already known" and consists only of channel-capacity and sender-side facts.
No decoder result of any kind existed.

## The claim

Every result in this project so far attacks the **inference**: believe the
existing choice model harder (`prereg/gamma_split.md`, refuted), or give it a
better covariate (`prereg/choice_basis.md`, cleared its fit bar). This attacks
the **channel**.

The rules force an asker to name a *specific* card, and within the half-suit
they have chosen that pick is free. The engine spends all of it on expected
value. If both seats of a team agree in advance which card to name, the choice
itself becomes a message and costs no turn. That is a convention in the bridge
sense and it is legal in exactly the way bidding conventions are: Literature
forbids communication *during* play, not agreement before it. The paper's
limitations section names **TMECor** --- equilibrium with pre-play correlation
and no in-play channel --- as the right solution concept for this game and
records that nothing in the project approximates it. This is the smallest
concrete thing that does.

**The convention.** Among the cards of the half-suit the asker does not hold,
sorted by index, name the one at position `(held - 1) mod k`, `k = 6 - held`.
The receiver cannot invert that --- the modulus depends on the very quantity it
is trying to learn --- and does not need to: for each candidate world it has a
hypothesised hand, so it asks the *forward* question, "would this hand have
named this card?", and reweights the world by `exp(beta)` if so.

**Why the weight is soft, which is the load-bearing decision.** The sender only
speaks when the channel is cheap, and cheapness is computed from the sender's
own posterior, which the receiver cannot reproduce. So the receiver never knows
whether a given ask carried a message. Under a hard decode, every unencoded ask
would inject a false constraint and the propagator would cheerfully eliminate
the true world. A constraint can be fatally wrong; a likelihood can only be
mildly wrong.

**Why it is not redundant with the depth model.** The shipped choice model reads
an ask as evidence about *how many* cards of the half-suit the asker holds. The
convention's test is a function of *which* ones. It therefore discriminates
between worlds **inside a single depth class**, where the choice model is
exactly uniform by construction. That is the only reason this can add anything
at all, and it is checked as a validity condition below rather than assumed.

## What is already known before this registration

All of it is about the channel and the sender. None of it is a decoder result.

1. **The channel is wide.** 3,883 asks over 40 self-play games at the champion:
   a mean of **3.57 legal cards** per ask, **1.72 bits**, spent entirely on
   expected value. The cost of naming a random legal card instead of the best is
   **0.131** probability, and the best-to-worst spread is heavily skewed ---
   median 0.022, p90 0.616. At a spread of 0.02 or less there are **19.3 bits a
   game** going spare, and locating one card among six players is 2.6 bits. That
   is roughly seven cards' worth of free location information per game
   (`results/convention_cost.json`).
2. **The existing signalling channel is expensive by comparison.** It spends a
   whole turn on a deliberately dead ask to prove one negative, is worth
   **+0.122 [+0.029, +0.215]** sets/game, and was declined only against a
   pre-registered +0.15 bar (`prereg/deadline_signalling.md`).
3. **The sender fires.** Six games per setting, whole table encoding:

   | `convention_max_cost` | our asks | carrying the convention card | mean cost paid |
   |---|---|---|---|
   | 0.02 | 560 | 57.0% | 0.0040 |
   | 0.05 | 628 | 63.4% | 0.0090 |
   | 0.10 | 621 | 73.6% | 0.0175 |
   | 0.25 | 595 | 79.8% | 0.0668 |
   | 1.00 | 1,552 | 100% | 0.4983 |

   The last row is the degenerate extreme --- speak whatever it costs --- and
   its game length nearly triples, which is what paying half a probability an
   ask looks like. It is carried as a boundary marker and is not a candidate.

4. **The first wiring was dead.** The likelihood was added to
   `SISSampler._attempt`, the scalar sampler, which no decision has used since
   the batch path landed; `sample_batch` calls `draw_batch`, which never
   materialises the per-draw deal dict the scalar code reads. The inertness
   check duly reported the decoder as bit-identical to the incumbent on every
   seed --- **a dead term reading exactly like a measured null**, which is the
   second time this project has produced that artefact (the first was the
   `gamma_team` guard in `oppmodel.build`). It is now in `sisbatch.draw_batch`,
   moves the marginals on 47 of 62 real positions with a median absolute
   marginal change of 0.070, and `tests4/test_convention.py` asserts both that
   and the agreement of the two implementations world by world. **This is why
   validity condition V3 below exists and why it is checked inside the
   instrument rather than trusted.**

## Design

**Transcripts.** Generated **once per sender setting**, with the encoder on at
every seat and **the decoder off at every seat**. Every decoder arm is then
scored offline on those identical positions. This is what makes the comparison
paired: an arm that acted on its own belief would be scored on its own positions
and the difference would be confounded with which positions each arm reached.
Truth is used only to score, never to act.

The consequence, stated now rather than discovered later: this measures whether
**the message decodes**, not whether a team running both sides plays better. A
pass licenses a duel, registered separately. It ships nothing.

**Arms.** Sender `convention_max_cost` in {0.02, 0.05, 0.10}; receiver
`convention_beta` in {0.25, 0.5, 0.8, 1.2, 2.0}, each paired against
`convention_beta = 0` **within its own sender setting**.

**Where beta should land, predicted in advance.** Under the true world the named
card is the convention card with probability equal to the carry rate above
(0.57-0.74); under a false world it is roughly `1/3.57 = 0.28` by chance. The
log-odds of that is `log(0.63/0.28) ~= 0.81`. So a correctly specified decoder
should optimise near **beta ~= 0.8**, and an optimum at the top of the grid
would mean the term is doing something other than decoding.

**Pools.** Cards the propagator has *not* pinned, split by where the card
actually is: `team` (true holder is a teammate of the observer) and `opp`. The
independent unit is the **decision**, never the card --- cards inside one
decision share a belief.

**Outcomes**, each a paired mean difference against `beta = 0` with a 95%
interval:

* **Primary:** teammate-side NLL.
* **Co-primary:** teammate-side top-1 accuracy.
* Secondary, reported and not gating: opponent-side NLL and top-1, pooled NLL,
  and the same three restricted to half-suits a teammate has asked in.

## Decision rule, fixed in advance

An arm **licenses a duel** only if, on the teammate pool:

1. its paired NLL interval lies **entirely below zero**, **and**
2. its paired top-1 interval is **not entirely below zero**.

Both, or nothing. Condition 2 is the one that refuted the split gamma: a model
can improve NLL by spreading mass while naming the true holder less often, and
for an engine whose dominant error is *naming a split* that is a worse belief.
The allocation decision reads the argmax.

**If no arm satisfies both, the direction is withdrawn and no duel is run.**

## Validity conditions --- the run is VOID, not null, if any fails

* **V1 --- the message is on the wire.** At least **25%** of our own side's asks
  in the generated transcripts must name the convention card. Below that there
  is nothing to decode and the instrument is scoring noise.
* **V2 --- the term is not redundant with depth.** Across the sampler's own
  drawn worlds, the convention term must vary **within** a fixed asker-depth
  class on at least 20% of scored (position, asker) pairs. If it does not, it is
  the depth model wearing a new name.
* **V3 --- the term is live.** The `beta > 0` arms must produce marginals
  numerically different from `beta = 0` on at least **50%** of scored decisions.
  A term wired into a path no decision takes has already been mistaken for a
  measured null once in this project and once in this task.
* **V4 --- the inert default holds.** `convention_beta = 0` and
  `convention_max_cost = 0` must reproduce the champion bit-identically.

## What a null would mean

That the *capacity* measured in `results/convention_cost.json` is real but this
**encoding** does not convert it into belief accuracy. That is a result about
the code book, not about the channel, and it would leave the channel open: 1.72
bits an ask is a fact about the rules of Fish, not about this convention. The
next code books in line are (a) encode the asker's *void* half-suits rather than
its depth, since a void is what the declaration policy actually needs, and (b)
encode a single bit --- parity of the holding --- which costs far less and is
far more often free.

A null would also sharpen the negative result worth publishing either way: that
an engine with exact propagation, a fitted choice model and an exhaustive
endgame leaves **19.3 bits a game** unspent because the objective was never
written to consider what an ask *says*.

---

# AMENDMENT to V2, recorded 2026-08-29, before the primary outcome was read

**What had been read when this was written:** the three validity counters from a
one-game smoke run (below `MIN_GAMES_TO_WRITE = 20`, so it writes nothing and is
void by construction) and three mechanical diagnostics of the sampler's own
drawn worlds. No 40-game run had been started. No paired NLL or top-1 interval
at any usable sample size had been looked at.

**Amending a validity condition after watching it fail is exactly the move this
project's discipline exists to prevent**, so the original is preserved above
verbatim, both statistics are computed and reported by the instrument, and any
result that depends on the amendment will be labelled as such.

## V2 as registered fails

> **V2 --- the term is not redundant with depth.** Across the sampler's own
> drawn worlds, the convention term must vary **within** a fixed asker-depth
> class on at least 20% of scored (position, asker) pairs.

Measured over 1,215 (position, ask) pairs in four games: **6.9%**. Under every
sender setting in the smoke run it fails, at 1.5% to 5.6%.

## Why it was the wrong statistic, on grounds independent of any outcome

The denominator is wrong. It counts every recorded ask, and **76.5% of recorded
asks are inert**: the sampler entertains exactly one holding for that asker in
that half-suit, so `is_encoded` takes the same value in every world, so the ask
contributes the *same constant* to every world's log-weight.

A constant factor cancels exactly under self-normalisation. That is an
identity, not an empirical claim, and the instrument checks it rather than
asserting it: multiplying every importance weight by `exp(3 beta)` moves the
normalised weights by `5.55e-17`.

So an inert ask cannot dilute the convention's effect on the posterior. It can
only dilute the statistic V2 was written with. As registered, V2 measures **how
sharp the sampler already is**, not **whether the convention duplicates the
depth model** --- and those come apart precisely because the propagator is
exact, which is a property of this engine and not of the idea under test.

## V2', the amended condition

> **V2' --- the term is not redundant with depth.** Among the recorded asks
> where the convention term is **not constant across the sampler's drawn
> worlds**, at least **20%** must vary within a fixed asker-depth class.

Same floor, same direction, denominator restricted to the asks that can affect a
posterior at all. Measured: **29.5%** over the same 1,215 pairs (84 of 285 live
asks). It passes.

Reported alongside it, and not gating: 23.5% of recorded asks are live, and
**84.0% of scored decisions carry at least one live ask**, which is the
statement V3 already tests empirically from the other end.

## A defect found while diagnosing this, and fixed before the run

The age structure of the inert asks exposed a genuine correctness bug, not a
statistical one. The sampler works in **initial-deal space** ---
`bel.candidates[c]` is the set of players who may have *initially* held `c` ---
but the code book is a function of the hand the asker held **at the moment of
the ask**. Cards move. The decoder was testing the encoding against a holding
the asker may never have had, and the further back the ask, the more wrong the
test.

`oppmodel.build` now walks the log forward keeping a public location ledger and
snapshots each of our own asks as it passes: cards publicly with the asker then
(constant in every world), cards publicly elsewhere (definitely not held), cards
never publicly moved (decided by the draw). The measured effect of the fix, on
the same four games:

| age of ask | mean distinct holdings | `is_encoded` varies |
|---|---|---|
| most recent | 6.01 | 48.0% |
| 1-2 back | 2.82 | 27.5% |
| 3-6 back | 2.34 | 20.1% |
| 7-14 back | 1.76 | 11.2% |
| 15+ back | 1.58 | 7.1% |
| **all, before the fix** | | **9.0%** |
| **all, after the fix** | | **16.2%** |

This also retires a design change that looked necessary an hour ago. The decay
of the curve invited a `convention_window` --- decode only the last N asks ---
but with the at-ask reconstruction correct, a stale ask is now *correctly*
interpreted and merely weak, and an inert one cancels. There is nothing left for
a window to remove, so no parameter is added.

## Three defects found in this build, recorded because the pattern matters

1. **The decoder was wired into a path no decision takes** (`SISSampler._attempt`
   rather than `sisbatch.draw_batch`). It reported bit-identical to the
   incumbent on every seed --- a dead term reading as a measured null.
2. **The encoder could name an illegal target.** It re-picked the target as the
   likeliest holder over all opponents; a seat can be empty and still be the
   best guess for where a card went. `IllegalAction: target has no cards`, on
   the second game of the first sender sweep. It now takes its targets from the
   engine's own legal-ask list.
3. **The decoder read the wrong hand** --- initial-deal rather than at-ask, as
   above.

All three were found by mechanical checks run *before* any outcome was read.
None would have been visible in the primary outcome: each one produces a
smaller, quieter, entirely plausible number.
