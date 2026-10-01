# Pre-registration: what the wrong-signed opponent model costs, and whether anything should be done about it

Written before any game of this program is played.

## The finding this responds to

`results/choice_curve_foreign.json`. Our sampler re-weights sampled deals by
`depth^gamma` with `gamma = +0.35` for every seat that is not itself. Measured
against Dylan's v0.7 over 6,090 of his asks in 150 cross-engine games, his
propensity exponent is

    alpha = -1.0041,  95% CI [-1.1434, -0.8648]   (clustered over deals)

against our own self-play `alpha = +1.2071`. Opposite signs. On three of the
six seats at the exhibition table we up-weight worlds in which he is DEEP in
the half-suit he just asked in, when the evidence says he is more likely
shallow.

## Why this is dangerous to act on, stated before acting

This project has already withdrawn a feature for exactly the failure this
invites. The endgame ladder above m=2 grew with its dose against a sibling
configuration and reversed against a foreign engine, because what it measured
was deception of the sibling's opponent model rather than strength. A per-seat
exponent FITTED on v0.7 and VALIDATED on v0.7 would reproduce that error with
the arrow pointing the other way, and it would look like a large win while
doing it.

So the question this registers is deliberately not "does splitting gamma beat
v0.7". It is two narrower questions whose answers are useful whichever way
they fall.

## G1 -- What does the mis-signed model cost us, if anything?

Arms, all against v0.7, paired duplicate deals, seats rotated, fresh seed
block 1,800,000+:

  A  gamma = +0.35   (shipped)
  B  gamma =  0.0    (no opponent model at all: legality carries the signal)
  C  gamma = -1.00   (his measured exponent, applied to HIS seats only)

400 deals x 2 rotations per arm. Statistic: paired difference in set margin
against arm A.

Fixed now, before any game:

- **Minimum interesting effect 0.15 sets/game**, this project's standing ship
  bar (`fish4/registry4.py`).
- If B beats A by more than the bar, the honest reading is that our opponent
  model is a LIABILITY against a foreign policy, not an asset, and the paper's
  "+1.92 sets/deal-pair for the opponent model" becomes a self-play-only
  claim. That would be the most important result here and it is the one we
  are least expecting.
- If C beats A but B does not, the model is worth having and its exponent is
  policy-specific. That licenses nothing on its own -- see G2.
- If neither clears the bar, the mis-signed exponent is costing us little,
  the finding stays a measurement about his engine, and no knob is built.
  **This is the outcome we expect**, because gamma enters as one scalar
  re-weighting of a 480-draw sample and the sampler is already dominated by
  hard constraints; writing that expectation down now is the point.

## G2 -- Does anything fitted on v0.7 survive contact with an engine it was
not fitted on?

Runs ONLY if G1's arm C clears the bar. Same three arms, unchanged, against
**the v0.3 champion** -- a foreign policy in the sense that matters here: its
asks were never used to fit anything in arm C.

- C must clear the bar against v0.3 as well, on the SAME fixed setting fitted
  against v0.7, with no refitting. Anything less and it is opponent-specific
  and is not shipped.
- If C wins against v0.7 and loses against v0.3, that is the deception-ladder
  signature and it is reported as such, prominently, because it is the second
  independent instance of the same trap in this project and that is worth more
  than the knob would have been.

## What ships

Nothing, unless G1 arm C and G2 arm C both clear +0.15 with intervals clear of
zero. A per-seat exponent would additionally need a rule for seats whose
policy is unknown -- the site plays humans, and a human is not v0.7 -- and
that rule is out of scope here and would need its own registration.

## Analysis discipline

Paired per deal, standard errors clustered over deals rather than decisions.
Every runner pins `wrong_distribution_outcome="opponent"` explicitly and
records the engine digest and `BRIDGE_REV`. No arm is inspected before its
block completes.
