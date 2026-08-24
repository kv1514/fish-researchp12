# Architecture Notes

Why the system is shaped the way it is. Every decision below was made
because of a measurement or a proof, and the ones that were made on
intuition and later disproved are marked as such.

---

## 1. The information boundary is a hard wall, not a convention

`GameState` holds the truth. `Observation` holds what a seat may legally
know. Policies receive only `Observation`, and the single place the two meet
is `runner.play_game`.

This is enforced, not merely intended:

- `Observation.reconstruct` rebuilds a seat's entire view from
  (rules, own initial hand, public event log). Tests assert the engine's
  observation is *identical* to that reconstruction at every step of full
  games, for all six seats. If any private state leaked in, the two would
  diverge.
- Feature vectors get the same treatment: tests assert they are unchanged
  when hidden cards are permuted into any other layout consistent with the
  public record.
- Agent RNG seeds are drawn from a stream independent of the deal. This was
  a real leak, found by audit: seeds were derived from the deal seed, so a
  determined policy could in principle invert its own seed to recover the
  layout.

Training may use ground truth (the value net is trained on true states);
*acting* may not. That line is what makes the distinction meaningful.

## 2. Beliefs are exact because Fish makes them exact

Every card movement in Literature is public: a successful ask names the
card, a claim reveals all six locations. So a card's current location is a
deterministic function of the initial deal plus the public log, and *all*
hidden-state inference reduces to constraints on the initial deal:

- per-card candidate sets over initial owners (6-bit masks),
- exact per-player deal counts,
- OR-constraints from ask legality ("the asker held at least one of that
  half-suit at that moment").

This is why the tracker is exact rather than a heuristic filter. It is
**sound** (the true world is never excluded; tested continuously) but
deliberately documented as **not complete** (no full arc-consistency) and
the sampler as **not uniform** over consistent worlds. Overstating either
would be the easiest way to mislead ourselves.

## 3. Bitmask hands

Hands are integers; a half-suit is a mask. Membership, transfer, and
half-suit intersection are single integer operations, and a whole hand
compares and hashes in one step, which is what makes exact endgame solving
and fast determinization practical.

## 4. Search is built around variance, not depth

The central measured fact: **the spread of a position's value across
possible hidden layouts is about 2.4x the gap between the best and worst
candidate move.** Consequences that shaped the design:

- Any search that evaluates different candidates against different sampled
  worlds ranks luck. PIMC and ISMCTS both lost to their own prior for this
  reason.
- The fix is common random numbers: identical worlds and identical rollout
  seeds across all candidates, so world luck cancels in the *comparison*.
- Search additionally only overrides the prior when the paired difference is
  statistically significant. A search that can merely nudge a strong prior
  is far safer than one that can replace it with noise.

## 5. Two feature spaces, on purpose

`extract` (belief space) describes an uncertain position. `extract_perfect`
describes a fully-known one.

Mixing them was a real, measured failure: a value net trained on belief
features and applied inside determinized worlds lost 34-6, because inside a
sampled world every location is certain and the belief features take values
the net never saw. A value function must be trained on the distribution it
will be *used* on.

## 6. Exact solving needs value iteration, because Fish is loopy

Two opponents can trade a card back and forth and return to an identical
position. The state graph is **cyclic**, so backward induction does not
terminate. The solver instead works in layers: claims strictly reduce the
number of unresolved half-suits (so they always descend), while asks and
passes cycle within a layer and are solved by value iteration to a fixpoint.

Non-terminal in-layer states start at value 0, which encodes the honest
semantics of an unbroken cycle: if play never progresses, nobody scores
again. A side that can only lose by claiming will therefore prefer to stall
forever, which is exactly what real Fish stalemates look like.

Tractability is bounded and stated: a layer with k live cards has up to 6^k
placements. One half-suit solves in seconds; two is hopeless, so the solver
refuses loudly above 9 live cards rather than hanging.

## 7. Evaluation is paired by construction

Every deal is played twice with the teams swapped, on the same cards, the
same rotated starting seat, and the same agent seed. Only the policy
assignment differs. Per-pair differentials are then i.i.d. across deals.

Ratings use a regularized MAP Bradley-Terry fit. This matters because
shutouts are common here, and an unregularized maximum-likelihood gap
between a policy that never loses and one that never wins is *infinite*. The
first implementation reported whatever a fixed-iteration loop happened to
reach; those ratings were retracted. Separated policies are now flagged so
their numbers are read as bounds.

## 8. Python, deliberately, for now

Profiling says inference dominates, not rule application: belief world
sampling cost 736 microseconds per world, roughly 30x the per-decision cost
of belief updates, while the rule engine was never the bottleneck. Caching
the constraint scaffolding across draws and satisfying disjoint
OR-constraints during construction (rather than repairing afterwards) cut
that to 178 microseconds, a 4.1x win with no language change.

A compiled core is not yet justified. It becomes justified when rule
application, not inference, is measured to dominate.

## 9. The web platform is a spectator, not a participant

The browser may display all six hands because a viewer is not a policy. The
server drives agents through exactly the same `Observation` boundary as
every other harness. It is stdlib-only (http.server + vanilla JS) so the
platform runs anywhere Python does, with no install step and no build.
