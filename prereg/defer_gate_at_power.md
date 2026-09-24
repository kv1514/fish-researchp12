# Is the deferred gate real on the current engine, at power?

**Registered 2026-08-31, before the run.**

## The loose end this closes

`prereg/stuck_claim_gate.md` measured `B_defer` — raise the doomed-ask branch's
declaration bar instead of declaring at a coin flip — at **+0.0580
[-0.0177, +0.1337]** over 1,000 games at seed base 2,400,000. It did not ship,
correctly: the interval covers zero and the bar was +0.15.

Two things have happened since, and both make that measurement stale rather
than wrong.

1. **The engine moved.** `claim_forced_exhaustive` shipped after that run.
   Its A_shipped baseline is +2.302 and today's is around +2.43-2.45, and its
   forced-path error rate was 57.9% against today's 46.5%. A knob that trades
   gated declarations for forced ones is priced against a forced path that has
   since improved.
2. **It is now the cheap half of a understood mechanism.** The signalling line
   established that the value in this region is the POSTPONEMENT of a gated
   declaration, not information (`prereg/signal_no_repeat.md`), that signalling
   buys it for about eight doomed asks a game at +0.1435 [+0.0971, +0.1899]
   (`prereg/signal_value_after_exhaustive.md`), and that signalling PRE-EMPTS
   this knob entirely so the two cannot be stacked
   (`prereg/signal_vs_defer_additivity.md`). If the postponement is available
   here it is available for nothing.

**Power.** 500 deals gave a half-width of 0.0757. At 2,000 deals expect about
0.038, which separates +0.058 from zero. That is the whole reason to re-run it:
the original was underpowered for its own point estimate.

## Arms

    A_shipped   V06_DEPLOYED, unchanged
    C_defer     A + stuck_team_certain=0.999, claim_stuck_threshold=0.5

`C_defer` is `prereg/stuck_claim_gate.md`'s arm unchanged, so this is a
replication and not a new intervention. Opponents `dylan_v07`, as in every run
in this line.

## Fixed before any data

* **Seed base 10,900,000.** Barred from 2,400,000, 3,600,000, 9,300,000,
  9,700,000, 9,900,000, 10,100,000 and 10,500,000.
* **2,000 deals x 2 parities = 4,000 games per arm**, both arms on the same
  deals, clustered on the DEAL.

## Primary outcome

`D = margin(C_defer) - margin(A_shipped)`, paired, 95% interval clustered on
the deal.

* **REAL** if the interval is clear of zero and positive.
* **REFUTED** if clear of zero and negative.
* **NULL AT POWER** if it covers zero. At an expected half-width near 0.038
  that is an informative null: it would put the effect below about +0.04 and
  retire the arm, rather than leaving it open for a third look.

## Secondary, fixed now

The declaration path ledger per arm, and wrong declarations a game. The
mechanism claim is specifically that this knob moves declarations out of the
gated path; if the margin moves and the ledger does not, or the reverse, that
is reported and not filed.

## The ship bar is not the question and is not amended

`prereg/stuck_claim_gate.md` set +0.15 and did not amend it on seeing +0.0580.
`prereg/deadline_signalling.md` set +0.15 and did not amend it on seeing
+0.1220. **Nothing at or below +0.15 ships out of this run either**, whatever
the interval does. What is at stake is whether the effect exists on the current
engine, not whether it is worth the champion's complexity — a question already
answered no, twice, at a bar written down before either number was seen.


---

# OUTCOME, 2026-08-31: REAL

Seed base 10,900,000, 4,000 games x 2 arms, 68 minutes.
`results/signal_vs_defer.json`.

    PRIMARY  D = margin(C_defer) - margin(A_shipped)
             +0.0455 [+0.0134, +0.0776]   2,000 deal clusters

Clear of zero and positive: **REAL**. The half-width came in at 0.0321 against
the 0.038 projected, so the run delivered its registered precision.

It is a textbook powered replication of `prereg/stuck_claim_gate.md`: +0.0580
[-0.0177, +0.1337] on 500 deals there, +0.0455 [+0.0134, +0.0776] on 2,000
here. The point estimates agree and the original was simply underpowered for
its own number. **The effect exists on the current engine and it costs nothing
— zero signalling turns a game.**

## The registered secondary confirms the mechanism

| arm | gate decls | wrong | forced decls | wrong | wrong/game |
|---|---|---|---|---|---|
| A_shipped | 0.296 | 27.1% | 0.183 | 42.3% | 0.1585 |
| C_defer | **0.095** | **9.2%** | 0.259 | 34.9% | **0.1005** |

The knob does exactly what it is named for: declarations move out of the gated
path, and wrong declarations fall by 37%.

## And it contradicts the conclusion the signalling line reached

Set beside `results/signal_no_repeat.json` (seed 10,100,000):

| | gate drained | wrong declarations cut | margin gained |
|---|---|---|---|
| signalling | 0.224 | 0.0252 | **+0.1435** [+0.0971, +0.1899] |
| deferral | 0.201 | **0.0580** | +0.0455 [+0.0134, +0.0776] |

Deferral drains nearly the same gated volume and cuts **more than twice** as
many wrong declarations, and gains **less than a third** of the margin. The
intervals do not overlap.

**So the error ledger does not explain the margin**, and "the value is the
postponement" — written up from the no-repeat refutation — is at best a third
of the story. Postponement is what `C_defer` does, and it is worth +0.0455.
Whatever the other +0.098 of signalling is, it is not fewer wrong
declarations. `C_norepeat` sharpens the point: it posts the LOWEST error rate
of every arm measured, 0.1333 a game, and gains +0.0360.

I do not know what the remainder is, and this registration does not license a
guess. It is recorded as an open question rather than resolved by a story that
happens to fit.

## One caveat that is my own doing

The signalling and deferral arms were never played on the same deals.
`prereg/signal_vs_defer_additivity.md` would have paired them, and I dropped
`B_signal` from this run on the grounds that it would "re-measure what is
already on disk". That was right about the number and wrong about the
comparison: B against C paired is exactly the contrast that now matters. The
two intervals do not overlap, so the difference stands unpaired — but it would
be tighter, and free of any cross-run baseline question, had I kept the arm.

## It does not ship

+0.0455 against a bar of +0.15, set before +0.0580 and before +0.1220 and not
amended for any of them. `V06_DEPLOYED` is unchanged and
`claim_stuck_threshold` stays at its inert default.
