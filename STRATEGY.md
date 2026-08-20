# Strategy Book

The strategy book is evidence-gated. Statements are promoted only when their
support comes from reproducible, paired simulations with uncertainty estimates.

## Statistically demonstrated

- The implemented BasicHeuristic decisively beats the deliberately weak
  RandomAgent, whose hierarchical policy makes speculative claims with fixed
  probability. Across 100 duplicate deals / 200 team-swapped games, the
  heuristic scored 100% of game points (Wilson 95% lower bound 98.12%) with a
  paired margin of +6.13 half-suits [95% CI +5.98, +6.28]. This validates the
  baseline ladder and variance-control method; it is not a subtle prescription
  for expert human play.

## Likely, awaiting controlled ablation

- A 16-particle probabilistic policy beat the basic heuristic in a preliminary
  30-duplicate-deal run: 86.67% points [95% Wilson CI 75.83%, 93.09%], paired
  margin +2.97 [95% CI +2.43, +3.50]. This is statistically separated from 50%
  in that run, but the sample is modest and the agents differ in claim logic as
  well as belief-based asking. A controlled belief ablation and larger sample are
  required before promoting “belief tracking adds this much value” to the
  demonstrated section.

## Speculative hypotheses queued for testing

- The best ask may trade immediate acquisition probability for control of which
  opponent receives the turn on failure.
- A completed but unclaimed half-suit may have option value as a legal turn
  transfer mechanism when claims can choose the next teammate.
- The 8/Joker half-suit may differ strategically because all four ordinary cards
  share a visible rank while the jokers have unique requestable identities.
- Belief correlations and exact hand-size constraints may matter most late in the
  game, when independent marginals become overconfident or inconsistent.

These are experiment prompts, not recommendations.
