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
