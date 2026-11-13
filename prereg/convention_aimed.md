# Pre-registration: replicating the aimed code book on fresh seeds

**Registered 2026-08-29, before any run at a seed base other than 560,000.**

## Why this document exists

The aimed arm was added to `scripts4/convention_posterior.py` mid-stream. It is
not covered by `prereg/convention.md`, which registers the depth book and its
gates, so its result --- the largest in this direction by a factor of two --- is
**exploratory**. It is being replicated before it licenses anything.

There is a second reason, and it is the more important one. On the way here I
read a 70-decision probe of the aimed decoder, using the mixture at `q = 0.6`,
which returned +0.0017 +- 0.0652 and which I reported as "aiming is neutral". I
then constructed an explanation for that null --- that the aimed book trades a
locating signal for a counting one --- and wrote it up as a finding. The interval
covered every effect subsequently measured; the null was underpowered and the
explanation was a rationalisation. Both are retracted in `RESEARCH_FRONTIER.md`.

A result I have already talked myself into once, in the wrong direction, is
exactly the result that needs its criteria fixed in writing before the next run.

## What was measured, exploratorily

Sender and receiver both aimed, gate 0.05, 40 games, 1,076 scored decisions,
paired by decision against a shared inert baseline, teammate pool.

| arm | teammate NLL | teammate top-1 |
|---|---|---|
| flat 0.25 | -0.0427 [-0.0476, -0.0378] | +0.0204 [+0.0139, +0.0269] |
| flat 0.5 | -0.0628 [-0.0701, -0.0555] | +0.0320 [+0.0236, +0.0403] |
| flat 0.8 | **-0.0712** [-0.0803, -0.0621] | +0.0351 [+0.0258, +0.0444] |
| flat 1.2 | -0.0676 [-0.0789, -0.0564] | **+0.0375** [+0.0274, +0.0476] |
| flat 2.0 | -0.0342 [-0.0507, -0.0177] | +0.0316 [+0.0209, +0.0423] |

Every arm clears both gates, and **top-1 improves significantly at all five** ---
which nothing else in this project has done. Validity: V1 72.0%, V2' 42.9%,
V3 93.7%.

## The three things that could be wrong with it

1. **Chance.** Ten arms across two books were read before this one stood out.
2. **The transcripts.** The aimed sender plays different games, and their
   baseline belief is worse (NLL 1.3995 against 1.3706 at gate 0.10 depth), so
   there is more headroom. The paired deltas are within-transcript and valid,
   but the *comparison between books* is not clean.
3. **The seeds.** One seed base, 560,000, for both deal and agent RNG.

## Design

`scripts4/convention_posterior.py`, 40 games, stride 4, `n_draws = 720`, sender
gate 0.05 aimed --- identical in every respect except a **fresh seed base**, so
the deals, the agent RNG streams and the scoring RNG are all new.

**Outcomes**, paired mean differences against the inert baseline with 95%
intervals, teammate pool:

* **Primary:** NLL at `beta = 0.8`, the exploratory optimum.
* **Co-primary:** top-1 at `beta = 0.8`.
* Secondary, reported and not gating: the other four arms, the opponent pool,
  and the same for the unaimed book at the same gate as a within-run control.

## Decision rule, fixed in advance

The aimed book **replicates** only if, on the teammate pool at `beta = 0.8`:

1. the paired NLL interval lies entirely below zero, **and**
2. the paired top-1 interval lies entirely **above** zero, **and**
3. both point estimates are at least **half** the exploratory magnitudes ---
   NLL at most -0.0356, top-1 at least +0.0176.

Condition 3 is the one this document is for. Conditions 1 and 2 would be
cleared by a much smaller effect, and a much smaller effect is what regression
to the mean looks like. Condition 2 is on top-1 *above* zero, not merely "not
below": the whole claim is that this is the first belief change here to improve
the argmax, so a null on top-1 refutes the claim even with NLL intact.

**If any condition fails, the aimed result is reported as not replicating and
no duel is registered on it.** The depth book's own pre-registered result
stands independently.

## Withdrawal conditions

* If the within-run unaimed control does not reproduce its own published result
  to within a factor of two, the run is void: something other than the seeds
  changed.
* If V1 falls below 25% or V3 below 50% on the fresh seeds, void, not negative.
* If the replicated optimum moves off `beta = 0.8` by more than one grid step,
  the location is reported as unresolved even if the gates pass.

## What a replication would license

A duel, registered separately, with its own ship bar --- and nothing else. This
is still scored off-policy with the decoder off during play, and the sender is
still paying real probability (0.0090 per encoded ask at this gate) that a
belief instrument cannot see. This project has already measured one case where a
better belief bought nothing in play.

---

# OUTCOME, recorded 2026-08-29

**Replicated on all three conditions.** Fresh seed base 880,000 --- new deals,
new agent RNG streams, new scoring RNG --- 40 games, 1,169 scored decisions.

| | measured | condition | |
|---|---|---|---|
| **primary** NLL at `beta = 0.8` | **-0.0535** [-0.0683, -0.0387] | interval entirely below zero | PASS |
| **co-primary** top-1 at `beta = 0.8` | **+0.0392** [+0.0301, +0.0484] | interval entirely **above** zero | PASS |
| magnitude, NLL | -0.0535 | at most -0.0356 | PASS |
| magnitude, top-1 | +0.0392 | at least +0.0176 | PASS |

Every arm from 0.25 to 1.2 clears both gates, and **top-1 is significantly
positive at all five**, 2.0 included.

## The withdrawal conditions

**The within-run unaimed control reproduces almost exactly**, which is the
condition that would have voided everything:

| arm | original (seed 560,000) | replication (880,000) | ratio |
|---|---|---|---|
| flat 0.25 | -0.0117 | -0.0111 | 0.95 |
| flat 0.5 | -0.0183 | -0.0175 | 0.96 |

V1 73.7% (floor 25%), V3 93.9% (floor 50%). The NLL optimum is still at
`beta = 0.8`, so the location condition holds --- though 0.5 (-0.0533) and 0.8
(-0.0535) are indistinguishable, and the honest statement is that the optimum
lies somewhere in 0.5-0.8 rather than at either.

## Where it regressed and where it did not

| | exploratory | replication |
|---|---|---|
| NLL at 0.8 | -0.0712 | **-0.0535** |
| top-1 at 0.8 | +0.0351 | **+0.0392** |

NLL came down by a quarter, which is what reading ten arms and reporting the
best one costs, and is exactly why condition 3 was written. **Top-1 did not
regress; it went up.** The claim this document was written to protect --- that
this is the first belief change in the project to improve the argmax --- is the
part that held.

## What this licenses

A duel, and only a duel: `prereg/convention_duel.md`, registered before this
outcome was read, 3,000 duplicate-deal pairs at a **+0.15 sets/game** ship bar.
The instrument still cannot see what the sender pays (0.0090 probability per
encoded ask, on 74% of our asks here) or what happens when the encoder and
decoder are both live and the belief that picks the ask is itself shifted.

Nothing ships on a belief result. This project has already measured one case
where a better posterior was worth nothing in play.

---

# REPRODUCTION, recorded 2026-08-31

**The conclusion holds. The magnitudes do not, and the reason is worth more
than the magnitudes were.**

## The run above committed no results file

`f8abe6d` recorded this OUTCOME and touched three files: this document,
`prereg/convention_locate.md`, and a duels JSONL. No results file. Every figure
in the section above therefore existed in this repository only as prose --- here
and in a commit message --- and could not be re-derived by anyone, including its
author. `results/convention_posterior.json` is the *exploratory* 560,000 run,
which this document exists to say should not be quoted.

That is the same defect `scripts4/unwatched_claims.py` was written about, one
layer below the paper: the numbers a document repeats most are the ones nobody
re-derives.

## Re-run at the same seed base

40 games, stride 4, seed base 880,000, `results/convention_replication.json`.

| | recorded 2026-08-29 | re-run 2026-08-31 | condition | |
|---|---|---|---|---|
| NLL at `beta = 0.8` | -0.0535 | **-0.0382** [-0.0466, -0.0299] | below zero; at most -0.0356 | see below |
| top-1 at `beta = 0.8` | +0.0392 | **+0.0260** [+0.0164, +0.0356] | above zero; at least +0.0176 | see below |
| scored decisions | 1,169 | 1,068 | | |

> **THIS TABLE COMPARES TWO DIFFERENT SENDERS, and an earlier version of this
> section did not know that.** The timeline settles it:
>
>     1a96689  20:03  exploratory, 560,000     |
>     f8abe6d  20:14  replication, 880,000     |  OLD gate
>     -------------------------------------------------------------
>     6d75ec4  20:18  the sender's gate re-priced
>     -------------------------------------------------------------
>     2026-08-31      every re-run below       |  NEW gate
>
> Both figures in the left column were measured **before** `6d75ec4` re-priced
> `convention_max_cost` from success probability into the ask objective's own
> units; both in the right column were measured after. V1 carry 72.0% against
> 57.8%. So the left-to-right movement is **not** a magnitude changing --- it is
> a different sender being measured.
>
> **The original replication is unaffected**: exploratory and replication were
> both old-gate, checked against bars derived from the exploratory, and
> internally consistent. It replicated, and that stands.
>
> **What the re-run establishes is smaller than "the conditions still pass".**
> Conditions 1 and 2 --- NLL below zero, top-1 above zero --- are properties of
> the arm and it clears both under the re-priced sender, which is worth knowing.
> Condition 3's bars (-0.0356 and +0.0176) were set at *half the exploratory
> magnitudes*, and those magnitudes belong to a sender that no longer exists.
> Scoring a new-gate run against them is a cross-gate comparison, so "PASS" on
> condition 3 means less than it looks and is recorded here as `see below`
> rather than as a pass.

All five flat arms from 0.25 to 1.2 still clear both channel gates and top-1 is
still significantly positive at every one of them, 2.0 included. The claim this
document was written to protect --- that this is the first belief change in the
project to improve the argmax --- holds for the re-priced sender too, which is
the part that does transfer across the gate change.

## Why the magnitudes fell: the engine, not the decode

The exploratory arm at seed 560,000 --- the one whose file *is* committed --- was
re-run as a control, so the drift could be attributed rather than guessed at.

| | committed 2026-08-29 | re-run 2026-08-31 |
|---|---|---|
| scored decisions | 1,074 | 1,023 |
| **baseline** teammate NLL | 1.3995 | **1.3567** |
| paired NLL at `beta = 0.8` | -0.0712 | **-0.0403** |
| paired top-1 at `beta = 0.8` | +0.0351 | **+0.0226** |

Identical seeds, identical `n_games`, identical stride, and the stored spec is
byte-for-byte the same seven keys.

> **RESOLVED 2026-08-31, and it is not what this section assumed.** Bisected
> commit by commit --- `results/convention_drift_bisect.json`, a worktree per
> candidate with today's instrument copied in so the engine is the only
> variable --- the entire change is **one commit, `6d75ec4`**, and it is a
> **redefinition, not a drift**:
>
> | | V1 carry | decisions | baseline | flat 0.8 |
> |---|---|---|---|---|
> | `1a96689` | 72.0% | 1,074 | 1.3995 | **-0.0712** |
> | `6d75ec4` | 57.8% | 1,023 | 1.3567 | **-0.0403** |
> | ten further engine commits | 57.8% | 1,023 | 1.3567 | -0.0403 |
>
> `6d75ec4` re-priced the sender's gate. `convention_max_cost = 0.05` meant
> *0.05 of success probability* before it and *0.05 in the ask objective's own
> units* after. **The same label denotes two different senders**, so -0.0712
> and -0.0403 were never two measurements of one configuration. Fewer asks
> carry the message, the sender picks different cards, and the baseline is not
> "better" --- it is a different set of positions.
>
> The validation that makes this trustworthy: the probe at `1a96689`
> reproduces `results/convention_posterior.json` exactly --- 1,074 decisions,
> base 1.3995, flat 0.8 -0.0712.
>
> **The spec check could not have caught it.** `convention_max_cost` is not in
> the stored spec; the instrument sets it. And what moved was not its value but
> its units. A configuration fingerprint compares values, not meanings.

The consequence is not in doubt: **the marginal arms have crossed over.**
`flat 2.0` has gone from -0.0342 to **+0.0252** --- significantly harmful now,
where it was significantly helpful then --- and `mix 0.6` and above with it.

> **WITHDRAWN 2026-08-31, the same day it was written.** This paragraph
> originally continued: *"The decode did not get worse. The belief it decodes
> into got better, and a message is worth only what the receiver could not
> already work out. This is the first place in the project where that shows up
> as a measurement rather than a caveat."*
>
> It was not a measurement. It was an explanation for two points, on two
> engines, eleven commits apart, and it was registered and tested the same day
> in `prereg/channel_vs_precision.md`. **Refuted.** Swept on fixed transcripts,
> the paired gain grows as the belief improves rather than shrinking: -0.0064
> [-0.0217, +0.0090] at 180 sampler draws against -0.0436 [-0.0593, -0.0279] at
> 1440, contrast **-0.0372 [-0.0481, -0.0263]** over 40 game clusters. And the
> baseline stops improving after 720 draws while the gain keeps growing, so the
> gain is not tracking what the receiver already knows at all.
>
> That sweep is a different axis --- sampler precision --- so it did not
> explain the gap either. It did not need to: the bisect above shows there was
> no gap to explain, only a gate that had been re-priced. Both registered
> sweeps stand on their own terms; what is withdrawn is the premise that
> something had changed about the world between the two runs.

There is a second thing that run prices, and it applies to every figure in this
document. The engine ships at `n_draws = 480`; every number here was scored at
**720**, because that is what `gamma_split.py` fixed and this instrument
imported. That was first written as an interpolation --- "about 15% smaller" ---
and then **measured**: `results/channel_precision_shipped.json` puts the aimed
book at **-0.0368** [-0.0523, -0.0213] at 480 against -0.0382 at 720, a
difference of **4%**, not 15%. The curve flattens well before 720, which a
straight line between the 360 and 720 cells could not see.

So the figures in this document are quoted at 1.5x the sampler precision the
engine runs at, and that is worth a few per cent rather than a sixth. Worth
knowing; not worth restating the tables over.

## What should and should not be quoted

* **Do** quote: aiming replicates on pre-registered conditions, at two seed
  bases, on two engines a fortnight apart.
* **Do not** quote -0.0535 or +0.0392. They are the values of a policy that no
  longer exists.
* Expect the re-run figures to date the same way. Every number in this
  direction is measured against a moving baseline, and the baseline is the
  thing this project is deliberately trying to move.

## The within-run unaimed control, and the withdrawal condition

The withdrawal condition above voids the run if the unaimed control at the same
gate does not reproduce its own published result to within a factor of two. It
was re-run at gate 0.05, seed base 880,000, and **it holds**:

| arm | 560,000 committed | 880,000 recorded 08-29 | 880,000 today | ratio to committed |
|---|---|---|---|---|
| flat 0.25 | -0.0117 | -0.0111 | -0.0129 | 1.11 |
| flat 0.5 | -0.0183 | -0.0175 | -0.0221 | 1.21 |

Nothing voids. The unaimed book is, if anything, slightly stronger on NLL than
it was.

## The head to head, which is the sharpest form of the result

The unaimed book was also re-run at gate 0.10 for the four-book comparison. But
the gate-0.05 control gives something better: a direct A/B in which the sender's
cost gate, the seed base, the engine, the arm and the instrument are all
identical, and **the only difference is where the message points**.

| gate 0.05, `beta = 0.8` | paired NLL | paired top-1 |
|---|---|---|
| depth, **unaimed** | -0.0284 [-0.0345, -0.0223] | **-0.0086** [-0.0161, -0.0010] |
| depth, **aimed** | -0.0382 [-0.0466, -0.0299] | **+0.0260** [+0.0164, +0.0356] |

**The NLL barely separates them. The top-1 changes sign**, from significantly
negative to significantly positive, on the same asks at the same price.

Across every book measured on this engine and seed base:

| book, at its lowest-NLL arm clearing both gates | paired NLL | paired top-1 |
|---|---|---|
| depth, unaimed, gate 0.05 | -0.0221 | -0.0061 [-0.0124, +0.0003] |
| depth, unaimed, gate 0.10 | -0.0358 | +0.0067 [-0.0006, +0.0140] |
| depth, **aimed**, gate 0.05 | **-0.0382** | **+0.0260** [+0.0164, +0.0356] |
| locate (aimed by construction), gate 0.02 | -0.0184 | +0.0196 [+0.0100, +0.0293] |
| locate (aimed by construction), gate 0.05 | -0.0284 | +0.0227 [+0.0141, +0.0312] |

Every book that aims lands top-1 between +0.020 and +0.026. Neither book that
does not aim clears +0.007, and at the matched gate it is negative. Meanwhile
the NLL column does not order the books that way at all: unaimed at gate 0.10
(-0.0358) beats both locating books on the proper score while losing to both on
the argmax.

So aiming does not buy a generally better belief. It buys the **argmax
specifically**, and a proper score is close to blind to it. That is also the
best available explanation for why the aimed book was mistaken for a null for as
long as it was: the first number anyone reads is the NLL, and on the NLL there
is not much to see.
