# Pre-registration: does the ask correction pay at three live half-suits?

Written before any pair of this run.

## Where this comes from

The correction that ships (`endgame_m = 2, endgame_d_info = +2.0`) applies only
when at most two half-suits are live, which is **9.7% of decisions** measured
over 20 games. It is worth +0.1220 sets [+0.0711, +0.1729] on top of the
deployed configuration.

Three things now say the same defect exists at m = 3, which is a further 7.8%
of decisions:

1. A **sampled** one-ply target — posterior worlds instead of an enumerated
   belief — makes the same decisions as the exact target where both exist, at a
   cost of +0.0033 in the exact target's own units at 128 worlds
   (`results/oneply_sampled_check.json`).
2. Under that target at m = 3, the engine's ask is beaten on 23/24 positions,
   the better ask is riskier on 19 and safer on 1, and its hit rate is 0.4925
   below the engine's at t = −6.02 (`results/oneply_m3_defect.json`).
3. That 96% is a maximum over a noisy estimate, so it was **cross-fitted**:
   choose on sample A, score on sample B. The gain survives at **+0.2979
   [+0.0966, +0.4992]**, with 49% of the naive figure identified as selection
   bias (`results/oneply_crossfit_m3.json`).

## The arm

`x` = the deployed configuration. `y` = the same with `endgame_m = 3`.
Everything else identical, including `endgame_d_info = +2.0` — **the weight is
not refitted for m = 3.** Refitting would introduce a second free parameter
chosen on the same evidence that motivated the arm, and the question here is
whether the existing correction extends, not whether a new one can be tuned.

8 blocks of 250 pairs at 3 workers, base seeds 771000+, agent seeds 6610..6617.
2000 pairs. The evidence above comes from games seeded 99000+, so the duel
deals are disjoint from everything that motivated it.

## What each outcome means

1. **CI entirely above 0** — it extends. Ship `endgame_m = 3` into
   `V04_COMBINED` and `WEB_SPEC`, and report this interval.
2. **CI straddles 0 with a positive point estimate** — unresolved. Do not ship.
   The offline evidence does not license a default change on its own; that is
   the rule the m = 2 stacking run was held to and this is held to it too.
3. **Point estimate at or below 0** — it does not extend, whatever the offline
   target says. Report that the sampled target identified a defect that does
   not convert into play, which would be worth more than the change: it would
   mean the one-ply target stops predicting play somewhere between m = 2 and
   m = 3, and everything built on it above the endgame is suspect.

No second run under outcomes 2 or 3.

## What this cannot tell us

If it does extend, this run cannot say whether `+2.0` is the right weight at
m = 3 or merely a positive one, because the weight was deliberately not
refitted. A separate, later experiment would be needed for that, and its
result would not be licensed by this one.

## Amendments

None yet.
