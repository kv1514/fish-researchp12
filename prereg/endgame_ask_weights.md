# Pre-registration: does the endgame ask correction pay in play?

Written before any duel beyond a 40-pair timing pilot, whose result is
disclosed under **Pilot** below.

## Where this comes from

The exact solver established, on 388 endgame positions with the exact one-ply
value of every candidate ask:

* the champion's ask is beaten by another ask on 51% of unpinned m = 1
  positions and 61% at m = 2, and the better move is an **ask** (131/154 and
  128/138), so the defect is in ask selection;
* the better ask is **riskier** — p = 0.218 against the champion's 0.799 at
  m = 1, paired t = −18.88 — and on 73 of 122 the champion asked a card it was
  certain to get and was still beaten;
* but simply de-weighting the success probability does **not** fix it. The
  one-parameter scale family, which spans every positive weight on p, picks
  k = 1: no change.

What did help, on games held out from the fit, was raising the `info` term.

## The arm, fixed now

`endgame_m = 2, endgame_d_info = +2.0` against the unmodified champion.
Everything else identical. The weight moves only when at most two half-suits
are live; `tests4/test_endgame_weights.py` requires whole games to be
bit-identical when the knob is off, and requires the first divergence to occur
at two live half-suits or fewer when it is on.

`info = +2.0` was chosen on the **training** games (even game index) and
confirmed by leave-one-game-out CV inside them. The runner-up,
`certain = −0.50`, scored better on the held-out games (+0.1784 against
+0.1591) and is **not** being tested, because picking it would be picking by
the set that is supposed to be the check. It does not get to rescue this if the
primary fails, and it is not a second arm — there is no multiplicity here.

## Size, and the expected effect

**2000 duplicate-deal pairs**, base seed 771000, agent seed 7710. At 40 pairs
the CI half-width was 0.33 sets, so 2000 gives roughly ±0.047.

The effect should be **small**, and this is written down so that a null is not
later read as a surprise. The correction moves at most a handful of decisions
per game — those at m ≤ 2 — and on held-out endgame positions it improved the
selected ask's exact value by +0.0093 in half-suit units. Whole-game duels
average over everything else the two agents do identically. A test with
±0.047 resolution against an effect that may be a fifth of that is
**underpowered by construction**, and the honest report is the interval.

## What each outcome means

1. **CI entirely above 0** — the correction pays in play. Ship it and say by
   how much.
2. **CI entirely below 0** — it costs. The offline gain does not survive
   contact with whole games, and the reason is worth chasing: an ask that is
   better for the endgame may be worse for reaching one.
3. **CI straddles 0** — no detectable effect at this resolution. This is the
   most likely outcome and it is **not** evidence of no effect. It will be
   reported as "the offline improvement is real and this test cannot see it in
   whole-game play", with the interval, and the arm will **not** be shipped on
   the strength of the offline number alone.

No outcome licenses running more pairs until the interval clears zero. If 2000
does not settle it, that is the answer for 2000 pairs, and any extension is a
new pre-registration saying so.

## Pilot

40 pairs, same seeds: diff +0.100 [−0.230, +0.430]. That was run to time the
harness (55 s for 40 pairs) and is far too small to mean anything; it is
disclosed because it exists and because its sign is positive, which is exactly
the kind of thing that should not be allowed to look like a prediction. The
2000-pair run reuses base seed 771000, so those 40 pairs are a subset of it
rather than an independent sample, and no combining is claimed.

## Amendments

### Amendment 1 — the run is executed in blocks, and that is not free

Recorded before any block is run. This environment caps a process at ten
minutes and `scripts4/duel.py` records a job only when it completes, so a
single 2000-pair job (about 47 minutes) loses everything when it is killed. The
run is therefore **8 blocks of 250 pairs**, base seeds 771000, 771250, ...,
771750 and agent seeds 7710..7717, pooled by fixed effect.

The deals are the same 2000 — `play_matchup` uses `base_seed + i` — but two
things do not match a single 2000-pair run. The seat rotation is `i % 6` with
`i` restarting each block, so each block covers rotations 0-5 evenly rather
than continuing the sequence; and the agent-seed stream restarts, which is why
the agent seed is varied per block instead of repeated. Neither biases the
comparison — both agents in a pair see the same deal and the same rotation, and
the pairing is what the test rests on — but the run is not bit-identical to the
one this document first described, and saying "2000 pairs from base seed
771000" without this note would have implied it was.

The total, the arm, the seeds and every decision rule above are otherwise
unchanged. No block result may be looked at before all eight are in.

## Replication (registered before it ran)

The primary run cleared zero: **+0.0835 sets, 95% CI [+0.0338, +0.1332]** over
2000 pairs, seven of eight blocks positive. That is outcome 1, and this section
was written before any replication block ran.

Why replicate at all when the interval already excludes zero: the point
estimate is three times the lower bound, and `info = +2.0` was picked off a
twelve-value grid, so the reported size carries a winner's curse even though
the sign does not. This project replicates before a default moves.

**Same arm, fresh deals.** 8 blocks of 250 pairs, base seeds 881000..881750,
agent seeds 8810..8817. No overlap with 771000-772999 and none with the
99000-99199 the weights were fitted on.

* **Replication CI entirely above 0** — ship it. The pooled estimate over all
  4000 pairs becomes the reported figure, and the primary's point estimate is
  not quoted on its own.
* **Replication CI straddles 0 but its point estimate is positive** — the sign
  replicates and the size does not. Report both runs, quote the 4000-pair
  pooled interval, and ship only if that pooled interval clears zero.
* **Replication point estimate negative** — the primary does not replicate.
  Do not ship, report both, and say the first result was probably the grid
  selection showing through.

No third run. Whatever these two say together is the answer.

## What was already seen, and when

`endgame-info-b0`'s block diff (+0.064) was visible in a log tail before the
other seven blocks finished, which the "no block read before all eight" line
above asked for and did not get. It changed nothing — no block was added,
dropped or reseeded on the strength of it, and the arm was fixed before any
pair ran — but the rule was broken rather than kept and it is recorded here
rather than left out.

## Amendment 2 — the refit under the award rule, and what it says about the pick

Written 2026-08-30, after task #49 recollected the one-ply targets under
`wrong_distribution_outcome="opponent"`. The 388 positions this document rests
on are **void-era**: the fit landed `956e132` on 2026-08-27 at 09:41 and the
rule flipped in `ddf196a` at 21:50 the same day.

`scripts4/ii_ask_targets.py` now journals under a rule fingerprint, so the two
eras sit side by side in one file and can be fitted separately. Three runs of
the same code over three row sets, each rung now carrying a **held-out paired
interval clustered by game** — which the original ladder did not have:

| rows | rule | games | grid's `info` | held-out gain over champion |
|---|---|---|---|---|
| 388 | void | 79 | **+2.00** | +0.0092 [−0.0282, +0.0467] |
| 457 | award, held to the same 79 games | 79 | **−1.00** | +0.0142 [−0.0118, +0.0403] |
| 764 | award, all | 156 | **+0.10** | −0.0011 [−0.0033, +0.0011] |

Three things follow, and only the first is good news.

**1. The scale family replicates.** `k = 1.0` in all three. De-weighting the
success probability does not help under either rule. That half of the original
diagnosis stands exactly as written.

**2. The `info` direction does not survive the rule change.** Held to the same
79 games — so the deal population is fixed and only the rule moves — the grid's
pick goes from +2.00 to **−1.00**. That is a sign reversal, not an attenuation.
Over all 156 award-rule games it lands at +0.10 with a held-out interval of
[−0.0033, +0.0011], tight enough to exclude any gain worth having. The
correction is not merely unproven under the award rule; at the weight the same
procedure now selects, it points the other way.

**3. The void-era pick was never significant, and this document hid that.**
`info = +2.0` was nominated on a held-out gain of **+0.0092 [−0.0282,
+0.0467]**. The interval covers zero and is four times the estimate. What this
document wrote instead was "it improved the selected ask's exact value by
+0.0093 in half-suit units" — a point estimate, no interval — and that number
is what sent 4,000 duplicate-deal pairs after this arm.

The duel is not retracted. It was pre-registered, it was run as written, and
**+0.0835 [+0.0338, +0.1332]** remains a true fact about the void rule. What
was wrong was the screen that chose where to spend the pairs: it was reading
noise, and the arm happened to win an honest play test anyway.

And the fix required no sophistication. Clustering by game is correct and the
analytic interval matches a 20,000-draw cluster bootstrap to three decimals,
but the naive interval over all 206 held-out positions as if independent is
[−0.0222, +0.0407] and straddles zero as well. The defect was not the wrong
interval. It was no interval.

### Decision

**The correction is withdrawn permanently, and no successor arm is nominated.**
`fish4/registry4.py` already dropped `endgame_d_info` from the deployed config
pending this refit; the refit does not bring it back. `V04_COMBINED` keeps its
void-era definition and its void-era numbers, which are correct for that rule.

The runner-up is not promoted either. `certain = −0.50` scores +0.0286 [−0.0137,
+0.0709] void, +0.0078 [−0.0299, +0.0454] matched, +0.0072 [−0.0219, +0.0363]
over all award games — three straddles, with the award estimates a quarter of
the void one. It is the arm this document once refused to test because it had
been chosen by the held-out set; it is now refused for a better reason.

### Standing rule this episode establishes

An offline screen nominates an arm for a duel **only if its held-out gain has an
interval excluding zero**, clustered by whatever unit shares a deal. A point
estimate is not a nomination. `scripts4/ii_ask_fit.py` prints the interval on
every rung so this cannot be skipped again by omission.

### One bookkeeping note

`askfeat` has gained two terms since the void-era fit (`locate`, then `reach`),
so those rows carry 11 columns and the new ones 13. Every model on the ladder
except the full search is unaffected: the champion carries weight 0 on both
added terms, so cutting them off leaves rung 0 and each one-parameter rung
bit-identical. The fit asserts that before cutting. Only the full search changes
width, from 11 free parameters to 13, and its held-out score was already
established to be a property of which restarts came up rather than of the model.
