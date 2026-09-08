# Pre-registration: KRAKEN v1.2, and whether anything can beat SESTINA v1.0 honestly

Written before any candidate game of this program is played. The baseline block
named below was already running when this was written; no candidate arm was.

## Why this program exists, and why the prior work does not answer it

Through the repaired bridge (`BRIDGE_REV 3`) KRAKEN v1.1 **loses** to SESTINA
v1.0. Three independent measurements agree:

| route | our margin | games |
|---|---:|---:|
| our arbiter, dealt-hand arm | −0.6000 | 600 pairings |
| our arbiter, Nguyen's repaired bridge | −0.570 [−0.632, −0.508] | 8,000 |
| their arbiter, our bot package | −0.648 [−0.740, −0.556] | 5,400 |

So "beat SESTINA" means finding **more than about 0.6 sets per game**. For scale,
the largest single gain in the entire study is the opponent model at +1.92 sets
per *pair*, and the standing ship bar is ±0.15 sets per game.

**The prior exploration of this parameter space does not transfer, and that is
the reason to register rather than to resume.** Every measurement this project
took against v0.7 went through a bridge that reset their engine with the hand it
held rather than the hand it was dealt, corrupting the posterior their policy
reads (`results/bridge_dealt_hand_price.json`; +3.0833 [+2.7917, +3.3749] to us).
A knob rejected for failing the bar against a handicapped opponent has not been
tested against this one. A knob accepted against it is worse off still.

One artifact is squarely on this program's critical path.
`results/choice_curve_foreign.json` fits SESTINA's half-suit-choice propensity at

    alpha = -1.0041, 95% CI [-1.1434, -0.8648]

against our own self-play +1.2071, and concludes "OPPOSITE SIGN -- our model
re-weights his worlds backwards". That fit was taken through the defective
bridge, on asks a scrambled belief chose, and **the file records no
`BRIDGE_REV`**, so nothing would have caught it. It is re-measured under R0
below before any arm depends on it.

## The deficit, named before the candidates

Both projects' instrumented runs put our declarations level with theirs and our
**asking** behind:

| | ours | theirs |
|---|---:|---:|
| declaration accuracy, repaired | 97.4% | 96.9% |
| ask hit rate, our arbiter repaired | 52.5% | 54.9% |
| ask hit rate, their arbiter | 53.8% | 56.0% |

Candidates are therefore drawn from the ask channel. Naming that here is what
stops a later sweep over the claim knobs from being reported as though it had
been the plan.

## R0 -- Re-measure the foreign choice curve. Not a candidate.

`scripts4/choice_curve_foreign.py` through `BRIDGE_REV 3`, 150 games, same
estimator and clustering as the original. This is a measurement of their engine,
not a knob, and it ships nothing whichever way it falls. It exists because C1's
arm C is defined in terms of it.

Fixed now: if the re-measured alpha is within its own interval of +1.2071 (our
self-play value), the "opposite sign" finding was a bridge artifact and the
paper's §11 discussion of it is withdrawn along with the rest. If it remains
negative, the finding survives its instrument and stands.

## The candidates, fixed now

Three, and only three. Each is a single flag on `V06_DEPLOYED`; no combination
is measured until the singles report (the stacking rule is below).

**C1 -- the opponent model against the real opponent.**
Arms `gamma = 0.35` (shipped), `gamma = 0.0` (no opponent model; legality alone
carries the signal), `gamma = alpha_hat` from R0 applied to their seats only.
Rationale: the ask objective is where the deficit is, the opponent model is the
largest single gain in the study, and its only foreign fit is invalid.

**C2 -- `avoid_doomed_asks=True`.**
Never make an ask that provably cannot land while one that can is available.
It targets the measured deficit directly and mechanically: a doomed ask is a
guaranteed miss and a lost turn.

**C3 -- `depth_mode="atask"` at `gamma_schedule` unchanged.**
At-ask-time depth was demonstrated at +0.102 over 6,000 pre-registered pairs in
self-play and deliberately not shipped, because 0.102 is under the 0.15 bar.
It is admitted here as a candidate against a *different opponent*, which is a
new question and not a second look at the old one. If it clears here and not in
self-play it is opponent-specific and does not ship -- see the bar.

## The bar. Both halves, or it does not ship.

A candidate ships only if it clears **+0.15 sets/game with a 95% interval clear
of zero in BOTH**:

1. against SESTINA v1.0 through `BRIDGE_REV 3`, paired duplicate deals, and
2. against the **v1.1 champion in self-play**, paired duplicate deal-pairs.

The second half is not ceremony. This project has already withdrawn one feature
-- the endgame ladder above m=2 -- for growing with its dose against a sibling
and reversing against a foreign engine, and `prereg/gamma_policy_specific.md`
declined to ask "does splitting gamma beat v0.7" for the same reason. A change
that beats one opponent and nothing else is an exploit of that opponent, it is
not strength, and this program will not ship one however large it is. A
candidate that clears against SESTINA and fails self-play is **reported
prominently as opponent-specific** and left out of v1.2.

## Multiplicity, and the confirm stage

Three candidates at 95% is roughly a 14% chance of one false positive, and this
document is the place to say so rather than the discussion section.

- **Screen**: 300 deals x 2 seat parities per arm, seed block 9,300,000+.
- **Confirm**: anything clearing the screen re-runs on 600 deals x 2 parities,
  **fresh seed block 9,400,000+**, and must clear the bar again there. Screen
  and confirm are never pooled.
- Self-play arms use their own blocks and the same two-stage rule.

## Stacking

Measured only if two or more singles survive confirm, and then as its own arm
with its own confirm block. Naming a combination before its stacking run would
assert an additivity nobody has tested, which is the mistake
`fish4/registry4.py` records for `V04_COMBINED`.

## Expected outcome, written down in advance

**That none of the three clears 0.6, and that v1.2 does not beat SESTINA v1.0.**
The gap is four times the ship bar and larger than any single effect this
project has ever measured in a duel. The honest expected result of this program
is a v1.2 that is stronger than v1.1 by some amount smaller than the gap, and a
paper that says so. Writing that here is the point: if a candidate does come in
at +0.6 the first question will be what it is exploiting, and this paragraph is
what makes that question askable.

## Withdrawal conditions

- Any arm whose fallback count is non-zero is void, not adjusted.
- Any arm whose journal rows carry a `BRIDGE_REV` other than 3 is void.
- If a candidate's self-play arm moves *negatively* past the bar, it is dropped
  immediately whatever it does against SESTINA.

## Analysis discipline

Paired per deal, standard errors clustered over deals rather than decisions.
Every runner pins `wrong_distribution_outcome="opponent"`, records the engine
digest and `BRIDGE_REV`, and writes one row per game. No arm is inspected before
its block completes. The baseline block is `results/mega_match.json` at rev 3.
