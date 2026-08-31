# Pre-registration: does `unlocated_now` make the BELIEF better, not just the fit?

**Registered 2026-08-31, before any belief-space measurement of this covariate
exists.** `prereg/choice_basis.md` licensed exactly this step and required it to
carry its own registration; this is that document. Nothing about how the
covariate behaves inside a posterior has been run or looked at.

## What is already established, and what it does not establish

`results/choice_basis.json`, 17,005 choices over 200 games, held out at the game
level:

    M2 held^a                     cv_loglik  -17268.5   a =  2.1951
    M4 unlocated^a                cv_loglik  -16587.0   a = -4.8407
    M5 held^a unlocated^b         cv_loglik  -14125.5   a =  1.6929,  b = -3.9568

The primary outcome fixed in `choice_basis.md` was `D = M5 - M2 = +3,143` nats
against a bar of 1,000, so the covariate is **licensed to build**. M5 beats M4,
so that document's instability withdrawal condition did not fire.

What this does NOT establish is the thing that matters. A conditional logit over
the half-suits a teammate chose is scored on *predicting the ask*. The engine
does not want to predict asks; it wants a posterior over *where the cards are*.
The last attempt on this exact frontier -- `gamma_team`, believe the teammate
model harder -- produced a **better NLL and a worse top-1** and was refuted. A
fit gain is a licence to measure, and this document is the measurement.

## The sign, and why it needs saying out loud

`b` is **negative**. The model says a teammate prefers a half-suit with FEWER
unlocated cards, which is not a quirk: a card the public record can already
place is a card you can ask for and receive. The attractive half-suit is the
one that is nearly resolved, not the one that is wide open.

That makes `unlocated_now = 0` a real and legal state -- hold a card, know where
all six are -- and `0 ** -3.9568` is unbounded.

**Clamp, fixed here and not later.** The belief uses `u = max(unlocated_now, 1)`.
`choice_basis.py` clamps at `EPS = 1e-12`, which is harmless inside a
log-likelihood and would be catastrophic inside a sampler: it would hand one
half-suit a weight of order `10**47` and make the teammate model deterministic.
Treating "none unlocated" and "one unlocated" alike is the conservative reading
of the same evidence, and it is chosen now precisely because choosing it after
seeing the posterior scores would be a free parameter wearing a bug's clothes.

## Design

**Build.** `fish4/oppmodel.py` gains `w_unlocated: float = 0.0`, multiplying the
existing per-half-suit weight by `max(unlocated_now, 1) ** w_unlocated`. At the
default the branch is not entered at all, so the shipped engine is
**bit-identical** -- the same discipline as `w_contest=0.0`, `endgame_m=0` and
`stuck_team_certain=1.01`. A test asserts the bit-identity rather than trusting
it.

**Instrument.** `scripts4/unlocated_belief.py`, built as a sibling of
`scripts4/gamma_split.py` and inheriting its design decisions verbatim:

* games are generated ONCE at the incumbent, and every cell is scored on the
  SAME positions, so the grid is a paired comparison and no cell is scored on
  the positions its own play would have reached;
* the truth is used only to SCORE, never to act;
* cards are scored in two disjoint pools by where the card ACTUALLY is -- `team`
  and `opp` -- restricted to cards the propagator has NOT pinned, since a pinned
  card is scored perfectly by every cell and only dilutes the contrast.

**Grid.** `w_unlocated` over `(0.0, -0.5, -1.0, -2.0, -4.0)`, with `0.0` the
incumbent and `-4.0` about the fitted `b`. Positive values are not swept: the
fit's sign is not in doubt at 3,143 nats, and sweeping both signs would spend
half the grid establishing something already measured.

## Primary outcome and decision rule, fixed in advance

The pool that matters is **team**. This covariate exists to attack the
distributed-knowledge problem inside our own team, 95.3% of this engine's
residual errors are allocation errors, and the opponent pool is carried to show
the change is not simply moving error from one side to the other.

Let `w*` be the grid cell with the best team-pool NLL. Compared against
`w_unlocated = 0.0` on the same positions, clustered **by game** -- asks inside
one game share a deal, a policy realisation and a seed, and
`fish4/clustered.py` is the one implementation, at *t* on *k-1* df:

* **SHIP-CANDIDATE** requires **BOTH**, each with a 95% interval excluding zero:
  team NLL improves, AND team top-1 improves.
* **REFUTED** if team NLL improves and team top-1 does not. That is the exact
  signature `gamma_team` produced, and it means the model has become better at
  hedging rather than better at knowing.
* **REFUTED** if the best cell is `w_unlocated = 0.0`, the incumbent.
* A ship-candidate is a candidate only. It buys a duel under a further
  pre-registration; it does not enter `V06_DEPLOYED` on a posterior score, for
  the same reason a fit did not buy it a place in the posterior.

## Withdrawal conditions

* If `unlocated_now` is not recoverable inside the belief from the public record
  alone -- if computing it needs anything the observing seat cannot see -- the
  whole design is void. It is common knowledge or it is nothing, and a covariate
  that leaks is a bug, not a finding.
* If the bit-identity test at `w_unlocated = 0.0` fails, no measurement is read
  until it passes. A default that is not inert makes every cell a comparison
  against a moved baseline.
* If fewer than 8 games survive to give clusters, the interval is not reported:
  `k < 8` is too few for *t* on `k-1` df to mean much, and #83 in this project
  is what happens when that is ignored.
