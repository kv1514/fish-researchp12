# Pre-registration: does the endgame ask correction pay in play?

Written before any duel beyond a 40-pair timing pilot, whose result is
disclosed under **Pilot** below.

## Where this comes from

The exact solver established, on 388 endgame positions with the exact one-ply
value of every candidate ask:

* the champion's ask is beaten by another ask on 51% of unpinned m = 1
  positions and 61% at m = 2, and the better move is an **ask** (131/154 and
  128/138), so the defect is in ask selection;
* the better ask is **riskier** — p = 0.218 against the champion's 0.799 at
  m = 1, paired t = −18.88 — and on 73 of 122 the champion asked a card it was
  certain to get and was still beaten;
* but simply de-weighting the success probability does **not** fix it. The
  one-parameter scale family, which spans every positive weight on p, picks
  k = 1: no change.

What did help, on games held out from the fit, was raising the `info` term.

## The arm, fixed now

`endgame_m = 2, endgame_d_info = +2.0` against the unmodified champion.
Everything else identical. The weight moves only when at most two half-suits
are live; `tests4/test_endgame_weights.py` requires whole games to be
bit-identical when the knob is off, and requires the first divergence to occur
at two live half-suits or fewer when it is on.

`info = +2.0` was chosen on the **training** games (even game index) and
confirmed by leave-one-game-out CV inside them. The runner-up,
`certain = −0.50`, scored better on the held-out games (+0.1784 against
+0.1591) and is **not** being tested, because picking it would be picking by
the set that is supposed to be the check. It does not get to rescue this if the
primary fails, and it is not a second arm — there is no multiplicity here.

## Size, and the expected effect

**2000 duplicate-deal pairs**, base seed 771000, agent seed 7710. At 40 pairs
the CI half-width was 0.33 sets, so 2000 gives roughly ±0.047.

The effect should be **small**, and this is written down so that a null is not
later read as a surprise. The correction moves at most a handful of decisions
per game — those at m ≤ 2 — and on held-out endgame positions it improved the
selected ask's exact value by +0.0093 in half-suit units. Whole-game duels
average over everything else the two agents do identically. A test with
±0.047 resolution against an effect that may be a fifth of that is
**underpowered by construction**, and the honest report is the interval.

## What each outcome means

1. **CI entirely above 0** — the correction pays in play. Ship it and say by
   how much.
2. **CI entirely below 0** — it costs. The offline gain does not survive
   contact with whole games, and the reason is worth chasing: an ask that is
   better for the endgame may be worse for reaching one.
3. **CI straddles 0** — no detectable effect at this resolution. This is the
   most likely outcome and it is **not** evidence of no effect. It will be
   reported as "the offline improvement is real and this test cannot see it in
   whole-game play", with the interval, and the arm will **not** be shipped on
   the strength of the offline number alone.

No outcome licenses running more pairs until the interval clears zero. If 2000
does not settle it, that is the answer for 2000 pairs, and any extension is a
new pre-registration saying so.

## Pilot

40 pairs, same seeds: diff +0.100 [−0.230, +0.430]. That was run to time the
harness (55 s for 40 pairs) and is far too small to mean anything; it is
disclosed because it exists and because its sign is positive, which is exactly
the kind of thing that should not be allowed to look like a prediction. The
2000-pair run reuses base seed 771000, so those 40 pairs are a subset of it
rather than an independent sample, and no combining is claimed.

## Amendments

None yet.
