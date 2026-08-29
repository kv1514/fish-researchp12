# Pre-registration: read the signal that is already on the wire

**Registered 2026-08-29, before any duel of this configuration.**

## The claim, which is not a convention at all

Correcting the carry-rate figures produced a fact nobody was looking for: the
**incumbent engine already names the agreed card on 35.3% of its asks**, with
no encoder, no agreement and nothing changed. The ask objective and the code
book simply coincide that often. Against a chance rate of `1 / 3.57 = 28%`,
that is a real if weak regularity sitting on the wire today, unread.

So the encoder can be deleted entirely and the decoder kept.

That configuration is **not a pre-play convention** and should stop being
described as one. It is a better model of a teammate's card choice, and it
works for the reason `prereg/choice_basis.md` gave and never cashed:

> Our teammates run our policy, and we possess it. So the ceiling on predicting
> a teammate's ask is not "how good is a depth heuristic" but "how close can a
> cheap surrogate get to the policy that actually generated the choice".

The expensive route to that --- evaluating the policy per candidate world --- was
ruled out as a nested posterior per world per ask. This is the cheap surrogate:
one 64-entry gather that asks "would this hypothesised hand have named this
card, under the rule our own objective happens to follow 35% of the time".

**It costs nothing and risks nothing.** The policy is untouched; only the
belief moves. There is no message to mis-send, no turn given up, no probability
paid. The entire downside is a mildly mis-weighted likelihood, and the
decoder-only ablation already measured that at +0.033 [-0.646, +0.712] --- a
clean null --- even at `beta = 0.8`, which is four times too high.

## The weight, fixed a priori and not fitted

    beta* = log(0.353 / 0.280) = 0.2317

the log-odds of the measured agreement rate against the chance rate. Rounded to
**0.23**. This is a derived quantity, not a swept one; the grid below exists
only to show the shape around it.

## Design

`scripts4/duel.py`, duplicate deals, pair as the independent unit.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same plus `convention_beta = 0.23`, `convention_aim = True`, and
  **`convention_max_cost` absent** --- the encoder never fires and the policy is
  byte-for-byte the champion's apart from the belief it reads.
* **n_pairs:** 1,200 to start. If the interval straddles the bar, extend to
  3,000 rather than reading a straddle as a result.
* Rules: `wrong_distribution_outcome="opponent"`.

## Decision rule, fixed in advance

**Primary:** mean paired difference in sets/game, Y minus X, 95% interval.

The ship bar is **+0.05 sets/game**, not the +0.15 used for the convention and
the signalling channel, and the reason is stated before the number is known:
**those two spend a resource and this spends nothing.** +0.15 was set to make a
channel earn the turn or the probability it consumes. Here the policy is
identical and only the belief differs, so any effect that is real and positive
is worth having, and the bar exists only to keep a trivial one out.

* lower bound > 0 and point estimate >= +0.05 --> **ships**, after
  re-measurement of every affected figure.
* lower bound > 0, point estimate < +0.05 --> real but trivial; recorded, not
  shipped.
* interval contains 0 --> the free signal is too weak to matter in play.
  Recorded, and the decoder stays at zero.
* upper bound < 0 --> reading the coincidence is actively harmful, which would
  mean the agreement is anti-correlated with the truth in a way nothing has
  suggested. Recorded, and the direction closes.

## Withdrawal conditions

* If Y's measured agreement rate in the duel population differs from 35.3% by
  more than 5 points, `beta` was derived from the wrong number and is re-derived
  before anything is read.
* If either side raises `IllegalAction`, void.
* If Y's moves/game differs from X's by more than 3, the policy is not in fact
  identical and the run is void --- that would mean the belief change is moving
  the play in a way this design assumes it does not.

## What a null would mean

That a 35.3%-against-28% regularity is too weak to move a game, which would be
worth knowing precisely because it is free. It would also put a floor under the
convention direction: if reading the coincidence is worth nothing, then buying
a stronger signal has to pay for itself entirely out of the difference between
40.1% and 35.3%, and `prereg/convention_duel.md` has already measured what
buying more than that costs.

---

# INTERIM, recorded 2026-08-29: straddle, extending as registered

1,200 duplicate-deal pairs. Y minus X, positive = the free-read side is
stronger:

**+0.055 sets/game [-0.140, +0.250]** (457W / 270T / 473L)

The point estimate just clears the +0.05 bar and the interval straddles it, in
both directions: it contains zero and it contains effects twice the bar. The
registration anticipated exactly this and fixed what to do:

> **n_pairs:** 1,200 to start. If the interval straddles the bar, extend to
> 3,000 rather than reading a straddle as a result.

Extending to 3,000, same base seed --- so the 1,200 is a prefix of the larger
run and is superseded by it rather than pooled with it. **This interim is not a
result and licenses nothing.** It is recorded only so that the extension cannot
later look like a decision made after seeing which way the numbers went.

The one thing it does establish, and the reason it was worth running before the
belief measurement: at `beta = 0.23` with the encoder deleted, the free-read
configuration is **not harmful**. The upper bound on the champion's side is
+0.140 sets, against the +1.467 that the mis-priced encoder cost.
