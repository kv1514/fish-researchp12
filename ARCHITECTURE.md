# Fish Engine Architecture

## Safety boundary

The simulator owns the complete deal. Policies receive an immutable
`PlayerObservation`, never a `GameState` or environment reference. Observations
contain only the acting player's hand, public events, public card counts,
resolved half-suits, scores, and turn metadata. Legal actions are derived by the
environment and copied into the observation. This boundary is covered by tests
that compare observations made from hidden states which differ only in
opponents' private card allocation.

Training code may later add a centralized value critic, but policy inference is
required to use the same observation interface as the baseline agents.

## Layers

1. **Rules and state**: compact integer card identifiers, explicit ruleset
   configuration, deterministic deals, authoritative transitions, claims, and
   invariants.
2. **Observation and belief**: public event stream plus per-player private hand;
   hard ownership constraints followed by normalized marginal probabilities and
   sampled consistent worlds.
3. **Policies**: random, heuristic, memory, probabilistic, and sampled-search
   baselines sharing one observation-only protocol.
4. **Evaluation**: seeded duplicate deals, team swaps, seat rotation, confidence
   intervals, and persistent experiment summaries.
5. **Interfaces**: CLI play, benchmark, tournament, and state analysis. Machine
   input uses stable JSON rather than Python object serialization.

## Performance path

The first implementation is deliberately a Python reference model because it
keeps rules and leakage audits inspectable. Profiling—not assumption—determines
the next optimization step. The likely compiled-core boundary is batched state
transition and legal-action enumeration, leaving experiment orchestration and ML
in Python. Any optimized core must pass the same transition traces and invariant
suite as the reference implementation.

## Research path

The baseline search is intentionally an auditable sampled-world lookahead, not a
claim that the game is solved. Natural next candidates are information-set MCTS,
outcome-sampling MCCFR on abstractions, recurrent public-history policies, and
population self-play. Promotion requires statistically controlled duplicate-deal
evaluation against the league rather than training loss alone.
