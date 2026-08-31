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
| `unlocated_now` — give that model a better covariate | **refuted in the belief**; +3,143 nats on the fit and the posterior gets *worse*, monotonically, on both criteria |
| declarer-holding lever — let the best-informed teammate declare | refuted; the covariate was a confound |

All three attack the **inference**: squeeze more out of the asks that happen.
None attacks the **channel**: how much the asks carry in the first place.

### What `unlocated_now` cost, and what it bought

It is the sharpest of the three because the offline case was the strongest.
`prereg/choice_basis.md` put it at **+3,143 held-out nats** over the shipped
covariate — three times its own pre-registered bar of 1,000 — on 17,005 choices
with folds at the game level. On predicting which half-suit a teammate asks in,
it is not a marginal improvement; it is the best covariate anyone has found.

`prereg/unlocated_belief.md` then asked the only question that matters, over 40
games and 1,027 decisions, clustered on the game (k=40):

    w        team NLL   team top-1        paired vs w=0, clustered by game
    0.0      1.27280      0.41648         (incumbent)
    -0.5     1.29318      0.41183         NLL +0.0204 [+0.0162, +0.0246]
    -1.0     1.30445      0.40710         NLL +0.0317 [+0.0253, +0.0380]
    -2.0     1.31258      0.40306         NLL +0.0398 [+0.0319, +0.0477]
    -4.0     1.31500      0.40089         NLL +0.0422 [+0.0339, +0.0505]

Every cell is worse, on both criteria, and the harm grows monotonically with
the weight. The best cell is the incumbent, which the pre-registration named in
advance as a refutation. The opponent pool moves the same way, so this is not
error being shifted from one side of the table to the other.

**A dose-response refutes a mechanism rather than merely failing to find it**,
and this one is unusually clean: the covariate that best predicts *which
half-suit a teammate asks in* actively damages the posterior over *where the
cards are*. Those are different questions, and 3,143 nats of skill at the first
bought less than nothing at the second.

That is the fourth attempt on the inference to die, and the second — after
`gamma_team` — to die specifically because a better model of the ask is not a
better model of the deal.

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
channel, one-step improvement is exhausted.**

## A CORRECTION TO WHAT THAT SENTENCE COVERS

`scripts4/ask_regret.py` sets `SPEC = {"opponent_gamma": 0.35}` and uses it in
three places -- the agents that harvest positions, the agents that roll a
position out, and the agent whose choice is the incumbent. **That is not the
champion.** `V06_DEPLOYED` carries `w_lookahead = 0.25` at depth 3 beam 4 and
480 draws; the measured policy has no belief-space lookahead and 160.

So the result above bounds the headroom of **the ask objective in isolation**,
which is a cleaner thing to have measured in one way -- it is the hand-designed
objective on its own, unassisted -- and is **not** a bound on the champion's.
The distinction was not stated when the figure was first written here, and this
paragraph is the correction. `ASK_REGRET_SPEC=champion` now switches the
instrument, and the run prints which policy it measured.

It bounds neither the declaration channel nor multi-step improvement, and it is
measured against a 24-world rollout rather than against truth. And the
declaration channel is excluded **by construction**, not by omission:
`ask_regret` discards every position where the policy chose to declare, with the
line `if not isinstance(chosen, Ask): continue  # a claim: decided from the
posterior, not searched`.

## And the champion-spec run has NO RESOLUTION, which is the honest reading

`results/ask_regret_champion.json`, `ASK_REGRET_SPEC=champion`, 70 positions ×
16 worlds against V06_DEPLOYED — lookahead on, 480 draws:

| | |
|---|---|
| cross-fitted regret | −0.0893 ± 0.0838, 95% **[−0.2535, +0.0749]** |
| the same test vs a RANDOM ask | **+0.1857 ± 0.0966** |
| corr(rollout value, objective) | +0.2933 ± 0.0370 |
| mean rank of the chosen ask | 30.2% (against 34.6% for the isolated objective) |

**The scale reference is itself indistinguishable from zero.** The instrument
prints the consequence rather than letting a reader miss it: *"there is no scale
to express the regret as a fraction of — the test has no resolution here, which
is a fact about the design and not about the objective."* The interval is also
wider than the +0.15 bar.

So this run establishes **nothing** about the champion, and the point estimate
must not be quoted. What stands is the isolated-objective result at 208 × 24;
what the champion leaves on the table at one ply is still unmeasured, and needs
roughly the same 208 × 24 design at ~85 s a position — five to eight hours,
which is a cost rather than an obstacle.

The two numbers that *are* suggestive and are recorded as no more than that: the
champion picks asks ranked 30.2% through the list against the isolated
objective's 34.6%, and its objective correlates +0.2933 with the rollout value
against +0.2640. Both point the same way at a sample that cannot resolve either.

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

---

# RESULT: the declaration is taken at the right moment, in both directions

`results/declare_regret.json`. The new instrument runs the same cross-fitted
estimator with **claim actions in the action set**, filling the hole
`ask_regret` names in its own code. 109 positions where a declaration was
actually available, 16 worlds, the ask objective in isolation.

| what the policy did | n | regret | ± as first published | ± clustered by deal |
|---|---|---|---|---|
| all positions | 109 | +0.1101 | 0.1173 | 0.1339 |
| **it ASKED** — was declaring better? | 98 | +0.1607 | 0.1241 | 0.1433 |
| **it DECLARED** — was asking better? | 11 | **−0.3409** | 0.2338 | **0.4402** |

The ± columns are the correction of 2026-08-30 (#83): these 109 positions come
from **four deals**, so the published half-widths divided by 109 and paired a
4-cluster standard error with 1.96 instead of *t* at 3 df.

**The declared arm no longer excludes zero.** It reads −0.3409 [−0.7811,
+0.0993] once clustered, against [−0.5747, −0.1071] as published. The earlier
sentence here — "regret −0.34, interval excluding zero, so the alternatives were
worse" — is **withdrawn**. Eleven positions from four deals cannot carry it. The
point estimate still points away from "too eager", and that is all it says.

**When it asks, declaring would have been much worse**, and this half is
unaffected — it *tightens*, being a within-position contrast whose deal effect
cancels in the difference:

> where the policy asked, **best claim minus best ask = −1.1849 ± 0.1051**
> over 98 positions

and the best available claim beat the best available ask in **3 of 98
positions, 3.1%**. Splitting the regret by that: **+0.1474 on the 95 positions
where no claim would have won**, so the +0.16 is about choosing a better *ask*,
not about a missed declaration.

## This refutes the hypothesis that has been implicit all session

The teammate oracle declares at move **39.2** against our **70.6**, and every
direction from `prereg/declaration_timing.md` onward has treated that gap as
something to close. It is not closeable, and this says why: **at the moments we
ask, the declarations available to us are worth 1.18 sets less.** The oracle
does not declare early because early declaration is better. It declares early
because it is *certain*, and certainty is what it was handed. An honest engine
cannot copy the timing without the knowledge, and `results/teammate_split.json`
already showed the knowledge is not available — the record holds 92.1% and the
tracker already has it.

Two of the three channels are now measured and both are clean.

## One lead, and it is a subgroup finding

Ask regret is **−0.0188 [−0.0808, +0.0431]** over all positions and **+0.1474**
on this population — positions late enough that a declaration is available.
Different populations, so not a contradiction, but the suggestion is that the
objective is weaker late.

Recorded as a lead and nothing more: it is a subgroup that was not
pre-registered, and the action set here carries many hopeless claims whose noise
biases the cross-fitted challenger selection *downward*, so if anything +0.16 is
conservative. It needs its own measurement on its own population before it is
worth a term.

---

# The champion-spec regret is POSITIVE, and the obvious comparison is invalid

`results/ask_regret_champion_wide.json`, 162 positions × 24 worlds against
V06_DEPLOYED:

| | champion | the objective in isolation |
|---|---|---|
| cross-fitted regret | **+0.1641 [+0.0046, +0.3236]** | −0.0188 [−0.0951, +0.0575] |
| captures of what one-step lookahead finds | **52.0%** | 107.4% |
| vs a random ask | +0.3416 ± 0.0518 | +0.2548 ± 0.0506 |
| legal asks per position | 19.0 | 22.1 |
| best–worst spread | 1.5576 | 1.4295 |
| positions | 162 | 208 |

**The champion's regret excludes zero.** That is the first positive headroom
finding of the session, and it stands on its own terms: against a 160-draw world
measure and a champion continuation, the champion's chosen ask leaves +0.164
sets a decision on the table.

**But the side-by-side reading — "the lookahead makes ask selection worse" — is
not supported by these two runs, and it would be the easy thing to publish.**
Three things break the comparison:

1. **Different populations.** Each run harvests from self-play by its own
   policy. 19.0 legal asks a position against 22.1, and a wider best-worst
   spread: the champion reaches sharper positions, where the same quality of
   choice costs more in absolute sets.
2. **Different value functions.** `_rollout` plays the continuation with the
   same SPEC, so the two runs score their actions under different games.
3. **An actor/evaluator mismatch in one arm only.** The world-sampling posterior
   is hardcoded at `n_draws=160`. The isolated agent also acts at 160, so its
   actor and evaluator agree; the champion acts at 480 and is scored on worlds
   drawn at 160.

## The clean experiment, and it costs one run

`scripts4/actor_compare.py`. The per-world rollout values **do not depend on the
actor** — only the incumbent does. So one set of positions, one set of worlds
and one set of rollouts score BOTH actors, and all three confounds are held
fixed by construction. Paired on the position, so the deal variance that
dominates everything here cancels, and the positions where the two actors pick
the same ask contribute an exact zero rather than false precision.

Until it lands, the honest statement is: **the champion has measurable one-step
ask headroom (+0.164, excluding zero), and whether the lookahead is the cause is
unmeasured.**

## RESOLVED: the lookahead is not the cause. It changes 36% of asks and none of the one-step value

`results/actor_compare.json`. 129 positions, both incumbents scored on
**identical rollouts** — same positions, same worlds, same continuation policy,
so all three confounds above are held fixed by construction.

| incumbent | regret | ± |
|---|---|---|
| the objective in isolation | −0.0136 | 0.0861 |
| **the champion** | **−0.0142** | 0.0859 |
| **paired difference** (champion − objective) | **−0.0006** | **0.0393** |
| on the 47 positions where they disagreed | −0.0018 | 0.1087 |

**Zero, to a half-width of 0.039.** The two policies are equally good at one-ply
ask selection, and the `+0.1641` against `−0.0188` was an artefact of the
population and the continuation policy — exactly as flagged before it was read.
The claim that would have been easy to publish is false.

### What the same run says about the lookahead, which is worth more

**The two actors chose a different ask in 36.4% of positions and that changed
one-step value by 0.0006 sets.** The lookahead is not a tie-break: it re-ranks
better than one ask in three. Whatever it earns — and it earned +0.104
[+0.020, +0.189] in a 6,000-pair duel — it earns **beyond one ply**, which is
precisely what a possession-chain search is built to do and the first direct
evidence that it does it.

### What remains open, stated narrowly

On the champion's own population with a champion continuation, the regret is
**+0.1641 [+0.0046, +0.3236]**. This run shows the *choice* is not what leaves
it there, so either those positions offer more one-step value to anyone, or the
champion continuation changes what the estimator measures. Separating them needs
`ASK_REGRET_SPEC=champion` on this same two-incumbent design. If both actors
leave +0.16 on champion turf, the headroom is real and belongs to neither
objective — a better ask selector would capture it, and that is a live lead
rather than a closed one.

---

# RESULT: exploitability is negative, and a negative result here says nothing

`results/exploitability.json`. Seat 0 deviates to a rollout best response at
**beam 5 / 6 worlds** against five champions, 240 paired deals, control verified
at exactly 0.000 on every deal:

> **DEVIATION GAIN −0.608 sets per deal, 95% CI [−1.122, −0.095]**, sd 4.06.

The interval now excludes zero — where the earlier beam-3 run gave −0.4875
[−1.244, +0.269] — but **it excludes it on the wrong side**, and the
interpretation was fixed before the run and by the script itself:

> gain ≤ 0 — weak evidence only. PIMC's strategy fusion can make the responder
> play badly, so a failure to find an exploit is not evidence that none exists.

So this establishes **nothing about the champion's safety**. What it does show is
that a perfect-information rollout responder is a *worse* player than the
champion by 0.6 sets a deal, which is a fact about PIMC and consistent with the
v0.3 diagnosis that a search ranking candidates against different sampled worlds
is ranking noise.

**It is not evidence that more search made the responder worse.** The beam-3 and
beam-5 runs used different base seeds and are not paired, and their intervals
overlap heavily. Two unpaired numbers that overlap are one number.

## A note on my own power calculation

I fixed the power before the run and predicted a half-width of **0.437**. The
actual is **0.514**, because I used the per-deal sd of 3.453 from the *beam-3*
run and the beam-5 responder came in at **4.06**, 18% higher. The prediction was
optimistic in exactly the way a power calculation borrowed from a different arm
usually is, and the conclusion is unaffected only because the result landed
nowhere near the bar either way.

Resolving +0.15 on this instrument needs 2,036 deals at the old sd and **2,815**
at the observed one — 48 hours. That is a fact about the instrument, and it means
**single-seat exploitability cannot answer the headroom question at the
precision this project ships on.** The two regret instruments can, and did.

## ANSWERED: the champion's regret belongs to the turf, and both actors face it equally

`results/actor_compare_champion.json`. The same two-incumbent design run with
`ASK_REGRET_SPEC=champion`, so positions and continuation are both the
champion's. 103 positions, identical rollouts.

| incumbent | regret | ± |
|---|---|---|
| the objective in isolation | +0.0728 | 0.1043 |
| the champion | +0.0930 | 0.1061 |
| **paired difference** | **+0.0202** | **0.0736** |
| on the 35 positions where they disagreed | +0.0595 | 0.2182 |

Set beside the same design on objective-only turf:

| turf | objective only | champion | paired difference |
|---|---|---|---|
| objective-only | −0.0136 ± 0.0861 | −0.0142 ± 0.0859 | **−0.0006 ± 0.0393** |
| **champion** | **+0.0728 ± 0.1043** | **+0.0930 ± 0.1061** | **+0.0202 ± 0.0736** |

**The rows move together and the actors do not separate.** Whatever raises the
regret on champion turf raises it for *both* policies by the same amount, and
the paired difference is zero on both turfs — measured twice now, at ±0.039 and
±0.074. **The lookahead does not change one-step ask quality**, and that is as
settled as anything here gets.

## What that leaves, stated as a lead and not a finding

The champion's own regret is **+0.1641 [+0.0046, +0.3236]** in the 162-position
run and **+0.0930 ± 0.1061** here. Both positive; the first excludes zero and
the second does not, and their intervals overlap heavily, so they are one
quantity measured twice with the smaller run noisier. The honest summary is
**weak evidence of a positive one-step regret of roughly +0.09 to +0.16 a
decision for the deployed policy, not caused by its ask choice.**

And "turf" still bundles two things this design cannot separate, because the
champion arm uses champion positions *and* a champion continuation. Splitting
them needs a cross: champion positions with an objective-only continuation. That
is the next measurement if this lead is followed, and it is diagnostic rather
than actionable — no change to the engine follows from either answer without a
duel.

## Where the headroom question ends up

| channel | verdict |
|---|---|
| ask, one ply, objective in isolation | no headroom: −0.0188 [−0.0808, +0.0431], 208 positions |
| ask, one ply, the deployed champion | **weak positive, +0.09 to +0.16, not from the choice** |
| declaration | correct in both directions; declining to declare is right by 1.18 sets |
| single-seat deviation | −0.608 [−1.122, −0.095], and a negative result here is uninformative by construction |

Seven pre-registered attempts to correct this policy have failed and one search
class is closed by proof. The one thread still live is the weak positive above,
and it is weak: two runs, one significant, and no mechanism.

---

# RESULT: the choice model was fitted on the wrong population, and it did not matter

`scripts4/choice_curve.py` measures the propensity exponent behind the opponent
model — the largest single effect in this engine, about 1.9 sets a deal-pair.
Its docstring claimed the curve was measured "for the champion, against a copy
of itself — which is precisely the situation the opponent model is used in".

**That was false.** `SPEC = {"opponent_gamma": 0.35}` is the ask objective in
isolation: no belief-space lookahead, 160 draws. `results/actor_compare.json`
measured those two policies choosing a **different ask in 34–36% of positions**,
so the exponent was fitted to one policy and applied to another. The results
file recorded no spec at all, which is how the figure could be read as the
champion's for as long as it has been.

`fish4/oppmodel.py`'s shipped `ALPHA_*` profile is a quadratic through seven
bands of that same fit, so the defect reached the engine.

## Re-measured on the deployed champion: 300 games, 25,304 decisions

| half-suits resolved | shipped (objective-only) | champion | diff | 95% half-width |
|---|---|---|---|---|
| 0 | 2.000 | 1.883 | −0.117 | 0.206 |
| 1 | 1.280 | 1.201 | −0.079 | 0.227 |
| 2 | 1.200 | 0.968 | −0.232 | 0.292 |
| 3 | 0.680 | 0.703 | +0.023 | 0.314 |
| 4 | 0.300 | 0.513 | +0.213 | 0.331 |
| 5 | 0.410 | 0.519 | +0.109 | 0.431 |
| 6–8 | −0.020 | −0.368 | −0.348 | 0.399 |

**No band differs.** The largest discrepancy is the 6–8 tail at 1.7σ, and every
one sits inside its interval. The decay from ~1.9 to below zero — late asks
carrying no depth signal, then anti-signal — replicates on the correct
population.

Pooled, the exponent moves **1.207 → 1.083, a shift of −0.124 [−0.241,
−0.007]**: marginal, and *toward* the shipped conceptual model of α = 1. On the
champion, α = 1 is only 2.2σ away and worth **9.9 nats over 25,304 records** —
"proportional to depth" is very nearly exactly right on the population the model
is actually applied to.

## What this changes: nothing, and that is the finding

`ALPHA_*` stands. And `gamma_schedule`, which replaces the constant with this
profile, was already duelled at **6,000 pairs: −0.064 [−0.158, +0.029],
`do_not_adopt`** — a null. That duel used this profile, the profile is now
confirmed on the right population, so the refutation stands rather than needing
a re-run against corrected constants.

A wrong-population fit that turns out not to distort its own result is worth
recording precisely because the alternative was assumed rather than checked. The
defect was real, the exposure was real, and the damage was nil.

`CHOICE_CURVE_SPEC=champion` now switches the population, every run prints which
it used, the spec is written into the results file, and the docstring no longer
claims something the code does not do.

---

# RESULT: the feasibility repair is inert against the current champion

`prereg`/task #50 flagged three void-era verdicts the award rule re-prices, and
named one as *"the one adoption decision the flip can plausibly reverse"*: the
feasibility filter, which refuses a declaration no complete deal allows and
repairs it. Its verdict is **+0.0284 [+0.0242, +0.0326]** over 6,000 pairs
against a **+0.05** bar — `do_not_adopt`, and `ClaimConfig.feasibility` is
`False` today.

The reasoning for re-running it is sound on its face: a misdeclaration costs 1
under the void rule and 2 under the award rule, so an intervention that prevents
one should be worth about twice as much, and 0.028 × 2 clears 0.05.

**It does not need re-running, because against the current champion the
intervention does nothing at all.**

`scripts4/path_ledger.py --vs=self --arm=claim_feasibility=1`, 480 games under
the award rule, is **bit-identical** to the baseline — 252 / 1703 / 106 / 99 by
path, 63 wrong, margin +0.0000.

## Not a dead knob — checked, because this project has been burned by exactly that

A bit-identical arm is the shape of a silent no-op, and `fish4/posterior.py`
carries a comment about a `> 0` guard that "made an experiment arm collapse into
another arm and report a bit-identical result — a null that looked like a
measurement". So the knob was instrumented directly rather than trusted:

> `claim_feasibility=True` → `_feasible` called **10,407** times over 20 games,
> returning False **632** times (6.1%). At `False` it is never called.

The filter fires about 32 times a game and changes no action.

## Why: `claim_forced_exhaustive` subsumes it

Both act on the forced path. Turning the exhaustive search off makes the filter
live again:

| arm | forced n | forced wrong | total wrong | margin |
|---|---|---|---|---|
| champion (exhaustive on) | 99 | 41 | 63 | 0.0000 |
| exhaustive **off** | 99 | **48** | 70 | −0.0292 |
| exhaustive off **+ feasibility** | 99 | **40** | 62 | +0.0042 |

Without the exhaustive search the filter removes **8 wrong declarations per 480
games** and recovers **+0.033** — about what the exhaustive search itself is
worth. With it, nothing. They are substitutes, and `claim_forced_exhaustive`
shipped *after* the feasibility verdict was measured.

## What that settles

An intervention that is exactly inert has a margin of exactly zero under **any**
misdeclaration rule, so the award-rule flip cannot reverse this adoption
decision. #50's item (2) is closed without spending 6,000 pairs, and the reason
is not that the doubling argument was wrong — it is that a later change made the
intervention a no-op before the argument could apply.

It also independently confirms `claim_forced_exhaustive` does what #64 claimed:
on its own it cuts forced-path errors from 48 to 41 per 480 games.

Items (1) the free-signalling duel and (3) the perpetual/analytics misdeclare
rates remain open under #50.

# #49 — the endgame ask correction does not come back, and the screen that shipped it was noise

`fish4/registry4.py` withdrew `endgame_d_info = +2.0` from the deployed config
on the award-rule flip, "pending a refit of `scripts4/ii_ask_fit.py` against
award-rule targets". The targets are recollected and the refit is run. It does
not bring the knob back — and it turns up something worse about how the knob was
chosen.

## The three fits

Same code, one journal, three row sets. `scripts4/ii_ask_targets.py` fingerprints
rows by rule, so the void era and the award era can be fitted separately rather
than pooled by accident.

| rows | rule | games | grid's `info` | held-out gain over champion |
|---|---|---|---|---|
| 388 | void | 79 | **+2.00** | +0.0092 [−0.0282, +0.0467] |
| 457 | award, held to the same 79 games | 79 | **−1.00** | +0.0142 [−0.0118, +0.0403] |
| 764 | award, all | 156 | **+0.10** | −0.0011 [−0.0033, +0.0011] |

The void row reproduces the archived fit to the digit under current code, so the
change between rows 1 and 2 is the rule and not code drift.

**The sign reverses.** Holding the deal population to the same 79 games, the
grid's pick moves from +2.00 to −1.00. Over all 156 award games it collapses to
+0.10 with an interval that excludes any gain worth having.

**The scale family replicates**: `k = 1.0` under both rules. De-weighting the
success probability does not help. That half of the original diagnosis stands.

## The part that is not about this knob

`info = +2.0` was nominated for a 4,000-pair duel on a held-out gain of
**+0.0092 [−0.0282, +0.0467]**. The prereg quoted the estimate — "+0.0093 in
half-suit units" — and no interval, because the ladder did not compute one.

The duel stands. It was pre-registered, run as written, and +0.0835 [+0.0338,
+0.1332] is a true fact about the void rule. What was wrong is upstream: the
screen that decided where to spend the pairs could not tell its winner from
zero, and the arm won an honest play test anyway.

`scripts4/ii_ask_fit.py` now prints a game-clustered paired interval on every
rung. Under that instrument **every rung of every fit straddles zero**,
including the one that shipped.

This was not a subtle statistical error. Clustering by game is the right thing
— positions inside a game share a deal, and the analytic interval agrees with a
20,000-draw cluster bootstrap ([−0.0282, +0.0467] against [−0.0257, +0.0449])
— but it was not what would have saved this. The naive interval that treats all
206 held-out positions as independent is [−0.0222, +0.0407], and it straddles
zero too. **Any** error bar would have caught it. There was none.
`tests4/test_paired_gap.py` pins the instrument.

## Standing rule

An offline screen nominates an arm for a duel only if its held-out gain has an
interval excluding zero, clustered by whatever unit shares a deal. A point
estimate is not a nomination.

By that rule the runner-up is refused too: `certain = −0.50` scores +0.0286
[−0.0137, +0.0709] void, +0.0078 [−0.0299, +0.0454] matched, +0.0072 [−0.0219,
+0.0363] over all award games. #49 closes with the correction withdrawn
permanently and **no successor arm**.

## Three instrument fixes this needed

* `ii_ask_fit.py` chose its rule era by **majority vote** over the journal and
  said nothing about it. It now prints the full inventory, takes
  `II_ASK_FIT_FP` to name an era, and `II_ASK_FIT_GAMES_FROM` to hold the deal
  population fixed across eras.
* It wrote `results/ii_ask_fit.json` under a fixed name, so the second era's fit
  silently overwrote the first's — the same failure `path_ledger` had with two
  arms and one filename. The fingerprint is in the filename now.
* Void-era rows carry 11 feature columns and award-era rows 13. The fit cuts
  every model to the rows' own width and **asserts** that each dropped term
  carries zero champion weight, so rung 0 is provably the same policy either
  way. Without that it raised a `matmul` dimension error, which is the good
  outcome; silently broadcasting would have been the bad one.

# "162 positions" is 8 deals — every one-step regret interval was too narrow

Found while pairing the #82 turf comparison. `scripts4/ask_regret.harvest`
walks games in order and emits **every** qualifying ply, returning as soon as it
has enough. So a run reported as *162 positions* is 162 consecutive plies drawn
from **8 deals**, sampled 20–40 deep. The positions inside one deal share the
hands, the history and every earlier decision. Every interval this instrument
has published divided by 162 rather than by 8.

The deal boundaries are recoverable without re-running anything: `history` (the
event count) rises within a deal and drops at the next. That rule was checked
against the harvest's own game index on 260 positions under both harvest
policies and recovers **every** boundary exactly, so the correction below is a
computation on the existing files, not an estimate.

## Two mistakes, not one

Fixing the count alone would have replaced one too-narrow interval with
another. Cluster-robust variance is asymptotic in the **number of clusters**,
and these runs have three to ten deals — so the standard error has to be paired
with a *t* critical value at `k − 1` degrees of freedom, not 1.96. At six
clusters that is a 31% difference, at four 62%, at three 61% again on top of a
much larger standard error. `fish4/clustered.py` does both together, and every
instrument now routes through it.

| run | as published | clustered by deal, t at k−1 df | deals |
|---|---|---|---|
| `ask_regret_wide` (objective) | −0.0188 [−0.0808, +0.0431] | −0.0188 [−0.0951, +0.0575] | 8 |
| `ask_regret_champion_wide` | **+0.1641 [+0.0797, +0.2484]** | **+0.1641 [+0.0046, +0.3236]** | 8 |
| `ask_regret_champion` | −0.0893 [−0.2535, +0.0749] | −0.0893 [−0.7109, +0.5323] | 3 |

**No conclusion reverses, but one comes very close.** The champion's positive
one-step regret still excludes zero — by **+0.0046**, against a published lower
bound of +0.0797. Its interval is **1.89×** wider than published. The
70-position run is really 3 deals and its interval is **3.78×** what was
quoted. Those are the numbers from here on.

`ask_regret.py` now records the deal on every row and reports both intervals,
the clustered one labelled as the honest one and annotated with its degrees of
freedom. `harvest` gained a `games_out` out-parameter rather than a wider return
tuple, so no existing caller changed.

**What is not affected:** duplicate-deal duels. `duel.py` pairs on the deal and
treats the pair as the independent unit, and `fish4/match.py` already used a *t*
critical value for the pair count — that discipline was right from the start,
and it is why the duel results, including the ones this project ships on, do not
move.

# #82 — the one-step regret is the turf, and the turf is the positions

Two runs read side by side once said the lookahead makes one-step ask selection
worse: the ask objective alone at −0.0188 and the deployed champion at +0.1641.
`scripts4/actor_compare.py` exists because those runs differ in three ways at
once — the positions harvested, the continuation that scores them, and whether
the acting and evaluating posteriors agree. It scores **both actors on one set
of positions, one set of worlds and one set of rollouts**.

Run as a 2×2 over the two remaining confounds, every interval clustered by deal
with the *t* correction:

| harvest | continuation | pos | deals | champion − objective | champion-actor level |
|---|---|---|---|---|---|
| objective | objective | 129 | 5 | −0.0006 [−0.0409, +0.0396] | −0.0142 [−0.1837, +0.1553] |
| objective | champion  | 110 | 4 | +0.0417 [−0.0439, +0.1273] | +0.0220 [−0.1366, +0.1806] |
| champion  | objective | 125 | 6 | −0.0087 [−0.0843, +0.0669] | +0.0753 [−0.0731, +0.2238] |
| champion  | champion  | 103 | 5 | +0.0202 [−0.0465, +0.0870] | +0.0930 [−0.0655, +0.2516] |

## The actors do not separate, in any cell

Four paired differences, all straddling zero, the tightest at **±0.041**.
Pairing is the sharp end of the design: both actors see the same position and
the same worlds, so the deal effect cancels inside the pair, and the paired
intervals stay close to their naive versions (±0.041 against ±0.039) while the
unpaired levels beside them widen by half again. **The lookahead does not change
one-step ask quality** — its +0.104 duel win is earned beyond one ply, not at
it.

## The continuation is measured and null

The two cells sharing a harvest draw the *same positions* — 110 and 103 matched
indices, every one with the same legal-ask count, checked rather than assumed —
so the continuation effect is paired:

* objective harvest, 110 positions over 4 deals: **+0.0545 [−0.2373, +0.3464]**
* champion harvest, 103 positions over 5 deals: **−0.0218 [−0.1654, +0.1217]**
* pooled, 213 positions over 9 deals: **+0.0176 [−0.1010, +0.1362]**

Which policy plays the continuation does not move one-step regret.

## The positions are what is left, and they are not settled

The position distribution cannot be paired — it *is* the factor:

* at the objective continuation: **+0.0895 [−0.1358, +0.3149]**
* at the champion continuation: **+0.0711 [−0.1532, +0.2953]**
* pooled main effect: **+0.0803 [−0.0786, +0.2393]**

Positive under both continuations, and straddling zero under both. The two main
effects are not on the same footing and the ratio between their point estimates
is not worth quoting: the continuation effect is paired and measured at ±0.118,
the positions effect is unpaired and measured at ±0.159 around a larger centre.
What the 2×2 supports is an **elimination** — not the ask choice (four paired
nulls, tightest ±0.041), not the continuation (a paired null over 9 deals) —
leaving the position distribution as the only factor with a positive estimate
under both conditions. Its size is a lead, not a finding, and by the standing
rule recorded under #49 it does not get quoted as one.

## Why it was not settled by spending more

Priced before deciding, from the measured per-position sd on each turf (0.498
and 0.613) at 54 s a position: **±0.09 needs 296 positions a turf (8.9
CPU-hours), ±0.07 needs 489 (14.7 hours), ±0.05 needs 959 (28.8 hours)** — and
±0.07 still touches an effect of +0.080. Deal clustering makes it worse than
that, because the binding count is deals and not positions, and 320 positions a
turf would still be about a dozen deals. A run was started at that size and
stopped once the arithmetic was done: no engine change follows from either
answer without a duel, so this is a diagnostic, and 15–30 CPU-hours is the wrong
price for one.

`actor_compare` now records the deal on every row, so the next turf comparison
can pair by deal instead of paying for the variance.

# #50 item (3) — the perpetual/analytics table does not move under the award rule

`scripts4/perpetual_study.py` was **pinned** to `wrong_distribution_outcome="null"`
with a comment saying its statistics "are about nulls/void outcomes, which the
opponent-award baseline cannot produce". That is true of the *outcome* and false
of the *event*: a team holding all six and naming the wrong split happens under
both rules, and only its consequence differs.

Fixed the right way round — the rule is a parameter, and the counter classifies
the event (`ClaimEvent` whose winner is not the claimer's team, with every
revealed card on that team) exactly as `fish4/match.py` already did for
`x_misdeclares`. Each run cross-checks itself: under `"null"` the voided count
must equal the classified count, and under `"opponent"` nothing may void. Both
assertions hold.

**Replayed on the same 200 seeds, the two rules agree on every field of the
table**, `mean_plies` to the decimal included — 0.275 / 0.275 / 0.220 events per
game across the three arms, 200/200/200 games with a repeated position, 4.24% of
plies fully dead, 110 games with an unplaceable set, the 23.4%-vs-0.92% stuck
split. The only divergence is the void-only cross-check counter, which reads
0.275 under the void rule and 0 under the award rule, exactly as it must.

## Not assumed — the knob was instrumented

Play being identical under two rules is the shape of a knob that does nothing,
and `fish4/claim4.py` genuinely reads this one: `forced_claim` sets
`loss_split = -1.0` under the award rule and `0.0` under the void rule, which
turns the split ranking from `p_exact` into `p_exact + p_team`. So it was
counted rather than reasoned about (`scripts4/rule_bite.py`, 800 games of
champion self-play):

> `forced_claim` called **284** times; all 284 had a candidate with
> `p_split > 0`, so the term is live. The two rules **ranked differently 0
> times** and **returned a different claim 0 times**. 166 of the 284 offered
> only one candidate split at all.

The rule reaches exactly one decision in this engine, it is arithmetically live
at every one of them, and it changes none. The paper's caption said the row
"would read as misdeclarations per game" under the award baseline; it now says
so as a measurement.

That closes #50. Item (1), the free-signalling duel, was re-priced under the
award rule as design R5 — **+0.068 [−0.033, +0.169]** over 500 pairs, 109
misdeclarations against 138, which is the registered "CI straddles zero: it
stays off, reported with its interval and the misdeclare split". Item (2) closed
earlier: the feasibility repair is exactly inert against the current champion,
so no rule can re-price it.

# #83 — the audit: which other intervals divided by positions?

`scripts4/cluster_audit.py` recovers the deal index for the archived files — by
replaying the harvest, which reproduces them exactly — and reprints each
headline beside its published version. `min_resolved` is part of a harvest's
identity: `rollout_target` uses 4 and `ask_regret` uses 5, and the first version
of this audit passed 5 to both, which silently recovered the wrong deals for
three files while every count still looked plausible.

| instrument | clustering unit as published | deals behind it | verdict |
|---|---|---|---|
| `ask_regret*` | positions | 3–8 | **fixed**; champion regret 1.89× wider, still excludes 0 at +0.0046 |
| `actor_compare*` | positions | 4–6 | **fixed**; all four paired cells straddle either way |
| `declare_regret` | positions | 4 | **restated**; see below |
| `rollout_target*` | positions (110 of them) | **4** | **restated**; slope 2.33× wider, still excludes 0 |
| `ii_ask_fit` | games | 38–79 | already right; the *t* correction moves it by ~1% |
| `duel_depth_base_rate`, `retake_bonus_base_rate` | duel pairs | n/a | **not affected** — the interval is over pairs, the correct unit. Only the conditional sd they feed on is estimated from clustered positions |
| `duel.py` / `fish4/match.py` | duplicate-deal pairs | n/a | **not affected**, and already used a *t* critical value at the pair count |
| `learn_ask_objective` | positions (CR1) | not recovered | one level short, same as `rollout_target`. Its verdict was a **2,000-pair duel** (`results/learned_weights_verdict.json`), so no published conclusion rests on its offline standard errors — but a future fit should cluster on the deal |

## declare_regret, restated

| figure | published | clustered by deal (4) |
|---|---|---|
| regret, all positions | +0.1101 ± 0.1173 | +0.1101 ± 0.1339 |
| regret where it asked | +0.1607 ± 0.1241 | +0.1607 ± 0.1433 |
| regret where it **declared** (n=11) | −0.3409 ± 0.2338 | **−0.3409 ± 0.4402** — now straddles zero |
| best claim − best ask, when it asked | −1.1849 ± 0.1266 | **−1.1849 ± 0.1051** |

**The one reversal in this whole audit is the declared arm**: 11 positions from
4 deals, and it no longer excludes zero. The claim it supported — "when it
declares, it is right to" — is withdrawn above.

The load-bearing figure is the last one — it is what refuted the "too slow to
declare" story behind four earlier directions — and it *tightens*, because it
is a within-position contrast whose deal effect cancels. The same pattern as
the paired actor cells: pairing survives clustering, levels do not.

## rollout_target, restated

The slope of rollout value on `p_success` is **+0.681**, published as
[+0.4005, +0.9615] over "110 positions". Those 110 positions are **4 deals**,
and the interval is [+0.0269, +1.3352] — **2.33× wider**, still excluding zero.
Its two public-continuation siblings straddled zero before and after.

The paper quoted four slopes from this run with position-clustered standard
errors, and all four are restated. **None reverses.**

| slope | published | deal-clustered | ratio |
|---|---|---|---|
| `expose` | +1.807 ± 0.359 | +1.807 ± 0.536 | 1.48× |
| `deplete` | +1.387 ± 0.224 | +1.387 ± 0.249 | 1.10× |
| `certain` | +0.919 ± 0.169 | +0.919 ± 0.223 | 1.30× |
| `P(success)` | +0.681 ± 0.142 | +0.681 ± 0.207 | 1.45× |

The joint-fit column (`P(success)` at −0.329 ± 0.264, VIF 13.5) is left as
published, because the sentence after it in the paper says that column should
not be read at all — restating a standard error nobody may use would be
decoration.

`centred_slope` now clusters on the deal where the rows carry one and prints a
warning to stderr when they do not, instead of silently reporting the tighter
number. `rollout_target.gather` records the deal on every row.

## What the two mistakes have in common

Both are the same error at different depths: **counting rows as if they were
independent draws**. Dividing by 162 positions instead of 8 deals, and pairing
a 4-cluster standard error with 1.96 instead of *t* at 3 df, are the outer and
inner versions of it. `fish4/clustered.py` does both at once precisely so that
fixing one without the other cannot happen again, and
`tests4/test_clustered.py` pins each.

# The paper did not compile, and the script that builds it named the wrong file

Found by running `pdflatex` after editing `paper/kraken.tex`, which
`scripts4/check_tex.py` had just declared clean.

## Three defects, each of which looked fine

**1. `check_tex` passed a file that does not build.** The caption rewritten for
#50 item (3) used `\path{}` four times. `\path` expands to `\url`, which is
**fragile in a moving argument**, and `\caption` writes its argument to the list
of tables. The build died with `! Undefined control sequence. \Url Error ->\url
used in a moving argument` — reported at the caption's *closing brace*, five
lines after the last offending command.

The repository's own convention is `\texttt{...}` with escaped underscores in
captions and `\path{}` in body text, and every other caption already followed
it. `check_tex` now scans each `\caption{...}` by brace-matching and flags
`\path`, `\url` or `\verb` inside one; `tests4/test_check_tex_fragile.py` (6
tests) checks that it fires on the real regression, stays quiet on `\texttt` and
on `\path` in body text, and does not run past a caption containing nested
groups.

The checker's docstring now says what it is: **not a substitute for a build.**
It was written when the machine had no TeX. The machine has `pdflatex`.

**2. `paper/build.sh` still named `fishbot_v06.tex`** — stale since the KRAKEN
rename. The script that produces a *committed deliverable* pointed at a file
that does not exist, and nothing noticed because nobody had run it since.

**3. The committed PDF was a day stale.** `paper/kraken.pdf` last changed at
`fe1a85b` (2026-08-29); `kraken.tex` has changed repeatedly since, including
today. 773,452 bytes committed against 802,704 rebuilt.

Rebuilt through the repaired script — three passes, as its own comment
requires: **91 pages, 0 undefined references or citations.**

## The pattern

A structural checker that reports "no structural problems found" is the same
shape as a knob that produces a bit-identical result: it is what a *silent
no-op* looks like from the outside. This project has a rule for that case —
instrument the thing directly rather than trusting the summary — and it applies
to its own tooling. `check_tex` is cheap and worth keeping, but the load-bearing
check is `bash paper/build.sh`, and it now works.

---

# UPDATE, 2026-08-31: the convention's numbers had no file, and re-running them found something better

Two defects in this direction, one bookkeeping and one substantive.

## The strongest claims in the direction were backed by nothing

`f8abe6d` recorded the aimed replication and the locating book's outcome, and
touched three files: two pre-registrations and a duels JSONL. **No results
file.** `-0.0535`, `+0.0392`, `-0.0315`, `+0.0408` existed in this repository
only as prose in a prereg and a commit message, and could not be re-derived by
anyone, including me. `results/convention_posterior.json` is the *exploratory*
560,000 run, which `prereg/convention_aimed.md` exists to say is superseded.

That is `scripts4/unwatched_claims.py`'s finding one layer below the paper: the
numbers a document repeats most are the ones nobody re-derives. It is now
closed --- `results/convention_replication.json` holds five sender settings on
one engine at one seed base --- but it was open for two days across the two
documents that license the whole direction.

`fish4/convention.py` had the matching defect in code: it still stated the
retracted "aiming came out neutral, so the book trades a locating signal for a
counting one" theory as established fact, in a comment block that used it to
motivate the locating book defined immediately below. Every other copy of that
theory in the repository sat under an explicit retraction banner. The code was
the one place a reader would meet it as a finding.

## Re-running it: the conclusion holds, the magnitudes are down a third

At the same seed base 880,000, the aimed book clears all three pre-registered
conditions again --- but NLL at `beta = 0.8` is **-0.0382** where **-0.0535**
was recorded, and top-1 **+0.0260** where **+0.0392** was.

The exploratory 560,000 arm, whose file *is* committed, was re-run as a control
to find out why. Identical seeds, identical `n_games`, byte-identical stored
spec:

| | committed 08-29 | re-run 08-31 |
|---|---|---|
| scored decisions | 1,074 | 1,023 |
| **baseline** teammate NLL | 1.3995 | **1.3567** |
| paired NLL at `beta = 0.8` | -0.0712 | -0.0403 |

Eleven engine commits landed in between and the baseline is 0.043 nats
stronger. Every number in this direction is therefore measured against a target
this project is deliberately moving, and the marginal arms have already crossed
over: `flat 2.0` has gone from -0.0342 to **+0.0252**, significantly harmful
where it was significantly helpful.

**What is NOT said here, and was, for about an hour.** This paragraph read
*"the decode did not get worse; the belief it decodes into got better ... a
channel is worth what the receiver could not already work out."* That is
withdrawn. It was an explanation for two points on two engines, and it was
registered and tested the same day --- see the update below. **It is refuted on
the nearest axis available**, and the drift itself is now measured, real and
unexplained.

## The locating book no longer supersedes, by its own rule

`prereg/convention_locate.md` fixed condition 2 in advance: the locating book
supersedes only if its best passing arm's top-1 is at least as good as the
aimed depth book's. On today's engine, best locate arm **+0.0227** against
aimed **+0.0260** --- it fails, and against the literal bar the amendment wrote
down (+0.0351) it fails by more. Both gates of `prereg/convention.md` still
pass, so it is not refuted as a channel; it simply never beat the aimed depth
book by more than noise in either direction, and its apparent win came from a
run that no longer reproduces.

## What the re-run found that the original could not

The unaimed control was run at the *matched* gate, which the original comparison
never was. It gives a direct A/B where the sender's price, the seeds, the
engine, the arm and the instrument are identical and the only difference is
where the message points:

| gate 0.05, `beta = 0.8` | paired NLL | paired top-1 |
|---|---|---|
| depth, **unaimed** | -0.0284 [-0.0345, -0.0223] | **-0.0086** [-0.0161, -0.0010] |
| depth, **aimed** | -0.0382 [-0.0466, -0.0299] | **+0.0260** [+0.0164, +0.0356] |

**The NLL barely separates them. The top-1 changes sign.** Across all five
settings, every book that aims lands top-1 between +0.020 and +0.026; neither
book that does not aim clears +0.007. And the NLL column does not order them
that way at all --- unaimed at gate 0.10 (-0.0358) beats both locating books on
the proper score while losing to both on the argmax.

So aiming does not buy a generally better belief. **It buys the argmax
specifically, and a proper score is close to blind to it.** Which is also the
best explanation for why aiming was mistaken for a null for as long as it was:
the first number anyone reads is the NLL, and on the NLL there is not much to
see.

## The pattern

A retracted theory survived in the one place nothing checks --- a code comment
--- while every document that could be searched for it carried the retraction.
And the run that refuted it wrote no file, so the refutation was as
unre-derivable as the claim. The fix for both is the same: put the number where
something can read it back, and re-run before quoting. The re-run cost twenty
minutes and produced a sharper result than the original had.

---

# UPDATE, 2026-08-31: I registered my own explanation and it was refuted in an hour

The previous update explained a shrinking effect with a sentence I liked:
*a message is worth only what the receiver could not already work out.* Two
points, two engines, eleven commits apart. It went into three files.

It is the same shape as the aimed book's own retracted "neutral" reading --- a
mechanism built on one underpowered comparison --- so it was registered
(`prereg/channel_vs_precision.md`) and swept before it could be repeated a
fourth time. **REFUTED**, by the rule fixed in advance.

## The sweep

Scoring `n_draws` on **fixed transcripts**: a better-sampled belief on the same
1,068 decisions, model unchanged. 40 games, seed base 880,000, sender gate 0.05
aimed, `beta = 0.8`, clustered on the game.

| `n_draws` | baseline team NLL | paired team NLL |
|---|---|---|
| 180 | 1.3155 | **-0.0064** [-0.0217, +0.0090] |
| 360 | 1.3004 | -0.0300 [-0.0444, -0.0156] |
| 720 | 1.2919 | -0.0382 [-0.0538, -0.0227] |
| 1440 | 1.2930 | **-0.0436** [-0.0593, -0.0279] |

    D = d_1440 - d_180 = -0.0372 [-0.0481, -0.0263]   over 40 game clusters

Entirely below zero. **The gain grows as the belief improves.** The 720 cell
reproduced `results/convention_replication.json`'s -0.0382 to **0.0000**, so
this is not a different instrument measuring a different thing.

## The finding is better than the refutation

**The baseline saturates and the gain does not.** From 720 to 1440 the baseline
gets no better (+0.0011, noise) while the gain still grows -0.0382 -> -0.0436.
So the gain is not tracking what the receiver already knows.

At 180 draws there is **no channel at all** --- an interval covering zero --- on
the same transcripts where 1440 draws gives -0.0436. The message is byte-for-
byte identical in all four cells.

> **AMENDED an hour later, and the reason is the next section.** This passage
> continued: *"It tracks how many sampled worlds the decoder has to reweight ...
> only the number of worlds it can act on differs."* That is withdrawn too.

The opponent pool makes the same point louder, with a **sign change**:

| `n_draws` | paired **opponent** NLL |
|---|---|
| 180 | **+0.0435** [+0.0287, +0.0582] |
| 720 | +0.0025 [-0.0033, +0.0082] |
| 1440 | **-0.0086** [-0.0135, -0.0037] |

Decoding a teammate's message into a small world-sample **actively damages** the
opponent-side belief, significantly, and stops doing so once there are enough
worlds. Reweighting few worlds by one fact distorts the rest of the joint.

## A caveat this hands to every convention number in the project

The engine ships at **`n_draws = 480`**. Every belief figure in this
direction --- the depth book, the aimed book, the locating book, both results
files --- was scored at **720**, because `gamma_split.py` fixed it there and the
convention instrument imported the constant.

That was first written here as an interpolation --- "roughly 15%, about -0.033"
--- and then **measured**, because an interpolation standing in three documents
when the measurement costs four minutes should not stand. A descriptive run
with 480 added to the grid gives **-0.0368** [-0.0523, -0.0213] against -0.0382
at 720: **4%**, not 15%. The curve flattens well before 720 and a straight line
between the 360 and 720 cells could not see it.
`results/channel_precision_shipped.json`, marked `registered: false` because a
different grid is not the registered test.

So "these numbers are quoted at 1.5x the sampler precision the engine uses" is
a fact about all of them that nobody had --- and it is worth a few per cent, not
a sixth. The four cells the descriptive run shares with the registered one came
back bit-identical, which is what the per-decision seeding is for.

### The audit that follows, and it comes back clean

If a paired belief effect depends on `n_draws`, then two instruments scoring at
different precisions cannot have their magnitudes compared, and this project has
at least two: `gamma_split.py` and the convention instruments at **720**,
`unlocated_belief.py` at **480**. So: does any standing claim actually compare
across them?

**No.** Every belief results file already records its own `n_draws` in the
payload --- checked, all five --- and the one cross-instrument reference in this
document, `gamma_team`'s refutation cited beside `unlocated_now`'s, compares
*directions* ("better NLL, worse top-1") and not magnitudes. A direction is a
sign and survives a precision difference.

Recorded as a clean negative rather than left as an implied problem. What was
genuinely missing is that **nothing printed the precision beside the table**, so
a reader had to open a JSON file to find out whether two runs were comparable.
`gamma_split.py`, `unlocated_belief.py` and `convention_posterior.py` now print
it in their summary header with the warning attached. The hazard is real, the
data to detect it was always there, and no result depended on it.

## What it does not say

It does not explain the drift. That was a **model** change over eleven commits;
this sweeps **sampler precision**. The registration said so before the numbers
existed, so the limit is not being discovered now to make the result look
tidier. The drift is measured, real, and unexplained --- and this run supplies a
competing hypothesis for it that cannot be checked, since eleven commits could
have changed how many *effective* worlds the sampler produces as easily as they
changed the belief's quality, and the old engine is not available to ask.

## The pattern

The claim was mine, an hour old, already in three files, and refuting it cost
one registration and a four-minute run. The reason it got tested rather than
repeated is that it had the recognisable shape: a tidy mechanism, asserted from
the smallest number of points that could suggest it, in the sentence most likely
to be quoted. That shape is now the trigger, and it has fired four times on this
branch --- the aimed book's "neutral", the locating book's motivation, the
unlocated covariate's transfer, and this.

---

# UPDATE, 2026-08-31: the replacement explanation lasted an hour, and it is also refuted

The section above refuted "the channel is worth less against a better belief"
and replaced it with "the gain tracks how many sampled worlds the decoder has
to reweight". **Same day, same treatment, same outcome.**

The duller competitor the sweep could not distinguish: *any* paired difference
between two beliefs may grow with draws, because at low precision both
marginals are coarse and there is less room for the arms to differ. That would
make it a property of the instrument, true of everything, and not a fact about
code books. Registered in `prereg/precision_generality.md` and swept.

## An unrelated, opposite-signed arm grows too

`w_unlocated = -4.0` against the incumbent, on the champion's own transcripts,
no message involved anywhere. Its effect is a **harm**, so a shared mechanism
has to explain a harm growing as well as a gain growing.

| `n_draws` | baseline team NLL | paired team NLL (+ is harm) |
|---|---|---|
| 180 | 1.2972 | +0.0371 [+0.0293, +0.0448] |
| 480 | 1.2728 | **+0.0422** [+0.0339, +0.0505] |
| 1440 | 1.2658 | +0.0465 [+0.0376, +0.0553] |

    D = d_1440 - d_180 = +0.0094 [+0.0016, +0.0172]    k = 40 games

Entirely above zero. **INSTRUMENT PROPERTY**, by the rule fixed in advance.
Growth-with-draws is not about code books.

The 480 cell reproduced `results/unlocated_belief.json`'s **+0.0422** to
**0.0000**. Both sweeps today landed on their anchor to four decimals, which is
the only reason either contrast is worth reading.

## The size difference, which is a lead and not a third mechanism

| | 180 draws | 1440 | growth | as % of its own end effect |
|---|---|---|---|---|
| aimed code book | -0.0064 (null) | -0.0436 | **0.0372** | **85%** |
| `w_unlocated = -4.0` | +0.0371 | +0.0465 | **0.0094** | **20%** |

The channel grows **4x** what the unrelated arm does, and four times more again
as a share of where it ends. Something beyond the shared instrument effect is
happening to it.

**That is not allowed to reinstate the sentence.** The registration asked one
question and got one answer, and a size difference noticed afterwards is the
post-hoc rescue pre-registration exists to refuse. It is recorded as a lead.

## The caveat that survives, and grew

Every convention belief figure was scored at `n_draws = 720`; the engine ships
at **480**. This run adds the other half: `results/unlocated_belief.json` was
written at **480** while the convention files were written at **720**, so those
two directions were **never scored at the same precision** and their magnitudes
were never directly comparable. Nobody had noticed, because `N_DRAWS` is a
module constant in two different instruments and neither prints it next to a
result.

## The pattern, and it is now the whole shape of this branch

Three explanations were offered today for one drift. Two were registered and
refuted within an hour of being written; the third was never offered, because
by then the rule was clear:

1. *the belief improved, so the message is worth less* --- refuted, the gain grows;
2. *the decoder has more worlds to reweight* --- refuted, an unrelated arm grows too;
3. --- nothing. The drift is measured, real, and **unexplained**, and that is
   where it stays until something measures it rather than explains it.

Both refutations cost one registration and a four-minute run. The expensive
part was never the experiment; it was noticing that a sentence I liked had
arrived without one.

---

# UPDATE, 2026-08-31: there is no plateau, and that changes what a belief number is

The precision sweep stopped at 1440 because that is where the registered grid
stopped. The obvious question it left is whether the effect had converged there,
and it had not. Extended descriptively to **2880** --- six times the precision
the engine ships at --- `results/channel_precision_plateau.json`:

| `n_draws` | baseline team NLL | paired team NLL |
|---|---|---|
| 180 | 1.3155 | -0.0064 |
| 360 | 1.3004 | -0.0300 |
| 480 | 1.2968 | -0.0368 |
| 720 | 1.2919 | -0.0382 |
| 1440 | 1.2930 | -0.0436 |
| **2880** | 1.2908 | **-0.0493** |

Each step tested as a **paired contrast** clustered on the game, because
comparing two intervals by eye is what the per-decision rows exist to avoid:

    d_360  - d_180  = -0.0236 [-0.0346, -0.0126]   SIGNIFICANT
    d_480  - d_360  = -0.0068 [-0.0144, +0.0008]   covers zero
    d_720  - d_480  = -0.0015 [-0.0066, +0.0037]   covers zero
    d_1440 - d_720  = -0.0053 [-0.0089, -0.0018]   SIGNIFICANT
    d_2880 - d_1440 = -0.0057 [-0.0080, -0.0034]   SIGNIFICANT

**The last step is significant.** The effect is still growing at 2880 draws,
and the baseline it is scored against has been flat since 480
(1.2968, 1.2919, 1.2930, 1.2908 --- noise). So this is not the belief improving,
and there is no convergence anywhere in the measured range.

## What that does to every belief figure in this project

It means **"the aimed book is worth -0.0382 nats" is not a property of the aimed
book.** It is a property of *(the aimed book, 720 draws)*. Quote it without the
second half and it reads as a measurement of an intervention when it is a
measurement of an intervention *and an instrument setting* --- one that can be
made 29% larger by changing the setting alone, on the same transcripts, with the
same message.

At the precisions this project actually uses, **75--78% of the 2880-draw value
is present**, so nothing recorded is badly attenuated and no result changes. The
severe attenuation is at 180 draws (13%), which nothing uses. That is the
reassuring half and it is worth stating plainly, because the alarming half ---
no asymptote --- is easy to over-read.

## Deliberately not explained

Two explanations for the precision dependence were offered today, registered,
and refuted within an hour of being written. A third is available: the
convention's term can only separate worlds of the *same depth* that place cards
differently, and the instrument already measures how rare that is --- V2
discrimination at **8.2%** of asks as registered, 31.3% among live ones --- so a
small discriminating subpopulation would need many draws before it is
represented at all.

That is a hypothesis, it is **untested**, and it is written here as one sentence
rather than a section for exactly the reason the two before it were wrong. What
would test it is a book whose term discriminates on every ask rather than on
8%; whether that is worth building is a separate question from whether this
story is true.

## The shape of the finding

An off-policy belief instrument's magnitudes are not converging on a true
effect. They scale with how many worlds you pay to sample, without bound in the
range anyone would run. A null on such an instrument is therefore a statement
about a budget as much as about a hypothesis --- and the only reason that is not
a problem for anything recorded here is that the budget happened to sit above
the steep part of the curve.

---

# UPDATE, 2026-08-31: the drift was never drift. The gate was re-priced.

Three explanations were offered today for why the aimed code book measured
-0.0712 two days ago and -0.0403 on a re-run at identical seeds. Two were
registered and refuted. The third was written down as untested.

All three were wrong in the same way: **they explained a change in the world
when the change was in the label.**

## Bisected, because "unexplained" is a fact you can go and get

A git worktree per candidate commit, with **today's** instrument copied in so
the engine is the only variable, running the configuration that produced the
original file: 40 games, stride 4, sender `0.05 aimed`, seed base 560,000.
`results/convention_drift_bisect.json`.

The gate that makes it worth reading: **the probe at `1a96689` reproduces
`results/convention_posterior.json` exactly** --- 1,074 decisions, base 1.3995,
flat 0.8 **-0.0712**. Without that the bisect would be measuring something else.

| commit | | V1 carry | decisions | baseline | flat 0.8 |
|---|---|---|---|---|---|
| `1a96689` | origin | **72.0%** | 1,074 | 1.3995 | **-0.0712** |
| `6d75ec4` | **sender gate re-priced** | **57.8%** | 1,023 | 1.3567 | **-0.0403** |
| `5c0b4c1` | teammate ceiling | 57.8% | 1,023 | 1.3567 | -0.0403 |
| `5936bf6` | the `locate` term | 57.8% | 1,023 | 1.3567 | -0.0403 |
| `f383516` | the calibration gap | 57.8% | 1,023 | 1.3567 | -0.0403 |
| `9cf986d` | one version | 57.8% | 1,023 | 1.3567 | -0.0403 |

**One commit. Ten others move it by nothing at all.**

## What that commit did

`6d75ec4` replaced

    cost = encode_cost(marg, hand, hs, opps)      # a drop in P(success)

with

    cost = scores[pick] - scores[best_enc]        # the ask objective's units

against the same threshold, `convention_max_cost`. It was the right fix --- the
old gate was paying a third of the objective for a message it believed cost
0.009, and the duel found it. But it means **`gate 0.05` denotes two different
senders**, and -0.0712 and -0.0403 were never two measurements of one thing.
The carry rate is the signature: 72.0% of our asks carried the message before,
57.8% after. Fewer messages on the wire, different cards named, different
transcripts, and a baseline that is not *better* --- it is a **different set of
positions**.

## The check that could not catch it, which is the part to remember

Before running either sweep I compared the two runs' stored `spec` and found it
**byte-identical on all seven keys**, and said so in three places as evidence
that nothing about the configuration had changed.

It was true and it was useless. `convention_max_cost` is not in that spec ---
the instrument sets it --- and what moved was not its **value** but its
**units**. A configuration fingerprint compares values. It cannot see a field's
meaning move underneath it, and a byte-identical spec is exactly what a
redefinition looks like from the outside.

That is the same shape as everything else this branch has found: a check whose
form does not match the claim it is being used to support.

## What survives

Both registered sweeps stand entirely, on their own terms and their own
transcripts:

* **`prereg/channel_vs_precision.md`** --- a paired belief effect grows with the
  draw budget and does not converge by 2,880 draws. REFUTED as registered.
* **`prereg/precision_generality.md`** --- an unrelated, opposite-signed arm
  grows too, so that is a property of the instrument. INSTRUMENT PROPERTY as
  registered.

Neither was ever a test *of* the gap; each was a test of a story told *about*
it. The stories are gone and the measurements remain, which is the right way
round.

What is withdrawn is the premise underneath them: that something had changed
about the world between the two runs. Nothing had. Four explanations were
offered for a phenomenon that did not exist, and the one action that settled it
in twenty minutes was to stop explaining and bisect.

## The bisect has a consequence I nearly left un-drawn

If `6d75ec4` re-priced the gate at **20:18** on 29 August, then every convention
belief figure measured before it belongs to a different sender than every figure
measured after. Checking the timeline against what each run actually is:

    1a96689  20:03   exploratory, seed 560,000    |
    f8abe6d  20:14   replication, seed 880,000    |  OLD gate, V1 carry 72.0%
    ------------------------------------------------------------------------
    6d75ec4  20:18   the sender's gate re-priced
    ------------------------------------------------------------------------
    2026-08-31       every re-run today           |  NEW gate, V1 carry 57.8%

**The original replication is clean.** Exploratory and replication were both
old-gate, checked against bars derived from the exploratory, internally
consistent. It replicated and that stands, and so does the reading that its NLL
regression was the cost of reading ten arms.

**Two comparisons made today were not**, and both were mine:

* the aimed re-run scored against **condition 3**, whose bars were set at half
  the *exploratory* magnitudes --- old-gate numbers used as a bar for a new-gate
  run. Conditions 1 and 2 are properties of the arm and still hold; condition 3
  is now recorded as `see below` rather than PASS.
* the locating book's **condition 2** against the literal **+0.0351**, also
  old-gate. The verdict does not move --- the same-gate comparison
  (+0.0227 against +0.0260) is the one that decides it and was already the one
  quoted --- but the second reading is withdrawn rather than kept as
  corroboration.

Neither changes a verdict. Both are cases of a number surviving a change in what
it denotes, which is precisely what the engine digest now committed to every
belief instrument exists to make visible.

`results/convention_posterior.json` is worth one explicit sentence, since it is
the file most quoted in this direction: **all of it is old-gate.** It remains a
valid measurement of inference on its own transcripts, as `6d75ec4` said at the
time. It is not comparable in magnitude to anything measured after 20:18 that
day.

---

# UPDATE, 2026-08-31: Direction 2 is already aimed, so its stated mechanism has no headroom

Direction 2 above proposes:

> The shipped signalling gate fires on *cheapness*. It does not consider what
> the team needs to know. Aim it instead at the half-suit whose allocation is
> most likely to be forced unresolved.

That is a claim about the code, and the code is right there, so it was measured
before it was implemented. `scripts4/signal_aim.py`, `results/signal_aim.json`.

**208 signalling opportunities over 60 games. The ask points at a stuck
half-suit 208 times out of 208 --- 100.0% --- with a mean of 1.04 stuck
half-suits available when it fires.**

The gate in `agent4.decide` already refuses to signal unless
`stuck_half_suits()` is non-empty, and although `perpetual.signalling_ask` then
searches every half-suit our team *owns* rather than only the stuck ones, the
two sets do not come apart in practice: a card whose holder is already placed is
skipped, which leaves essentially the stuck set. And with about **one** candidate
available there is nothing to choose between even in principle.

So the proposal's mechanism --- pick a better target --- **has no headroom.** It
is not that aiming would help a little; there is no aiming decision being made
badly.

## Where Direction 2's headroom must actually be

Not in *which* half-suit.

> **CORRECTION, half an hour after the above was written.** This section
> originally offered two remaining leads and the first of them, **when**, was
> already closed --- by `prereg/deadline_signalling.md`, which is the very
> document I cited beside it. It did not merely note the gate was uncalibrated;
> it **registered and ran** the re-priced gate. Arm B at `p_best <= 0.15`
> against arm C at `0.50`, 1,000 games:
>
> | arm | gate declarations | wrong/game |
> |---|---|---|
> | B (0.15) | 75 (9.3% wrong) | 0.156 |
> | C (0.50) | 78 (10.3% wrong) | 0.152 |
>
> **Widening the gate by 3.3x changed the engine's behaviour on three
> declarations in a thousand games.** Its own words: *"the gate was never the
> binding constraint ... p_best <= 0.15 is very nearly implied by the situation
> the protocol fires in ... That retires the hypothesis rather than leaving it
> open."*
>
> I proposed a lead without checking whether the project had already closed it,
> in a note whose whole point was that a claim about the code should be measured
> before it is built. It is the day's own lesson, missed on the day.

That correction also explains the measurement above rather than merely competing
with it. **1.04 stuck half-suits when the signal fires** and *"a stuck seat is
one whose best ask is already bad"* are the same fact from two angles: by the
time this protocol engages, the situation has almost no degrees of freedom left.
Neither the target nor the threshold is a choice being made badly, because
neither is much of a choice.

## What the project itself names as the open question

`prereg/deadline_signalling.md`, having measured the mechanism at
**+0.122 [+0.029, +0.215]** sets/game and declined it against a +0.15 bar, says
where the ceiling is:

> **Its ceiling is that it adds errors almost as often as it avoids them** ---
> 52 games against 72. That is the number to attack if this mechanism is ever
> revisited, **not the gate**.

So the open question is not when to signal or what to aim at. It is: **why does
a deliberately dead ask that proves where a card is not sometimes make the
declaration worse?** Avoiding an error is worth +1.61 and adding one costs
-0.96, so the two are not symmetric, and 52 against 72 at those prices is what
turns a real mechanism into a +0.122 that misses a +0.15 bar.

That is a well-posed question with a measured decomposition already behind it,
and it needs no new play to answer: `results/signal_gate_journal.jsonl` already
carries a per-game, per-arm declaration path ledger for all 1,000 games.

### Answered, from data already on disk

`scripts4/signal_error_paths.py`, `results/signal_error_paths.json`. The split
reconciles exactly against the registration --- **52 added, 72 avoided, 876
unchanged** --- which is the check that the right baseline is being used, since
C against `B_incumbent` instead gives 22 / 28 / 950 and would have looked like a
new finding.

**Where the declarations move, C minus A, per game:**

| group | voluntary | gate | forced | exact |
|---|---|---|---|---|
| errors **ADDED** (n=52) | **-0.788** | -0.635 | **+1.327** | -0.250 |
| errors **AVOIDED** (n=72) | **+0.139** | -0.847 | **-0.139** | +0.111 |

**And what each path costs**, arm C over all 1,000 games:

| path | declarations | wrong |
|---|---|---|
| voluntary | 3,692 | **0.1%** |
| exact | 796 | 0.0% |
| gate | 78 | 10.3% |
| **forced** | 307 | **46.3%** |

Signalling drains the **gate** path in both groups, by about the same amount
(-0.635 against -0.847). That part is the mechanism working as designed and it
is *not* what separates the two outcomes.

What separates them is entirely **where the drained declaration lands instead**:

* **avoided** -> it becomes **voluntary** (+0.139) and exact (+0.111). The split
  got placed, so the declaration is made knowingly, at 0.05% wrong.
* **added** -> it becomes **forced** (+1.327) while voluntary *falls* (-0.788).
  The split did not get placed; the spent turn pushed the seat past the
  deadline, at 46.3% wrong.

So the protocol is not choosing badly between targets --- measured above, 208/208
--- or between thresholds --- retired by its own registration. **It is spending a
turn on information that arrives in time in 72 games and too late in 52**, and
the price of "too late" is a 0.05%-wrong declaration becoming a 46.3%-wrong one.

That is the first statement of this mechanism's failure mode in terms of the
thing it actually trades, and it says what a fix would have to be: not a better
target and not a wider gate, but a condition that predicts **whether the
information will arrive before the deadline**. Which is what "how early" was
groping at, now with a measurement under it instead of a guess.

### And what it would cost to build one, checked rather than assumed

A predictor has to fire at the moment of the signalling decision, so the useful
next question is whether anything observable *then* separates the 52 from the
72. **The journal cannot answer it**, which is worth stating so the next person
does not spend the afternoon discovering that:

| field | added (n=52) | avoided (n=72) |
|---|---|---|
| `rev` | 2 for every game | 2 for every game |
| `fallbacks` | 0.000 | 0.000 |
| `kv_even` | 0.52 | 0.47 |
| declarations (arm C) | 4.67 | 4.71 |

The one field that looked like a separator is not one. Baseline declarations per
game are 5.019 against 5.444, a difference of **-0.425 [-0.882, +0.031]** ---
covering zero. Quoted with its interval rather than as two means, because two
means differing in the direction you hoped is how the last four mechanisms on
this branch got written down.

`signal_gate_journal.jsonl` stores per-game aggregates: a path ledger, a margin,
a deal id. It holds nothing about the *state at the moment the signal fired*.
So the descriptive step before any registration --- which observable predicts
the group --- needs **new instrumented play**, not more analysis of what is on
disk. That is the honest price, and it is why no registration is written here.

## The probe reported zero first, and the reason is the recurring one

The first version reached for `agent._ctx(obs)` --- which does not exist ---
inside a bare `except Exception`, and reported **0 opportunities**. A zero from
a probe that never ran looks exactly like a zero from a phenomenon that never
happens, and the only reason it was caught is that "never, in 30 games" was
implausible enough to check rather than record. The instrument now builds the
context the way `agent4.decide` builds it and swallows nothing.

---

## UPDATE 2026-08-31 — the clock was the wrong variable, and the instrument says so

The previous section named the honest next step and its price: the journal
stores per-GAME aggregates and holds nothing about the state at the moment the
signal fired, so the descriptive step before any registration needs new
instrumented play. `scripts4/signal_deadline.py` is that play, and
`results/signal_deadline.json` is 1600 games of it — 800 deals x 2 parities,
arm C, seed base 9,300,000, deliberately not the 3,600,000 whose deals produced
the lead.

**The hypothesis this instrument was built to test is REFUTED.** The reasoning
was clean and it was wrong: `fish/agents/base.py::stalled` declares a position
stuck after 80 actions with no resolution, `agent4.decide` turns that into a
forced declaration, every signal spends one of those 80, and neither
`signalling_ask` nor its gate reads the counter — so the stall clock looked
like the clock the mechanism cannot see. Measured at the moment of the first
signal, per (deal, parity, half-suit), clustered on the deal:

| observable at fire time | in time | too late | difference |
|---|---|---|---|
| **`since_claim`** (the stall clock) | 13.00 | 12.12 | **-0.88 [-2.46, +0.71]** covers 0 |
| `legal_asks` | 31.91 | 20.45 | **-11.46 [-14.45, -8.42]** |
| `my_cards` | 7.19 | 5.57 | -1.62 [-2.08, -1.17] |
| `team_cards` | 19.28 | 16.49 | -2.78 [-3.82, -1.73] |
| `min_team_cards` | 4.61 | 3.84 | -0.76 [-1.14, -0.40] |
| `live` half-suits | 5.51 | 4.64 | -0.86 [-1.20, -0.53] |
| `unplaced` in the target | 1.57 | 1.90 | +0.33 [+0.21, +0.45] |
| `step` | 70.38 | 94.78 | **+24.40 [+18.68, +30.53]** |

The stall clock is the one thing that does not separate them, and it is not
close: 13.0 against 12.1 out of a window of 80, with an interval covering zero.
Nothing is racing that deadline. Both groups signal about a sixth of the way
into it.

**What separates them is how much game is left.** Fewer legal asks, fewer cards
in hand, fewer cards on the weakest teammate, fewer live half-suits, and 24
actions later in the game.

### CORRECTION, one commit later: the count says the opposite of the inference

The paragraph that stood here concluded, from the observables alone, that
"the mechanism is not running out of TIME, it is running out of ASKS" —
because `agent4.decide` has two routes to a forced declaration, `not asks` and
`stalled and claimable`, and every separating variable belonged to the first
while the only variable belonging to the second separated nothing. It was
recorded at the time that pointing is not counting, and `forced_reason` was
added to count it. **The count goes the other way, 3 to 1:**

| which deadline actually fired on the 244 too-late episodes | |
|---|---|
| `stalled and claimable` | **185** |
| `not asks` | 59 |
| unattributed | 0 |

Both facts are true, and reconciling them is the finding. Per episode:

| | in time (n=355) | too late (n=244) |
|---|---|---|
| fires in the episode | 5.6 | **42.5** |
| stall clock at the FIRST fire | 13.0 | 12.1 |
| stall clock at the LAST fire | 14.2 | **59.4** |
| `legal_asks` at the first fire | 31.9 | 20.5 |
| `p_best` at the first fire | 0.111 | 0.070 |

The clock does not predict at the first fire because at the first fire there is
nothing to predict: both groups are twelve or thirteen actions into a window of
eighty. What happens next is that the low-askability episodes **spin** — 42.5
signals against 5.6 — and the spinning is what walks the clock from 12 to 59.
The gate is a per-turn predicate on `p_best <= signal_max_p`; a seat with few
legal asks has no good ask to make, so the gate stays true, so it signals
again, so it burns another action of its own stall window.

**The signal is not racing a clock it cannot see. It is running the clock down
itself.** Remaining askability is the right PREDICTOR of which episodes do
that; the stall window is the deadline that then fires. The previous paragraph
had the predictor right and the deadline exactly backwards.

### Which changes what a fix would be

Not a deadline predictor. A REPEAT LIMIT. A signalling ask proves publicly that
this seat does not hold one named card; re-proving it on the next turn adds
nothing, and the mechanism does it a mean of 42.5 times in exactly the episodes
that end badly. The intervention is cheap, local to the gate in
`agent4.decide`, and has an obvious inert default (no limit = today's
behaviour, bit-identical).

It is a lead, not a result. It has not been registered and has not been run,
and the reason for the delay is on the record above: the previous confident
reading of this same data survived one commit.

### And the repeats are not a knob. They are waste.

Before registering a repeat CAP with a grid, one fact had to be measured,
because it changes what the intervention is rather than how it is tuned:
`perpetual.signalling_ask` picks the highest-entropy card among legal asks in a
half-suit our team owns and skips one already placed, but proving *this seat
does not hold X* removes only OUR bit from X's mask. With two teammates left
the mask still has two bits, so X can stay the top pick and be re-asked
forever. The instrument now records the CARD, not just its half-suit:

| | fires per episode | distinct cards | repeats saying nothing new |
|---|---|---|---|
| in time (n=355) | 5.6 | 1.27 | 4.3 |
| **too late (n=244)** | **42.5** | **1.74** | **40.8** |

**Ninety-six percent of the signalling asks in a bad episode re-prove a fact
already on the public record.** The mechanism has about 1.7 things to say and
spends 42.5 turns saying them, and those turns come out of its own stall
window — which is the deadline that then fires in 185 of the 244 cases. The
waste is not confined to the bad episodes either; the good ones spend 4.3 of
their 5.6 the same way. They simply have the slack to afford it.

So there is no grid to register. The intervention has no free parameter: do
not signal a card this seat has already signalled, and fall through to normal
ask selection once they are exhausted. It is a two-arm question — off against
on — not a sweep.

One caveat, stated rather than assumed. A repeat is redundant because under
the no-bluff rule *seat P does not hold X* is permanent once proven: P could
only acquire X by asking for it, which is public, and a seat holding X cannot
make a doomed ask for it. If that reading of the rules is wrong, the 40.8
figure is an upper bound on the waste rather than the waste.

That the implementation has no parameter does not mean it helps. Whether
removing 40.8 turns per bad episode changes the margin is a separate question
and needs a duel under its own registration, with the switch shipped inert
(off = today's behaviour, bit-identical) as every knob on this branch has been.

### The negative control moved, and it does not mean what it looks like

`p_best` — the gate's own input — came in at 0.11 against 0.07, difference
-0.04 [-0.07, -0.01], excluding zero. It was carried as a control precisely
because `prereg/deadline_signalling.md` widened that threshold 3.3x and moved
three declarations in a thousand games, so a probe finding it predictive would
be disagreeing with a settled result.

It is not disagreeing, and the reason is worth writing down rather than
assuming. Both group means sit BELOW 0.15, so almost every fire already
happened under the incumbent gate; the band the registration opened,
[0.15, 0.50], is nearly empty. A threshold move that adds an almost-empty band
changes almost nothing whether or not `p_best` correlates with the outcome
inside [0, 0.15]. The two results are about different things: one about where
the bar sits, this one about what the variable predicts below it. The control
is not violated, but it is not the clean null it was framed as either, and
`p_best` is in any case a plausible proxy for the same "late, few cards"
factor as every other separating row.

### Two corrections to what was said before the run

**The 300-fire probe said the signal never fires in a dead position.** At 1600
games it does, in about 2% of first fires (0.01 against 0.04, [+0.00, +0.06]).
"Zero in 300" was a small sample, not a property. The `dead` reading stands
only as "rare", which is still enough to say the free-turn justification in
`perpetual.signalling_ask` describes a position the shipped arm almost never
reaches.

**It does not spend A turn.** 623 episodes take a mean of 20.0 fires each,
median 3, max 163. The gate is a per-turn predicate, so once true it stays true
and the seat re-signals at the same half-suit every turn. Counting every fire
rather than the first put the stall clock at 12.3 against 38.5 — a 26-action
separation, in the hoped-for direction, that was entirely the repeats walking
the clock upward and counting one declaration once per repeat. That number
would have been reported as the finding.

### What the anchors caught on the way

The instrument reproduces three published figures before reporting anything and
exits non-zero if one fails. Two failed on the first run.

`voluntary` was the anchor's own fault: it asked whether the published POINT
fell inside this run's interval, which treats the published figure as exact.
That point rests on TWO wrong declarations out of 3,692. A pooled
two-proportion test on both counts puts it at z = +1.19 — agreement.

`forced` was real, and it was engine drift. 36.59% here against 46.25%
published, z = -2.71, while the path MIX reproduced almost exactly per 1000
games (voluntary 3733 against 3692, forced 308 against 307, exact 823 against
796). `signal_gate_journal.jsonl` was committed 2026-08-28 13:48:06 and
`claim_forced_exhaustive` shipped at 14:08:23, twenty minutes later, and the
journal carries the bridge rev and no engine digest. Dates are not evidence, so
the instrument re-ran with the field switched back off:

| `claim_forced_exhaustive` | forced error rate | against published 46.25% |
|---|---|---|
| 0 — as the journal was measured | 44.62% [37.66, 51.80] on 186 | z = -0.35, agrees |
| 1 — the shipped champion | 36.59% on 492 | z = -2.71, disagrees |

Switching the field back reproduces the published figure. `ENGINE_DATED`
records that, and an entry there is VOID unless its results file exists on
disk — the rule `check_prereg_backing.py` applies to a pre-registration, for
the same reason. A dated path still reports `agrees: False`; being explained is
not being in agreement.

**The finding survives the drift**, which is the part that mattered. On the
pre-exhaustive engine the same table gives `legal_asks` -8.43 [-13.83, -3.13],
`step` +21.80 [+11.04, +32.87], `my_cards` -1.39 [-2.06, -0.73], and
`since_claim` covering zero — the same shape, on 600 games.
See `results/signal_deadline_noexhaustive.json`.

### Still no registration, and now for a different reason

The earlier reason was that the criteria could not be chosen without inventing
them. They can be chosen now — remaining askability at signal time, on a seed
base other than 9,300,000. What is missing is one fact the payload does not
carry: `agent4.decide` writes "forced: no legal ask" and "forced: stalled with
a claimable half-suit" as distinct trace reasons, and `path_ledger._path_of`
folds both into `forced`. Every separating variable above points at the first,
but pointing is not counting, and this project has been wrong before about a
mechanism whose evidence all leaned one way.


---

## UPDATE 2026-08-31 — the repeats were not waste. They were the mechanism.

`prereg/signal_no_repeat.md` registered, built and ran. Both gates passed and
**the primary refuted the proposal**: D = -0.0715 [-0.1068, -0.0362] over 4,000
games at seed base 9,900,000. Removing 40.8 wasted turns an episode makes the
engine worse.

The decomposition is the finding, and it inverts the premise this whole line
of work rested on. Per game:

| arm | gate decls | wrong | forced decls | wrong | signal turns | margin |
|---|---|---|---|---|---|---|
| A_shipped (signalling off) | 0.299 | 0.0750 | 0.181 | 0.0842 | 0.00 | +2.4450 |
| B_incumbent (arm C) | **0.069** | **0.0070** | 0.315 | 0.1276 | 8.18 | **+2.5110** |
| C_norepeat (the switch) | 0.226 | 0.0529 | 0.193 | 0.0857 | 0.63 | +2.4395 |

Total wrong declarations a game: A 0.1590, B 0.1383, C 0.1388. B and C are
LEVEL on errors, so what the switch costs is not paid in mistakes.

`agent4.decide` reaches the signal branch BEFORE the gate branch. A seat that
can signal signals instead of taking a gate declaration — and a gate
declaration is wrong about a quarter of the time. Signalling again next turn
defers it again. B takes 0.069 gate declarations a game against A's 0.299, at a
tenth the error rate. Stop the repetition and the deferral stops with it:
C's gate path returns to 0.226 at 23.4% wrong and **C lands on A**, +2.4395
against +2.4450.

**The value of the signalling mechanism is the postponement, not the message.**
The 96% of asks carrying no information are the only thing buying the delay.
"A signalling ask proves once that a seat does not hold one named card, and
proving it forty more times spends forty actions to say nothing new" is right
about the information and wrong about the value — and it was the sentence that
motivated the registration.

That is the third time in this one line of work that a confident reading of
this data has been overturned by measuring the next thing down:

1. the stall clock looked like the predictor, and does not separate the groups;
2. the observables all pointed at `not asks`, and the count said `stalled`, 3 to 1;
3. the repeats looked like pure waste, and they are the mechanism.

### What is open

`B - A = +0.0660` is a point estimate with NO interval — the payload did not
carry per-game margins, and that contrast was not registered here anyway.
Whether the signalling mechanism itself is positive on 4x the data of
`prereg/deadline_signalling.md` (+0.068 [-0.033, +0.169]) is the obvious next
registered question, and the instrument now stores the rows so it can be
answered with an interval.

If it is positive, the interesting version is not "switch signalling on" but
"the gate declaration is worth deferring, and signalling is an accidental and
expensive way to defer it" — the cheap version would be a declaration-side
change, not an ask-side one.

### That declaration-side version already exists, and was already measured

Checked before proposing it, because this branch has nearly rebuilt an existing
mechanism before. `prereg/stuck_claim_gate.md` registered and ran exactly that
change on 2026-08-28: `B_defer` raises the doomed-ask branch's declaration bar
instead of declaring at a coin flip. Its ledger and mine are the same
intervention reached from opposite sides of the engine.

| | gate/game | forced/game | wrong/game | margin against A |
|---|---|---|---|---|
| **declaration side** — `B_defer`, 1,000 games, seed 2,400,000 | 0.317 -> 0.093 | 0.178 -> 0.262 | 0.193 -> 0.129 | **+0.0580** [-0.0177, +0.1337] |
| **ask side** — signalling, 4,000 games, seed 9,900,000 | 0.299 -> 0.069 | 0.181 -> 0.315 | 0.159 -> 0.138 | **+0.0660** (point only) |

Both drain the gate path by about 0.23 declarations a game, both push the
displaced declarations into the forced path, both cut wrong declarations, and
both land near +0.06 sets a game. One does it by declining to declare; the
other by spending a turn on a doomed ask so that declining happens as a side
effect.

**They do not pool.** The baselines differ (+2.302 against +2.4450), the older
run records no engine digest, and its forced-path error rate of 57.9% against
today's 46.5% says it predates `claim_forced_exhaustive` — the same drift
already proved above. Different engines, different seeds, different arms.
Nothing here combines two intervals covering zero into one that does not.

What it does change is the standing of the effect. An estimate near +0.06
reached twice by unrelated routes is better evidence that something is there
than either run alone, and both registrations declined to ship on it, which
was right both times. So the open question is not a third route to the same
intervention. It is whether +0.06 survives a run powered to see it — and the
power arithmetic is better than it looks, because the right quantity is the
PAIRED contrast and not the arm margin.

`B_defer - A` had a half-width of 0.0757 on 500 deals. Scaled to 2,000 that is
0.0379, comfortably under +0.058: **roughly 850 deals would settle it**, and
both routes have already been run at or above that. The signalling run's own
paired contrast `C - B` came in at half-width 0.0353 on 2,000 deals, which is
the scale to expect.

So the 9,900,000 run very probably already contains the answer for `B - A`,
and the reason it cannot be read is not sample size but that the payload did
not keep the per-game margins. That is a bookkeeping failure, not a
measurement one, and it is now fixed in the instrument — which makes re-running
it the cheapest open item on this branch rather than the most expensive.

Nothing enters `V06_DEPLOYED`. `signal_no_repeat` stays False and `signal_mode`
stays "off".


---

## CORRECTION 2026-08-31 — I cited the screen, not the confirm, all day

Every place above where this session says the signalling mechanism was measured
at **+0.068 [-0.033, +0.169], covering zero**, is wrong. That is
`results/r5_signal_check.json`, the SCREENING estimate arm B was carried to
reproduce. The registered confirm, `results/signal_gate_confirm.json`, is:

| arm against A_shipped | effect | interval |
|---|---|---|
| B_incumbent, `signal_max_p` 0.15 | +0.1180 | [+0.0325, +0.2035] **clear of zero** |
| C_measured, `signal_max_p` 0.50 | **+0.1220** | **[+0.0291, +0.2149] clear of zero** |

**The mechanism's value is established and positive.** It does not ship because
`prereg/deadline_signalling.md` set its bar at a point estimate of +0.15 and
+0.1220 clears zero without reaching it — a bar deliberately not amended after
seeing the number. `paper/kraken.tex` says this correctly at the tab:signal
table; the error was mine, in `prereg/signal_no_repeat.md`, in this document,
and in several commit messages.

I used the wrong figure to argue that a null was the expected outcome of the
no-repeat registration, and to write "whether the mechanism itself is positive
is the obvious next registered question". It is not a question. It is answered.

### What survives, and what the real open question is

The refutation stands untouched: `C_norepeat - B_incumbent = -0.0715
[-0.1068, -0.0362]` is measured on that run's own arms and owes nothing to the
earlier figure. So does the decomposition, and so does the finding that the
value is the postponement.

The convergence note above is weaker than I wrote it. Three estimates of
nearly the same intervention:

| | contrast | effect | seed |
|---|---|---|---|
| `B_defer` — declaration side | vs shipped | +0.0580 [-0.0177, +0.1337] | 2,400,000 |
| `C_measured` — ask side, registered confirm | vs shipped | +0.1220 [+0.0291, +0.2149] | 3,600,000 |
| `B_incumbent` — ask side, today | vs shipped | +0.0660, no interval | 9,900,000 |

Their LEDGER movements really are alike — each drains about 0.23 gated
declarations a game into the forced path and cuts wrong declarations — and that
part of the note stands. Their MARGINS are not as tidy as I made them look:
one covers zero, one clears it, and the third has no interval at all. Two of
the three baselines differ by 0.17 sets a game, which is larger than the effect
under discussion.

**The real open question is whether +0.1220 survives the engine change.**
Today's point estimate is +0.0660, about half, on an engine that now carries
`claim_forced_exhaustive`. That is mechanically coherent rather than
coincidental: signalling works by pushing declarations out of the gated path
into the forced path, and the forced path is precisely what that commit
improved — so the value of moving a declaration there should fall. Establishing
it needs the interval this run failed to keep, not new deals.

That is the fourth reading overturned in this line of work, and the only one
where the record was already right and I was quoting it wrong.


---

## UPDATE 2026-08-31 — SURVIVES. The mechanism's value is intact after the engine change.

`prereg/signal_value_after_exhaustive.md`, registered before the run and run at
seed base 10,100,000 (4,000 games x 3 arms).

    PRIMARY  margin(B_incumbent) - margin(A_shipped)
             +0.1435 [+0.0971, +0.1899]   2,000 deal clusters

Clear of zero and containing the published +0.1220, which is **SURVIVES** by
the rule fixed in advance.

**The mechanistic argument for a shrink was wrong.** Signalling works by moving
declarations out of the gated path into the forced path; `claim_forced_exhaustive`
improved the forced path; so moving a declaration there should be worth less.
That reasoning is why the registration was written. The measurement declined
it, which is the point of writing the reasoning down first.

| contrast | effect | reading |
|---|---|---|
| `B_incumbent - A_shipped` | **+0.1435** [+0.0971, +0.1899] | primary, SURVIVES |
| `C_norepeat - B_incumbent` | -0.1075 [-0.1429, -0.0721] | registered replication: REFUTED again |
| `C_norepeat - A_shipped` | +0.0360 [-0.0047, +0.0767] | covers zero |

The no-repeat refutation replicates on fresh deals — -0.1075 here against
-0.0715 at 9,900,000, intervals overlapping — and `C_norepeat` remains
indistinguishable from the shipped champion. Strip the repeats and the
mechanism does nothing: the same statement twice, on two seed bases.

### The caveat is about the earlier run, and it is mine

`results/signal_no_repeat_9900000.json` put `B - A` at **+0.0660** and this run
puts it at **+0.1435**. That is a wide gap for the same contrast on the same
engine — and **the earlier figure has no interval at all**, because that
payload did not store per-game rows. So the two cannot be compared properly,
only noticed. The registered run is the one that counts, and the +0.0660 was
always a difference of two arm means quoted without an interval, which is
precisely the kind of number this project should not lean on. I leaned on it
for two commits, including to write that the mechanism looked "about half as
valuable".

The instrument now reports every pairwise contrast on every run. This
registration's own primary had to be computed by hand from the stored rows
afterwards, because the built-in primary belongs to the previous registration —
a step at which a number can quietly become the wrong one. Which contrast is
primary is now a property of the registration, not of the code.

### Where the signalling line stands

* The mechanism is real: +0.1435 [+0.0971, +0.1899], replicating +0.1220.
* Its value is the POSTPONEMENT of a gated declaration, not the information it
  sends: removing the informationless repeats costs -0.1075 and returns the
  engine to baseline.
* It still does not ship. The point estimate is +0.1435 against a bar of
  +0.15 — short by 0.0065, on a threshold that is not amended for being
  narrowly missed.
* `prereg/stuck_claim_gate.md`'s `B_defer` reaches the same postponement from
  the declaration side at +0.0580 [-0.0177, +0.1337] and also did not ship.

The open question is no longer whether the effect exists. It is whether the
postponement can be had without spending eight turns a game on doomed asks —
and the one attempt at that so far, `B_defer`, was measured at half the size
with an interval covering zero, on a different engine and a different baseline.


---

## UPDATE 2026-08-31 — signalling PRE-EMPTS the deferred gate. The four-arm design was degenerate.

`prereg/signal_vs_defer_additivity.md` was registered, built, and then **not
run**, on the evidence of a 400-game probe that cost 11 minutes instead of 130
(`results/signal_vs_defer_probe200.json`).

**`B_signal` and `D_both` produce identical margins in all 400 games.**

    b  B_signal  +0.1150 [-0.0563, +0.2863]
    c  C_defer   +0.0850 [-0.0367, +0.2067]
    d  D_both    +0.1150 [-0.0563, +0.2863]
    I = (D - B) - (C - A) = -0.0850, which is exactly -c

The arms are not bit-identical in play — one gated declaration differs, 19
against 18 — so the knob reaches the engine. It just never changes a result.

The branch order in `agent4.decide` predicted this: the signal branch fires at
`p_best <= 0.50` and the gated declaration at `p_best <= 0.0`, a strict subset.
With signalling on, the gate is reachable only where there is no stuck
half-suit or no available signalling ask, about 0.048 declarations a game, and
the defer knob binds on a subset of that.

**The registered primary is uninformative as a consequence.** If `D - B` is
identically zero then `I` reduces to `-c` and says nothing about additivity.
Running 4,000 games would have measured `-c` more precisely and then printed
ONE EFFECT — a verdict that is true, for a reason the statistic does not
establish and a reader would take as statistical. That is worse than not
running, so it was not run.

### What is and is not established

**Established:** adding the deferred gate on top of signalling buys nothing.
0 of 400 games changed. The additivity question is answered structurally, which
is stronger than the statistical answer the design was reaching for.

**Not established:** that the two are the same mechanism. The order is
asymmetric and only one direction was tested — `C_defer` runs with signalling
off, so nothing here says whether adding signalling on top of deferral buys
anything. They remain two interventions that drain the same path, at +0.1150
and +0.0850 on 200 deals.

### Where the signalling line now stands, in full

| claim | status |
|---|---|
| the mechanism is real | +0.1435 [+0.0971, +0.1899], replicating the published +0.1220 |
| its value is postponement, not information | removing the informationless repeats costs -0.1075 and returns the engine to baseline |
| it still does not ship | +0.1435 against a bar of +0.15, short by 0.0065, bar not amended |
| the deferred gate reaches the same path | +0.0580 [-0.0177, +0.1337] on 1,000 games, older engine |
| the two do not stack | signalling pre-empts deferral; 0 of 400 games changed |

The live question is `C_defer` alone at power on the current engine: it was
last measured before `claim_forced_exhaustive`, its interval covered zero at
1,000 games, and on this probe it posts the lowest wrong-declaration rate of
the four arms (0.09 a game against A's 0.1375) while spending **zero**
signalling turns where `B_signal` spends 7.76. If the postponement can be had
for nothing, that is the arm that has it.
