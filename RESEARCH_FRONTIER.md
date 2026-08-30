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

---

# UPDATE, 2026-08-29: the channel is real, and three code books have been run

The channel direction is no longer speculative. It is built, tested, and
measured, and the results split cleanly into one thing that works, one thing
that was refuted by its own prediction, and one negative that taught more than
either.

## What is now in the engine, all inert by default

`fish4/convention.py` and a term in `sisbatch.draw_batch`: an encoder that
names the agreed card when a cost gate allows, and a decoder that reweights
sampled worlds by whether they would have named it. The half-suit stays
whatever the objective chose, so only the one degree of freedom the engine was
never using moves.

## The depth book works

At sender gate 0.02, 40 games, 1,037 scored decisions, paired by decision:

| beta | teammate NLL | teammate top-1 |
|---|---|---|
| 0.25 | **-0.0074** [-0.0092, -0.0057] | -0.0017 [-0.0070, +0.0036] |
| 0.50 | **-0.0113** [-0.0149, -0.0077] | -0.0029 [-0.0096, +0.0039] |
| 0.80 | **-0.0105** [-0.0165, -0.0045] | -0.0048 [-0.0124, +0.0028] |

Three arms clear both pre-registered gates. For scale, the split-gamma study's
best *passing* cell was -0.0121 on NLL and that was a known result about gamma
rediscovered; this is a new channel.

## The mixture was refuted by its own pre-registered alternative

`prereg/convention_mixture.md` argued the flat weight is mis-specified: it
ignores `k`, the number of cards the asker could legally have named, so it
over-credits matches in low-`k` (deep) worlds. The correct likelihood is
`q*1[match] + (1-q)/k` with `q` the measured carry rate. It is worse at every
`q` (+0.0065 to +0.1141 nats) with top-1 significantly negative throughout.

The registration named this outcome in advance:

> If the mixture's top-1 also decays monotonically, the `1/k` explanation is
> wrong ... most plausibly that `u` is not uniform, because the unencoded
> choice is made by an expected-value objective that prefers particular cards.

That is the live explanation. The `(1-q)/k` term applies to **every** ask,
matched or not, and pushes every teammate who has ever asked towards deep
holdings — a large systematic bias, justified only if the unencoded choice
really were uniform. It is not; it is the objective's.

## RETRACTED: "aiming failed"

**An earlier version of this section said aiming was neutral and built a theory
on it. That reading was wrong and is retracted here rather than quietly
edited.** It came from a 70-decision probe using the mixture at `q = 0.6` --- an
arm that was itself later refuted --- with an interval of +-0.0652, which covers
every effect since measured. A null from an interval that wide is not a null.

The theory built on it, that the aimed book trades a locating signal for a
counting one, was a rationalisation of an underpowered zero. It is not
supported.

## Aiming is the largest result in this direction

Sender and receiver both aimed, 40 games, 1,076 scored decisions, paired:

| arm | teammate NLL | teammate top-1 |
|---|---|---|
| flat 0.5 | -0.0628 [-0.0701, -0.0555] | **+0.0320** [+0.0236, +0.0403] |
| flat 0.8 | **-0.0712** [-0.0803, -0.0621] | **+0.0351** [+0.0258, +0.0444] |
| flat 1.2 | -0.0676 [-0.0789, -0.0564] | **+0.0375** [+0.0274, +0.0476] |

Every arm clears both gates, including the mixture arms that fail everywhere
else. And **top-1 improves significantly** --- which nothing in this project has
managed before. The split gamma, the at-ask covariate, the flat unaimed book:
every previous belief improvement bought calibration and paid for it in the
argmax. This one buys both.

The prediction that motivated it was therefore right: the channel had been
pointed at the half-suit the receiver already knew most about (0.2124 nats of
entropy, already certain 72.2% of the time), and pointing it at the
most-unlocated one (0.8556 nats, certain 9.7%) is worth 4.03x the entropy at
identical cost.

### Two things this is not

**It is not pre-registered.** The aimed arm was added to the instrument
mid-stream; `prereg/convention.md` registers the depth book only. This is an
**exploratory** result and needs a pre-registered replication on fresh seeds
before it licenses anything. `prereg/convention_aimed.md`.

**Its magnitude is not directly comparable to the unaimed arms.** The aimed
sender produces different transcripts, and their baseline is worse (NLL 1.3995
against 1.3706), so there is more room to improve. The paired deltas are valid
within their own transcripts; the ratio between books is not a clean 2.2x.

## Four defects, and the pattern in them

1. the decoder was wired into a sampler path no decision takes
2. the encoder could name an out-of-cards target — `IllegalAction`
3. the decoder read the initial-deal hand, not the hand held at the ask
4. cards the propagator had *deduced* were dropped from the reconstruction

Every one produces a smaller, quieter, entirely plausible number rather than a
crash, and #1 in particular reported *bit-identical to the incumbent on every
seed* — a dead term wearing the exact costume of a measured null, for the second
time in this project. The lesson is not "test more". It is that **a null is only
believable from an instrument that has been shown to be capable of a non-null**,
which is why V3 exists and why it is checked inside the run rather than trusted.

---

# UPDATE: the duel, and what it says about the instrument

**The convention as measured loses to the champion by +1.750 [+0.645, +2.855]
sets a game.** The belief instrument had cleared it three times, on
pre-registered criteria, with a replication on fresh seeds.

Ablation, same deals, same agent seeds, positive = champion stronger:

| arm | diff |
|---|---|
| encoder only --- speak, do not listen | **+1.467** [+0.818, +2.116] |
| decoder only --- listen, nothing sent | +0.033 [-0.646, +0.712] |
| both | +1.267 [+0.526, +2.008] |

**Speaking is the entire cost.** Listening with nothing on the wire is a clean
null, which vindicates the one design decision the module argued hardest for:
the decode ships as a soft weight in the sampler rather than a constraint in the
propagator, because *a constraint can be fatally wrong and a likelihood can only
be mildly wrong*. That is now measured rather than argued.

## The defect, and why no belief instrument could have found it

`encode_cost` priced the swap in **probability of success**. The agent does not
rank asks by probability of success --- `scores` carries lookahead, tempo,
concentration and the information an ask leaks. Measured in the objective's own
units over 877 swaps: median gap **+0.3596**, p90 **+1.2503**, on an objective
whose range is about 1.5.

So `convention_max_cost = 0.05` was not buying a message for five points of
probability. It was routinely paying a **third of the objective**.

The posterior instrument scores arms **off-policy**: the decoder is off while
the games are played, every arm sees identical positions, and the transcripts
are held fixed. That is what makes it a clean paired comparison, and it is
exactly what makes it blind here. **It measures what a message is worth and
never what it cost to send.** Three pre-registered passes and a seed
replication cannot detect a defect that lives entirely in the production of the
transcripts they all share.

## What survives and what does not

**Survives.** The decoder. The belief results are paired within their own
transcripts and the decode genuinely improves the posterior there. The aimed
replication stands as a statement about **inference**: aiming at the
most-unlocated half-suit improves both calibration and the argmax, and the
argmax result is still the only one of its kind in this project.

**Does not survive.** That the channel is *cheap*. Re-priced over 1,088 asks:

| | share of asks |
|---|---|
| objective already picks the agreed card | 19% |
| agreed card ties the chosen one | 5% |
| **free total** | **24%** |

against the **63-74%** the mis-priced gate reported.
`results/convention_cost.json` understates cost the same way and for the same
reason --- it also measured in probability, where a random legal card costs
0.131. The **1.72 bits an ask** remains a true fact about the rules of Fish.
That most of it was free does not.

## The methodological finding, which outlives the convention

This project has leaned on the off-policy posterior instrument for several
studies --- the split gamma, the choice basis, the normaliser spread --- on the
grounds that it is cheap and paired and says no before a duel has to be played.
It is all of those things. It is also **structurally incapable of pricing any
change that alters the transcripts**, and every change to a *policy* does that.

A belief-side instrument can refute (the split gamma, correctly). It can never
license. The gate between them is a duel, and this is the second time this
project has measured a posterior improvement worth nothing or less in play ---
the at-ask-time covariate was the first.

## CORRECTION to the carry-rate figures above, same day

**The "19% / 5% / 24% free" table is wrong and is superseded by this one.** It
was computed from a run with the gate wide open (`1e9`), where the agent swaps
on every ask and plays badly --- games stretch from 108 moves to 122 --- so it
describes a degraded population and not normal play. Measuring each gate on the
games it actually produces, 8 games and ~800 of our asks per gate:

| gate (objective units) | our asks naming the agreed card | moves/game |
|---|---|---|
| **0.0 --- no encoder at all** | **35.3%** | 108.6 |
| 1e-9 --- free-message | 40.1% | 103.2 |
| 0.01 | 43.5% | 103.0 |
| 0.05 | 57.5% | 108.2 |
| 0.15 | 75.6% | 118.0 |
| 0.4 | 86.4% | 122.4 |

Moves per game is the tell: the champion plays about 108, and every gate above
0.05 stretches the game out, which is what paying for a message looks like from
the outside.

**The corrected finding is stronger than the one it replaces.** The incumbent
engine --- no encoder, no agreement, nothing changed --- already names the agreed
card on **35.3%** of its asks, purely because the ask objective and the code
book happen to coincide. Against a chance rate of `1/3.57 = 28%` that is a real
if weak signal sitting on the wire today, unread, at zero cost and zero risk.

It also reframes what the encoder buys: from 35.3% to 40.1% at the
free-message gate, i.e. **about five points**, not the sixty-plus the
mis-priced gate appeared to deliver.

## A necessary qualification to "can refute, never license"

That claim is right about *policy* changes and wrong if stated more broadly, so
state it precisely: **the off-policy instrument is blind exactly when the change
alters the transcripts.** Its blindness is not a property of belief-scoring; it
is a property of scoring arms on shared transcripts whose *production cost* is
outside the comparison.

For the free-read configuration --- decoder on, encoder deleted --- there is no
production cost. The policy is the champion's byte for byte and the transcripts
**are** the incumbent's. Nothing about the games differs between arms because
nothing about the games can differ. There the instrument measures the whole of
what changes, and a positive result there really does mean the belief is better
on the positions the engine actually reaches.

It still does not follow that a better belief wins games --- that is a separate
inference and this project has twice measured it failing --- but the specific
trap that caught the convention (a cost invisible to the instrument) cannot
occur when the cost is zero by construction.


---

# UPDATE, 2026-08-30: the teammate ceiling is mostly INTERACTION

The +3.41 sets/game for perfect knowledge of a teammate's cards has now been
decomposed by routing the same cheat to one decision at a time
(`prereg/declaration_timing.md`, 600 games, anchor replicated to **0.0000** on
both A and T).

| the cheat reaches | ceiling over honest | share |
|---|---|---|
| the declaration channel only | **+1.0767** [+0.7979, +1.3554] | 0.316 |
| the ask channel only | **+0.7600** [+0.4731, +1.0469] | 0.223 |
| both (the published arm) | **+3.4100** [+3.1625, +3.6575] | 1.000 |

    D + K = 1.84     T = 3.41     interaction = 1.57, i.e. 46%

**Neither channel alone carries the ceiling, and the largest single component
belongs to neither.** Knowing your teammates' cards is worth far more when it
informs the asks *and* the declarations than the sum of what it is worth to
either.

## This is the explanation for four nulls, and it is better than the one I had

| attempt | channel it targeted | result |
|---|---|---|
| split gamma | ask (via the belief) | refuted |
| at-ask covariate | ask (via the belief) | better posterior, nothing in play |
| the communication channel | what the team knows, delivered through the belief | belief improved and replicated; duel −0.002 |
| declaration-timing hypothesis | declaration | **not supported**: 0.316, not the ≥0.50 it needed |

Every one of them was reaching for at most a third of the prize while the
interaction term — the biggest piece — sat untouched. My own hypothesis, that
the ceiling is a declaration-timing effect, is among the things this refutes.

## The mechanism was right; the magnitude was not

Handed its teammates' cards, a seat declares at mean move **39.2** against the
honest **77.8** — half as deep into the game — and makes **zero** compelled
declarations in 600 games, against 272 honestly of which 97 were wrong.
Eliminating every compelled declaration is real, and it is worth +1.08 sets a
game, not +3.41.

## What to build next, and it is not what any of the four tried

Not a better belief, and not a braver declaration rule. A policy whose **asks
are chosen for what they will let the team declare later** — a lookahead over
the declaration rather than over the next ask. That is the only shape of
intervention that can reach an interaction term, and this project has not
tried it.

## A rule about validity conditions, learned three times in two days

V1, V2 and V4 of that registration all failed as written, for one reason:
**they assumed the arms are comparable in ways the experiment is specifically
designed to break.** The arms play different games on purpose, so their pin
totals, their declaration path mixes, and even the error classes available to
them all differ *because the manipulation works*.

The conditions that held are the ones stated over a quantity the treatment
cannot touch. **A validity condition has to be about something the treatment
does not change.**


---

# UPDATE: the first attempt on the interaction is a null, and it locates the next one

`prereg/locate_term.md`. The decomposition said 46% of the teammate ceiling --
1.57 sets a game -- is interaction between the ask and declaration channels, so
the first intervention built to reach it was a twelfth term in the ask
objective: price an ask by the share of a half-suit's remaining *location*
uncertainty it removes, weighted by our team owning the rest.

**3,000 duplicate-deal pairs at the a-priori weight: +0.047 [-0.075, +0.168].**
The interval contains zero. Not shipped.

## Diagnosed rather than shrugged at

| | |
|---|---|
| size | median max\|locate\| per position **0.0444** -- at w=0.3, ≤0.013 on a score whose P(success) term spans ~1.0 |
| overlap | correlation with the existing score **+0.42** |
| bite | re-ranks the top ask **3.9%** of positions at w=0.3; **11.3%** even at w=2.0 |
| mechanism | mean declaration move **68.0 -> 67.7**, against the ceiling arm's **39.2** |

A term that re-ranks one ask in twenty-five by one percent of the objective's
scale cannot move 1.57 sets a game, and raising the weight does not rescue it.

## The general lesson, which is worth more than the term

**An additively weighted one-ply feature cannot reach an interaction term** --
whatever it measures. Such a feature can only nudge a ranking that the
P(success) term dominates. The teammate oracle does not win by re-ranking asks
with a small bonus; it plays a *different game*, arriving at positions where
every declaration is voluntary (its path mix is all-voluntary, against
218/17/13 honestly).

That rules out the whole family the ask basis belongs to, which is eleven of
its twelve terms.

## What the evidence now points at

Extend the existing lookahead -- `w_lookahead`, depth 3, beam 4 -- so its
**leaf evaluation scores declarability** rather than sets and tempo. Same
coupling, applied where it compounds over several moves instead of being
averaged into one ask's score. Bigger build; it is the one left standing.

---

# UPDATE: the search cannot reach it either, and this time there is a proof

`prereg/declarability_leaf.md`. The `locate` null said the interaction was not
reachable by an additively weighted one-ply feature and pointed at the search.
So the search got the quantity: `fish4.lookahead.declarability`, the expected
number of half-suits whose **split** we could name,

    D(B) = sum over live half-suits of  prod_c max_{p in team} M[c, p]

priced per edge of the possession chain rather than at its leaf, so each gain is
discounted by exactly the chain that must land to reach it:

    V(B, d) = max_a  p_a * [ 1 + w * (D(B|a) - D(B)) + V(B|a, d-1) ]

It does what it was built to do. On a constructed position the cards-only chain
scores two asks **exactly** equally and the declare-weighted one separates them
by 0.5, because securing a nameable half-suit first is worth `w*G*p*(1-p)` —
a preference in *order* that a card count provably cannot hold.

## It was never duelled, and that is the point

`scripts4/declare_bite.py` screens for futility through the real objective
(`_SCORE_RECORDER`, not a copy of it) before any pairs are spent. 3,786 real
champion decisions:

| w_declare | / score spread | r score | r cards | r rest | bite |
|---|---|---|---|---|---|
| 0.25 | 0.006 | +0.600 | — | — | 0.5% |
| 1.00 | 0.026 | +0.603 | — | — | 2.0% |
| 2.00 | 0.052 | +0.606 | +0.617 | +0.570 | 3.7% |
| 4.00 | 0.107 | +0.609 | +0.622 | +0.572 | 6.7% |
| 6.00 | 0.162 | +0.611 | +0.625 | +0.573 | **8.7%** |

The 15% floor and the [15%, 60%] window were fixed before the first number was
read. Nothing clears it, at any weight up to the a-priori ceiling of 6 — a
half-suit is six cards, and above that the search prefers positions it can
*name* to positions it can *win*. **The 3,000-pair confirmation was not run.**

## The theorem

`ChainState.apply_success` scales the **target's** column by a constant and
divides each row by its total. Both preserve ratios among non-target entries,
and the target is always an opponent. So for any two teammates `t1, t2` and any
card the chain does not itself take:

> `M[c, t1] / M[c, t2]` is **invariant** under the entire search tree — at every
> depth, every beam width, and **every leaf evaluation, including a perfect
> one**.

Asserted to 5e-16 over random chains. A possession chain resolves allocation
uncertainty on exactly the ≤ `depth` cards it takes, and on nothing else.

`scripts4/allocation_locus.py` prices it. Allocation uncertainty per card in
nats is `log(sum_team M) - log(max_team M)`, which summed over a half-suit is
exactly `log(ownership) - log(declarability)`. A chain can take card `c` only
from an opponent, so at most `1 - team_mass_c` of its deficit is reachable.
20,472 (decision, live half-suit) pairs, deficit-weighted, **no ground truth**:

| half-suits with P(our team owns it) | pairs | unreachable by ANY possession chain |
|---|---|---|
| any | 20,472 | 40.7% |
| ≥ 0.05 | 3,605 | 58.2% |
| ≥ 0.5 | 609 | 84.5% |
| **≥ 0.9** | **91** | **100.0%** |

The bottom row is the allocation case itself — 0.1676 of our 0.1759 wrong
declarations a game — and every card in it is on our own side. **A search that
takes cards from opponents cannot touch any of it.**

## What is now closed, and it is a lot

Two whole families, on their own terms rather than by exhaustion:

* **the ask basis** — an additively weighted one-ply feature cannot reach an
  interaction term (`locate`, 3,000 pairs, diagnosed);
* **the possession search** — no leaf evaluation whatsoever can reach the
  allocation half of it (proved, then priced at 100% in the cases that matter).

## What the theorem leaves

The teammate/teammate ratio on a card neither side can ask for moves only on
**public events**: a teammate asking (proving they lack that card and hold one
of the half-suit), or being asked and answering. Those are inputs to the belief
tracker, not to any search. Two levers follow.

1. **Our own MISS is priced at zero and it is the most informative outcome in
   the game.** `possession_value` says it outright — "a miss ends the
   possession, so it contributes no cards" — true in cards and false in
   information. Nothing in the twelve-term basis
   (`suit turn scarce reveal deplete expose claim info certain concent signal
   locate`) prices what our miss teaches our *partners* about our hand.
2. **How much of the teammate split does the public record even contain, and
   how much does the tracker already recover?** An off-policy fit question, no
   duel needed, and it bounds every future attempt the way this theorem just
   bounded the search.

(2) gates (1) and is far cheaper. If the tracker already extracts nearly
everything the record holds, then the teammate ceiling's 1.57 sets a game is
not an inference problem at all, and the search should move to what the oracle
**does** rather than what it **knows**.

---

# UPDATE: the record is not the problem. The engine's confidence in it is.

The theorem above said the teammate/teammate ratio moves only on public events,
so the next question was the bound: **how much does the record contain, and how
much does the tracker already get?** `scripts4/teammate_split.py`, 25 games,
28,707 (decision, teammate-held card) observations, ground truth used as a
label only.

The rule was fixed before the run: top-1 within two points of 50% in the frozen
population — half-suits our team holds all six of, where no opponent may legally
ask and no future public event can ever locate the cards — would mean the record
says nothing.

| unlocated teammate-held cards | nats over 0.5 | top-1 |
|---|---|---|
| all live half-suits | +0.1615 [+0.1574, +0.1656] | 67.8% |
| **frozen: our team holds all six** | **+0.4617** [+0.4518, +0.4715] | **92.1%** [91.2%, 92.9%] |
| the rest | +0.1055 | 63.2% |

**92.1%, not 50%.** The rule did not fire and the inference story is refuted:
the record contains a great deal about which partner holds a card, and the
tracker already has nearly all of it — 1920 draws instead of the deployed 480
moves top-1 by **0.2 points**, consistent with precision having stopped paying
past 480 four results ago.

## So the gap is not accuracy. It is knowing which 92%.

`scripts4/split_calibration.py` asks whether the engine's confidence in its own
split is calibrated — against `post.prob_assignment` conditioned by
`post.prob_all_with`, which is what `ClaimEvaluator` tier 3 actually reads and
compares to its 0.97 threshold.

| population | predicted (exact) | actual | bias |
|---|---|---|---|
| all live half-suits | 0.428 | 0.453 | **−0.024** |
| **frozen: our team holds all six** | **0.453** | **0.650** | **−0.197** |

Everywhere else the engine is calibrated. In exactly the half-suits it declares
from, it is **under-confident by 20 points**, and the reliability table is
monotone: when it says 0.508 it is right 0.798 of the time, when it says 0.688
it is right 0.858.

### Not the arithmetic — the population

A joint over more cards is smaller, and frozen half-suits carry 3.21 unlocated
partner cards against 2.17 elsewhere. Held at fixed `k`:

| unlocated cards k | frozen n | frozen bias | other n | other bias |
|---|---|---|---|---|
| 1 | 60 | −0.126 | 2,012 | −0.009 |
| 2 | 229 | −0.137 | 2,716 | +0.029 |
| 3 | 327 | −0.184 | 1,320 | −0.002 |
| 4 | 193 | −0.326 | 325 | −0.131 |
| 5 | 153 | −0.134 | 30 | +0.009 |

Non-frozen is calibrated at every `k`. Frozen is under-confident at every `k`.

### And the engine can see the population it is biased in

`p_team_joint` — `prob_all_with` over all six, already computed on the shipped
path at the decision a correction would live in:

| engine's P(we own all six) | n | actually frozen | predicted | actual | bias |
|---|---|---|---|---|---|
| [0.000, 0.500) | 7,137 | 10.5% | 0.421 | 0.442 | −0.021 |
| [0.500, 0.800) | 184 | 92.9% | 0.669 | 0.788 | **−0.119** |
| [0.999, 1.010) | 44 | 100.0% | 0.460 | 0.614 | **−0.154** |

The bias is absent where the engine is unsure and largest where it is certain.
**A correction is targetable from inside the engine**, which is what separates
this from every direction closed above.

## Why this is a different kind of lead

The four closed directions all tried to *change what the engine believes*. This
one says the belief is right and the **confidence attached to it is wrong, in a
detectable place, in a known direction**. Under-confidence at a 0.97 gate means
declarations held that we would win — and lateness is exactly the ceiling arm's
edge: it declares at move **39.2** against our **77.8**.

## What is not yet known, and must be before anything ships

* **The mechanism.** There is a *what* and no *why*. A correction fitted without
  one is a lookup table that will not transfer.
* **The sample.** 184 and 44 observations in the two decisive bands. The
  k-breakdown carries 60–327 per cell and agrees, so the direction does not rest
  on the 44 — but a fitted correction needs an order of magnitude more.
* **Whether earlier declaring pays at all.** Under-confidence is only a loss if
  the held declarations were winnable, and `scripts4/path_ledger.py` says
  voluntary declarations are already 0 wrong. Declaring earlier trades into a
  regime the ledger has not measured.

Nothing here licenses a change. It licenses a pre-registration.

---

# UPDATE: the mechanism is the action model, and it names a new intervention

`scripts4/split_why.py`, 1,619 frozen (decision, half-suit) pairs, every arm
re-scored on the **same belief at the same decisions** through
`FishBot4.build_posterior`, so nothing but the named argument differs.

| arm | predicted | names it right | bias | top-1 vs deployed |
|---|---|---|---|---|
| deployed, 480 draws | 0.506 | 0.725 | −0.219 | +0.000 |
| 1920 draws | 0.494 | 0.738 | −0.244 | +0.013 |
| 5760 draws | 0.493 | 0.730 | −0.237 | +0.005 |
| γ = 0.0 | 0.399 | 0.736 | −0.337 | +0.011 |
| γ = 0.7 | 0.578 | 0.721 | −0.143 | −0.004 |
| γ = 1.4 | 0.670 | 0.695 | **−0.025** | −0.030 |

**Flat in draws, monotone in γ.** Twelve times the sampling changes the bias by
0.02; four times the action-model weight nearly eliminates it. The
under-confidence is not the sampler — it is that `opponent_gamma = 0.35`
under-weights how much an ask reveals about the asker's hand, and the effect
concentrates in frozen half-suits because there the record of who asked what is
the *only* remaining evidence about the split.

Silence was ruled out before running rather than measured: `silence_delta` is
1.0 on the shipped path so the mechanism never fires, and it re-weights worlds
by TEAM OWNERSHIP, which is the exact event this measurement conditions on.

## But γ is not free, and the operating point is what decides

`ClaimEvaluator` compares against 0.97, so an average accuracy is the wrong
number. How often does each arm clear the bar, and how often is it right when
it does?

| arm | clears 0.97 | right when it does | clears 0.90 | right |
|---|---|---|---|---|
| deployed | 277 (17.1%) | **0.996** | 295 (18.2%) | 0.973 |
| 1920 draws | 263 (16.2%) | 1.000 | 270 (16.7%) | 1.000 |
| γ = 0.0 | 264 (16.3%) | 0.992 | 265 (16.4%) | 0.992 |
| **γ = 0.7** | **312 (19.3%)** | **0.974** | 413 (25.5%) | 0.966 |
| γ = 1.4 | 549 (33.9%) | 0.918 | 750 (46.3%) | 0.881 |

γ = 1.4 doubles the declarations and is **wrong 8.2%** of the time. Under
`wrong_distribution_outcome="opponent"` a wrong declaration hands the set over,
so that is not a trade — it is the misdeclaration v1.0 spent its whole error
ledger measuring. γ = 0.7 is the only arm that buys volume at near-equal
precision: **+13% more declarations clearing the gate, precision 0.996 → 0.974.**

## The intervention this names, which is new

`opponent_gamma` is global: raising it changes the belief the ASK objective
ranks on too, and `prereg/gamma_split.md` already refuted a uniform raise on
teammate top-1 pooled over all cards. So a global raise is not the move.

**The two decisions have different loss functions.** An ask wants the argmax and
is scored on top-1; a declaration wants a calibrated joint and is scored against
a 0.97 threshold. Nothing in this engine has ever priced them apart — the claim
evaluator reads the same posterior the ask ranking does, built with the same γ.

A **claim-specific γ** — the ask objective keeps 0.35, the declaration reads a
posterior built at a higher one — is the smallest intervention consistent with
every measurement above. It is not a new objective, not a new search, and not a
belief the ask channel ever sees.

Unmeasured and needed before anything ships: whether the extra correct
declarations are ones we would otherwise have won anyway later, which the
per-opportunity table cannot say and only a duel can; and the cost of a second
posterior per decision.

---

# UPDATE: the calibration gap is real and correcting it changes nothing

`prereg/claim_gamma.md`. Built the intervention the mechanism named: the ask
objective keeps γ = 0.35 and the DECLARATION reads a posterior built at a higher
one, through the existing `_claim_ctx` hook, gated on `p_team_all` clearing
`ClaimEvaluator`'s own screen so the second posterior is paid for on ~40% of
decisions rather than all of them. Inert at 0.0 and the champion bit-identical
there, asserted by `tests4/test_claim_gamma.py`.

The screen's rules were fixed before it ran. 480 games, identical deals:

| | deployed | γ = 0.7 |
|---|---|---|
| declarations per game | 4.500 | **4.413** |
| wrong per game | 0.1313 | 0.1208 |

> If declarations per game do not rise by at least 5%, the parameter is not
> reaching the decision, and no duel is run.

They **fell** by 1.9%. **The rule fires; no duel was run.** And the mechanism
check the registration named — mean move index of our declarations, which the
teammate oracle drags from 70.6 to 39.2 — moves **1.0** at γ = 0.7 and **4.1**
at γ = 1.4, while misdeclarations per game rise 19% and 69%.

## Why, and this is the finding

The path ledger says it in one line: **the voluntary path is already 1 wrong in
1,703.** The 0.97 gate is not what holds declarations back. A sharper joint
gives the engine almost nothing new it dares to declare, because it already
declares nearly everything it safely can.

| path | per game | error rate |
|---|---|---|
| voluntary | 3.548 | **0.06%** |
| gate | 0.221 | **19.8%** |
| forced | 0.206 | **41.4%** |

**62 of 63 errors come from `gate` and `forced`** — 0.427 declarations a game.
Those are not decisions made while under-confident. They are decisions with **no
alternative**: `gate` fires when the ask we were about to make cannot land,
`forced` when no legal ask exists at all. Calibration cannot help a choice with
one option.

## The direction this opens

Arriving in a forced position is an **ask-side outcome**, and it is the one
place the error ledger has never been attacked from. `prereg/forced_exhaustive.md`
already ships the best available play once stuck; nothing anywhere plays to
avoid getting stuck.

Nothing in the twelve-term basis prices it. `deplete` rewards draining an
*opponent*, `scarce` is our team's share of a half-suit. Neither prices **our
own remaining ability to ask** — how many half-suits we still hold a card in and
an opponent still plausibly holds one. It is computable from the belief already
on the context, it is a property of the position we choose to move into, and it
has never been measured.

That is the sixth measured case of a better belief buying nothing in play
(split gamma, at-ask covariate, the convention's decoder, `locate`,
declarability, and now the claim gamma). Six is enough to state the pattern
plainly: **this engine's remaining loss is not an inference problem.** Every
attempt to make it know more has failed, and the ledger has been pointing at
positions rather than beliefs the whole time.

---

# UPDATE: being forced is visible eight decisions ahead, and it is not about running out of cards

`scripts4/forced_locus.py`, 15,929 decisions by our seats over 150 games. Every
figure is a **residual against control decisions with the same number of cards
still in play**, because `live_asks` decays with the game and every stuck
decision is by construction late — an uncontrolled version of this table shows a
gradient for any feature that merely decays with time, and showed one.

Lead is counted in the **seat's own decisions**, since a seat can only steer on
its own turns.

| lead | n | cards left | hand | ask_hs | live_asks | best_p |
|---|---|---|---|---|---|---|
| 0 | 114 | 18.8 | **+0.595** | −0.692 | **−10.158** | −0.415 |
| 1 | 103 | 25.5 | +0.892 | −0.305 | −10.441 | −0.195 |
| 2 | 103 | 27.7 | +0.825 | −0.253 | −9.795 | −0.062 |
| 3 | 103 | 30.0 | +0.734 | −0.183 | −8.846 | −0.018 |
| 5 | 103 | 33.7 | +0.577 | −0.156 | **−6.850** | −0.022 |
| 8 | 95 | 37.8 | +0.722 | −0.057 | **−3.986** | −0.056 |
| 12 | 82 | 44.0 | +0.565 | +0.200 | +0.638 | +0.075 |

Two things, and both are new.

**It is steerable.** `live_asks` is 6.9 below control five of the seat's own
decisions before it gets stuck and 4.0 below at eight — roughly thirty to fifty
table moves. It reaches zero only at lead 12. Being forced is not an accident of
the last move; it is the end of a trajectory that is visible for most of a game.

**It is not a shortage of cards.** `hand` is **positive at every lead** — a seat
about to be stuck holds about 0.7 MORE cards than the control at the same stage,
while having ten fewer live asks. You do not get forced by running out of cards.
You get forced by holding cards in half-suits where everything else is **on your
own side**: more hand, fewer places to reach. `best_p` stays at control until
lead 1, so the *quality* of the asks available never degrades — only the
**count** collapses.

## Why the closed search does not close this one

The theorem in `prereg/declarability_leaf.md` says a possession chain cannot
change `M[c, t1] / M[c, t2]` for two teammates, because `apply_success` only
ever moves a card from an **opponent** to us. That is precisely why it cannot
reach declarability.

**Askability is made of exactly what the chain does edit.** `live_asks` counts
legal asks whose target plausibly holds the card — a function of *opponents'*
holdings, which `apply_success` rewrites on every edge. The same search that
provably could not see the allocation problem has full purchase on this one.

And the tension is real rather than assumed: every successful ask takes a card
*from* an opponent, so **each success shrinks the asker's own future
askability**. Taking cards is how the game is won and how a seat strands itself,
and nothing in the engine has ever priced the second half of that.

## What is at stake, stated as a bound and not a promise

`gate` and `forced` produce 62 of 63 wrong declarations, 0.129 a game. Under
`wrong_distribution_outcome="opponent"` each hands the set over, so each avoided
error is a two-set swing: **≤ 0.258 sets a game**, which clears the +0.15 bar
with room.

It is an upper bound and a loose one. The counterfactual for a forced
declaration is not "no error" — the half-suit still has to be resolved, and if
we do not declare it someone else does, possibly correctly. Only a duel can
price that, and it is the most likely way this direction comes back smaller than
the bound.

---

# UPDATE: the position IS steerable, and steering it is worth nothing

`prereg/reach_term.md`. The first intervention in six that is not about knowing
more: a thirteenth basis term charging an ask for the entry point it spends,

    reach = -pi * prod over the other five cards of (1 - P(an opponent holds it))

the probability that landing the ask closes the half-suit as somewhere we can
ever ask again. Nothing in the basis prices it — `deplete` drains an *opponent*,
`scarce` and `concent` reward team share and concentration, both of which
*consume* entry points and neither of which is charged for them.

`scripts4/term_bite.py` is now a standing futility screen for **any** basis
term, so the next one is screened for free. The v1 shape divided by the number
of askable half-suits and could not reach the decision — 1.6% bite at w = 0.3,
7.6% at w = 1.2, which is `locate`'s `1/u` again. v2 drops the divisor and
clears at **w = 0.80, bite 15.2%**, the smallest weight inside the registered
[15%, 60%] window. Correlation with the objective **−0.473**, against `locate`'s
+0.42: it points *against* the score rather than restating it.

## Both screen rules fired

480 games, identical deals:

| | baseline | w_reach = 0.8 |
|---|---|---|
| voluntary | 3.548 | **2.392** |
| gate | 0.221 | **0.585** |
| gate + forced | 0.427 | **0.800** |
| total per game | 4.500 | **3.767** |
| wrong per game | 0.1313 | **0.2167** |
| margin | 0.0 | **−1.671** |

The registration named this exact failure as the term's risk: `keep` is largest
when our team already holds the rest of the half-suit, so a positive weight
penalises **the ask that completes a set**. The engine stopped finishing, and
the declarations it withheld reappeared on the `gate` path — up 165%, at a 22.4%
error rate, displaced out of a path with a 0.06% one. **No duel was run.**

## The sign is backwards, and reversing it works — mechanically

Post-hoc, and labelled as such: the diagnostic showed stuck seats holding *more*
cards with *fewer* live asks, and the term assumed completing half-suits caused
it. The opposite sign says otherwise.

| arm | gate+forced /game | wrong /game | margin |
|---|---|---|---|
| baseline | 0.427 | 0.1313 | 0.0 |
| w_reach = +0.8 | 0.800 | 0.2167 | −1.671 |
| **w_reach = −0.4** | **0.348** | **0.1000** | **−0.075** |
| w_reach = −0.8 | 0.330 | 0.1042 | −0.100 |

**A quarter of the wrong declarations, gone.** Stuck declarations down 19–23%,
voluntary holding at 3.49–3.59. The clog is caused by **not finishing**
half-suits, not by finishing them — the causality in `forced_locus` ran the
other way.

**And the margin does not follow.** Nothing here approaches +0.15, and no
confirmation is registered: flipping a sign after reading a screen and then
duelling it is the forking path this project forbids.

## What that closes

The registration's own caveat came true:

> The counterfactual for a forced declaration is not "no error" — the half-suit
> still has to be resolved, and if we do not declare it someone else does,
> possibly correctly.

**Removing a quarter of the errors bought nothing.** The 0.258 sets-a-game bound
was loose in exactly that way. The 62 errors in the ledger are not recoverable
value; they are the price of resolving half-suits that had to be resolved by
somebody.

Six directions gave the engine a better *belief* and none paid. This one gave it
a better *position*, measured and achieved, and it did not pay either.

## A CORRECTION TO THE PARAGRAPH THAT WAS HERE

The first version of this section closed with: *"what is left in this engine is
not a defect to be fixed. Any further gain has to come from a different policy
class, not from a correction to this one."*

**That is a stronger claim than anything measured supports, and it was mine.**
Seven nulls in one family establish that the seven interventions tried did not
pay. They do not establish that no correction can. The two instruments that
would test it are both under-powered and one says so in its own docstring:

* `results/exploitability.json` — a single seat deviating to a rollout best
  response gains **−0.4875 [−1.244, +0.269]** over 80 pairs. `scripts4/
  exploitability.py` states the asymmetry outright: *"gain <= 0 — weak evidence
  only. PIMC's strategy fusion can make the responder play badly, so a failure
  to find an exploit is not evidence that none exists."* The responder ran at
  beam 3 and 3 worlds.
* `results/ask_regret.json` — the ask objective's chosen ask against the best
  available by rollout, **−0.0968 [−0.302, +0.109]** over **37 positions**. The
  interval contains zero and is wider than the +0.15 ship bar. Its own
  `mean_corr_objective_vs_rollout` is **+0.164 ± 0.072**: the objective barely
  tracks the rollout value it is being compared against.

So the honest statement is the weaker one: **seven pre-registered attempts to
correct this policy have failed, and the headroom left in it has never been
measured with enough power to say whether an eighth could succeed.** Which of
those two sentences is true is a measurement, not a conclusion, and it is the
next thing to run rather than the last thing to assert.

## What the two headroom runs can and cannot answer, stated before they land

Both are in flight as this is written and neither number is known. Fixing the
interpretation now, because a power calculation read *after* a result is not a
power calculation.

**Exploitability**, 240 deals, responder raised from beam 3 / 3 worlds to
**beam 5 / 6 worlds**. The per-deal sd is 3.453, so:

| half-width | deals needed | wall-clock at 62 s/deal |
|---|---|---|
| 0.60 | 127 | 2.2 h |
| **0.44** | **237** | **4.1 h** |
| 0.30 | 509 | 8.8 h |
| 0.15 | 2,036 | 35.1 h |

**n = 240 buys a half-width of 0.437.** So this run can rule out a *large*
single-seat exploit and **cannot resolve the +0.15 ship bar** — nothing it
returns should be read as "there is no headroom", and an interval containing
zero here is compatible with a real gain of a third of a set. Resolving the bar
on this instrument costs 35 hours, which is a fact about the instrument rather
than about the engine.

The asymmetry in `scripts4/exploitability.py`'s docstring still applies and is
the sharper limit: a rollout responder that fails to find an exploit may simply
be playing badly, so **only a positive result is informative**. A negative one
bounds nothing.

**Ask regret**, 240 positions × 24 worlds, harvested from 400 games — against
the 37 positions × 12 worlds the published figure rests on. The previous run's
`attenuation` table says the estimator recovers 21% of a true effect of 0.5,
57% of 1.0 and 97% of 2.0, so the quantity it measures is biased toward zero at
exactly the scale that matters and the wider run reduces that without removing
it. Its early rows already show the regret is **not uniform**: +0.42 to +0.58 in
positions offering 50-odd legal asks, 0.000 in positions offering three. If that
holds up, "how much does the objective leave on the table" has no single answer
and the honest version is a curve against the size of the action set.

---

# RESULT: the ask objective has no measurable one-step headroom

`results/ask_regret_wide.json`. **208 positions × 24 worlds**, harvested from 400
games, against the **37 × 12** the published figure rested on — and the harvest
cap that silently produced that 37 is fixed.

| | |
|---|---|
| **cross-fitted regret** | **−0.0188 ± 0.0316, 95% [−0.0808, +0.0431] sets** |
| naive max-over-actions | +0.4667 (inflated: selection bias +0.4856) |
| the same test against a RANDOM ask | **+0.2548 ± 0.0506** — the scale |
| **the objective captures** | **107.4% of what one-step lookahead can find** |
| corr(rollout value, full objective) | **+0.2640 ± 0.0265** (was +0.164 ± 0.072) |
| mean rank of the chosen ask | 34.6% through the action list |
| best–worst spread | 1.4295 sets |

**The interval is ±0.062 — for the first time tighter than the +0.15 ship bar.**
The hand-designed objective's chosen ask is, if anything, *better* than the
rollout-best, and it beats a random ask by +0.25. Against the estimator's own
attenuation table (26.6% of a true +0.5, 67.3% of +1.0, 99.1% of +2.0), a true
edge of +0.5 would surface at +0.13 and is excluded by the upper bound; the run
rules out one-step ask improvements worth more than roughly **+0.2 per
decision**.

That is a real answer to one third of the headroom question, and it is the
first time it has been answered with enough power to matter. **For the ask
channel, one-step improvement is exhausted.** It bounds neither the declaration
channel nor multi-step improvement, and it is measured against a 24-world
rollout rather than against truth.

## A prediction of mine, stated in advance and refuted

The section above this one predicted, before the run landed, that regret would
prove to be *a curve against the size of the action set* rather than one number
— because the early streaming rows showed +0.42 to +0.58 where 50-odd asks were
legal and 0.000 where three were.

| legal asks | n | mean regret | 95% half-width |
|---|---|---|---|
| 2–5 | 10 | +0.0500 | 0.1382 |
| 5–15 | 54 | +0.0478 | 0.1036 |
| 15–30 | 85 | +0.0039 | 0.0953 |
| 30–45 | 51 | −0.1601 | 0.1368 |
| 45–54 | 8 | +0.1042 | **0.5098** |

**corr(n_asks, regret) = −0.058 ± 0.136.** No relationship, and the sign is if
anything the opposite of the one predicted. The rows I read the pattern off sit
in a band of **eight positions with a half-width of ±0.51** — I was reading
noise off a streaming log, which is the same mistake the `locate` screen made at
400 pairs and the reason that screen's withdrawal condition was unevaluable.

The prediction is recorded as refuted rather than removed. Its value was in
being falsifiable before the data arrived, and one number, not a curve, is the
honest summary.
