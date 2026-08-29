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
