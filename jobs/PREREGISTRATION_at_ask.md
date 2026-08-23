# Pre-registration: does at-ask-time depth play better?

Written **before any of the five `at_ask` screening cells finished**. That timing
is the whole point, and it is checkable: the cells are queued behind the
precision run and this file is committed while that run is still on block four.

## The configuration, chosen from theory rather than from a screen

`fishbot4(opponent_gamma=1.0, depth_mode="at_ask")` against the champion,
`fishbot4(opponent_gamma=0.35)`.

Five arms are being screened and only this one is pre-registered, so the choice
has to be argued in advance or it is selection with extra steps. Two independent
measurements point at it and neither is a duel:

1. **The covariate.** Fitted as a conditional logit on 17,005 real decisions,
   depth at the moment of the ask beats initial-deal depth by **4,654 nats** —
   6,057 above uniform against 1,403. The shipped covariate reaches under a
   quarter of what its own one-parameter family can. And it costs a lookup
   table, because a successful ask is public, so at-ask depth is initial depth
   plus a world-independent delta (verified on 23,268 triples, zero mismatches).

2. **The exponent.** The likelihood drops a denominator that is exactly constant
   at $\alpha = 1$ and only there. Measured across worlds, the coefficient of
   variation of the dropped term is $0.000$ at 1, $0.035$ at 1.207, $0.226$ at
   2.195 — and $0.100$ at the shipped $\gamma = 0.35$. So $\gamma = 1.0$ is the
   unique exponent at which this model is correctly specified, and the engine
   currently sits further from it than the fitted value does.

Neither argument is that a cell scored well. The fitted exponent on the at-ask
covariate is 2.195, not 1.0, so this configuration is a deliberate compromise:
the better covariate at the exponent where the normaliser is exact, rather than
at the exponent the data prefer with a normaliser that is not.

## Effect size assumed for sizing

**+0.15 sets per deal-pair**, as a *minimum interesting effect* rather than an
estimate — the same threshold the precision pre-registration used, and for the
same reason. It is roughly what the lookahead turned out to be worth. No
screening cell contributes a number to this calculation, so there is nothing for
selection to inflate.

## Design

- **6 blocks × 1000 pairs = 6000 duplicate deal-pairs**, fresh seeds throughout.
- Per-pair standard deviation **3.796**, from the 4800 A/A pairs.
- **MDE at 80% power is 0.137**, under the 0.15 threshold.
- Runtime is close to the champion's: the table is built once per decision and
  read with a gather, so this is not the three-times-cost experiment the
  precision run is.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 6 blocks. Every block is unselected, so no
cell may be dropped for its result. **Demonstrated** if and only if this 95%
interval excludes zero.

**Homogeneity.** Cochran's $Q$ across the 6, diagnostic only, read as in the
lookahead pre-registration.

**Reported alongside, not decisive.** All five screening cells, labelled as
screens, including the four this run does not test.

## Committed in advance

- No cell will be excluded on the basis of its result.
- If the primary interval includes zero, the result is **not demonstrated**,
  whatever any screen said.
- No further run will be added to chase significance.
- **If this arm fails and a different screen looks better, that is a screening
  result and needs its own pre-registration.** Substituting the better-scoring
  arm into this document would convert a fixed analysis into a chosen one, which
  is the specific error this project has now made four times.
- A demonstrated effect changes `depth_mode` and `opponent_gamma` together or
  not at all. They were argued for jointly and the screens cannot separate them;
  claiming either alone from this run would be reading a two-factor change as if
  it were one.
