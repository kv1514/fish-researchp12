# Pre-registration: is exact m = 1 endgame play worth anything in play?

Written before any run above 40 paired deals, and before the raised-cap firing
rate came back.

## What is being tested

`fish4/endgame_ii.ExactEndgameMixin` replaces the heuristic at m = 1 decisions
with `fish4.exact_ii`'s exact best response, when the support is enumerable and
small. Off by default. The measurement is a duplicate-deal paired comparison
against the identical configuration with the flag off.

Three arms, distinguished by whether the solver's opponent model is right:

* **one** -- seat 0 alone. Five champions and us, which is exactly what the
  solver assumes. The only honest configuration, and the one that corresponds
  to the exploitability bound.
* **team** -- seats 0, 2, 4. Right about the opponents, WRONG about the two
  teammates, who no longer play the champion's move. This is the configuration
  anyone would actually ship.
* **all** -- every seat. Wrong about everyone.

## What is already known, exactly

`results/ii_first_endgame.json`: deviating optimally at the FIRST hidden m = 1
decision is worth **+0.1111** per game, CI [+0.0460, +0.1761], for one seat,
against a deterministic realisation of the champion. An agent that deviates at
*every* solvable hidden m = 1 decision should do at least that well in the
`one` arm, since it takes that deviation and more.

`results/ii_action_diff.json`: the champion picks the exact optimum at 30% of
hidden m = 1 decisions, and the cost spread over every such decision is
+0.2005.

## The scoping problem this exists because of

At the shipped caps (support <= 12, 50,000 nodes) the policy fired **2 times in
40 games** in the `one` arm. The measured +0.000 +/- 0.000 was therefore a
measurement of nothing, and it reads exactly like a clean null. Firing counts
are reported with every arm from now on.

The design is unusually cheap for the same reason. Because the intervention is
rare and the comparison is paired on the deal, most paired games are identical
and contribute exactly zero to the difference, so the variance of the paired
difference is tiny: +/-0.083 at 40 pairs, where this project's screens normally
need thousands. Extrapolating, about 300 pairs resolves +/-0.03.

## Predictions

1. **The firing rate rises with the caps but stays under one per seat per
   game.** `results/ii_endgame.json` has 305 solvable hidden m = 1 positions
   over 200 games across all six seats -- 1.5 a game, so 0.25 per seat per
   game. This is arithmetic from a measured file, not a guess.

2. **`one` comes out positive, and at least +0.05.** This is the prediction
   with a mechanism: the arm reproduces the exploitability setup, the exact
   computation says one decision is worth +0.1111, and this agent takes that
   decision and every later one. The risks are that the play harness scores
   whole games rather than the endgame subgame, and that firings are too few
   for the effect to appear at the sample size run.

3. **`team` is smaller than `one`, and I will not predict its sign.** The
   solver best-responds to a partner that does not exist. Last time I predicted
   a sign from an argument rather than a mechanism I was wrong, and this is an
   argument.

4. **`all` is the worst of the three.** Every seat optimising against a model
   of the other five that none of them match.

5. **No stalling anywhere.** Already measured at 40 pairs: zero unresolved
   half-suits in every arm, nulls unchanged. Recorded because a best response
   maximising the endgame value could in principle refuse to claim, and the
   harness scores an unresolved half-suit for nobody.

## What would make this not worth shipping even if it wins

A best response is not an equilibrium strategy. If `one` gains and `team` does
not, the honest reading is that the solver exploits a champion rather than
playing Fish better, and shipping it into a team makes the engine stronger
against this opponent and no more sound.
