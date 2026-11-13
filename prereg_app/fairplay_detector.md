# Pre-registration: is the fair-play detector fair, and does it catch anyone?

> Kept in `prereg_app/`, not `prereg/`, on purpose. `prereg/` is the research
> record the paper counts ("fifty-five pre-registrations produced exactly one
> change to the engine"); this one is about the app's cheat detector and
> changes nothing in the engine, so it must not move that count. It is held to
> the same rules: written before the run, results appended, never edited.

**Registered 2026-11-13, before `scripts4/fairplay_calibration.py` has been
run.** What has been read: one engine-vs-engine game timed in scratch, where
the asking seats landed 71 of 114 asks against 70.7 expected. Nothing else.

## The instrument

`api/_fairplay.py` as committed with this file: `assess()` scores each ask by
the probability, from the mover's own information, that the target holds the
card, and each declaration by the probability the declared split is right.
`flags()` applies four rules -- asks, declarations, focus-lost asks, engine
match -- at the thresholds in that file (z >= 4.0 with an 8-point excess for
asks; z >= 4.0 for declarations; match >= 0.90 over >= 80 open decisions).

## Players simulated

Seats 0 and 1 (opposite teams) are the players under test; the other four are
the engine. Every policy runs as its own persistent agent with its own seed,
so an "engine" player is NOT the server's assessment helper replayed.

| Name | What it is |
|---|---|
| `engine` | Our engine. Honest, and exactly what an engine-assisted human looks like. |
| `dylan` | Dylan's FishBot v0.7, a different engine. Honest, and the stand-in for a strong player whose choices our posterior did not model. |
| `peek50` | Our engine, but on half its turns, if a legal ask exists for a card an opponent really holds, it asks for one. |
| `peek15` | The same on 15% of turns: a careful cheater. |
| `share` | Our engine, but it declares any half-suit its team wholly holds, with the true split, the moment it is its turn: teammates reading their hands to each other. |

Focus loss and think time cannot be simulated (bots have no app to leave and
no clock to feel), so those two signals are not tested here.

## Quantities

Per seat-game: asks, hits, expected hits, variance; the same for declarations;
open decisions and engine matches. Careers of K games are formed by resampling
seat-games of one policy with replacement (B = 2000, fixed seed), and the
whole flag rule set is applied to each career's accumulated tally.

## Decision rules, fixed now

1. **Calibration.** For `engine`, the mean per-game excess hit rate
   ((hits - expected) / asks) must have a 95% interval inside [-0.03, +0.03].
   If it does not, the ask test is miscalibrated in-model and does not ship.
   For `dylan` the same interval is REPORTED; if its upper end exceeds +0.04,
   `ASK_EXCESS` is raised to (that upper end + 0.04) and the change recorded.
2. **False positives.** Over the honest policies, the career flag rate from
   the ask and declaration rules must be <= 1% at K = 10, 25 and 50.
3. **Power.** `peek50` must be flagged in >= 90% of careers at K = 10. The
   K at which `peek15` and `share` reach 90% is reported, whatever it is.
4. **Engine match.** `MATCH_RATE` stays at 0.90 only if the 99th percentile
   of `dylan` career match rates at K = 10 is below 0.80. Otherwise it is
   raised to that percentile + 0.10. `engine`'s own career match rate is
   reported: if it is below 0.90, the engine rule cannot catch an engine
   user and that is stated as a limitation, not tuned away.

## What would make me wrong

If the honest in-model player is miscalibrated, the core claim of the
detector -- that honest hits add up to the sum of `p` whatever a player
remembers -- fails, and the ask rule does not ship.

---

## Round 1 result (2026-11-13), and what it changed

500 games, 1,000 seat-games (`results/fairplay_calibration.json`). Against the
rules above:

1. **Calibration: FAILED.** `engine`'s mean per-game excess hit rate was
   +0.019 (95% CI +0.004 to +0.033); the bar was inside +/-0.03. Pooled over
   asks, honest players land more asks than the posterior predicts: `engine`
   +0.028, `dylan` +0.037 per ask. The posterior is slightly under-confident --
   the same direction as the split joint's under-confidence recorded in
   `scripts4/split_why.py`. Per this file, the ask test as registered does
   not ship.
2. **False positives: FAILED, badly for declarations.** `dylan` careers
   flagged at 7.8% (K = 25) and 32.6% (K = 50), almost all from the
   declaration rule: Dylan's bot is right on declarations our posterior calls
   uncertain (+0.082 per declaration). The ask rule alone reached 3.0% (K = 25).
3. **Power: passed.** `peek50` flagged in 100% of careers at K = 10 (99.95% at
   K = 5); `share` at K = 10 (100%, via declarations); `peek15` needs K = 50
   (95%).
4. **Engine match: kept at 0.90, and useless.** `dylan`'s p99 at K = 10 was
   0.451, so the rule stays -- but `engine` itself matches the assessment
   helper on only 47% of open decisions, because the policy samples. An
   engine user cannot be told from anyone else this way. Recorded as a
   limitation; the rule is removed rather than left looking like protection.

## Round 2: margin tests, chosen from round 1, confirmed on fresh games

A z-test against the plain expectation turns any constant miscalibration into
a flag given enough games. So test against a MARGIN above it:

    z_m = (hits - expected - m * n) / sqrt(max(var, 1))

An honest player whose true excess is below `m` drifts to negative z_m as they
play; a cheater whose excess is above `m` drifts up like the square root of
their move count.

* asks (and focus-lost asks): `m = 0.05`, flag at z_m >= 4, n >= 40. Round 1's
  largest honest pooled excess was 0.037.
* declarations: `m = 0.25`, flag at z_m >= 4, n >= 10. Round 1's largest
  honest excess was 0.082 per declaration; hand-sharing ran 0.49.
* engine match: removed as a rule (see 4); the rate stays in the review data.

These numbers were picked LOOKING at round 1, so round 1 cannot confirm them.
**Confirmation run:** 500 fresh games (`--seed-offset 100000`), same players,
analysed with the rules above. They ship if, on the fresh games:

* honest (`engine`, `dylan`) career flag rate <= 1% at K = 10, 25, 50 and 100;
* `peek50` >= 90% at K = 10 and `share` >= 90% at K = 25.

`peek15`'s K for 90% is reported whatever it is; it is expected to be large,
and that is the price of the margin: a cheater who uses it rarely is caught
slowly. If either condition fails, nothing ships as automatic flagging and the
numbers go to review only.

## Round 2 result (2026-11-13): ships

500 fresh games (indices 100000-100499), 1,000 seat-games, analysed with the
margin rules exactly as written above (`results/fairplay_calibration_r2.json`).
Flag rate over 2,000 resampled careers per cell:

| player | K=5 | K=10 | K=25 | K=50 | K=100 |
|---|---|---|---|---|---|
| `engine` (honest) | 0 | 0 | 0 | 0 | 0 |
| `dylan` (honest) | 0 | 0 | 0 | 0 | 0 |
| `peek50` | 0.966 | 1.000 | 1.000 | 1.000 | 1.000 |
| `share` | 0.172 | 0.634 | 0.987 | 1.000 | 1.000 |
| `peek15` | 0.048 | 0.118 | 0.502 | 0.914 | 1.000 |

Both conditions hold: no honest career flagged at any K (bar: <= 1%),
`peek50` 100% at K = 10 and `share` 98.7% at K = 25 (bar: >= 90%). The margin
rules ship. `peek15` needs about 50 games, as expected.

What this does NOT establish: that human players are calibrated like these
two engines. Both honest players here are programs; a human whose asks beat
the posterior by more than 5 points for reasons other than cheating would
drift towards a flag. That is what the review step is for, and the first real
data from rated tables is the next calibration.
