# Pre-registration: re-measure the baseline the recovery is quoted against

Written **before any pair of this run has been played**, and before the
`value_keep` settling run it will be combined with has reported.

## Why

The `value_keep` line reports a *recovery*: how much of the value objective's
deficit the turn credit gives back, against the pure objective's
**−7.355, 95% CI [−7.875, −6.835]**, measured over 200 pairs.

Recovery is a difference of two independent estimates on disjoint deals, so its
error is the quadrature sum. With the settling run at 2000 pairs:

| term | pairs | SE |
| :--- | ---: | ---: |
| settling run | 2000 | 0.081 |
| **baseline** | **200** | **0.265** |
| recovery | — | 0.277 |

**The baseline contributes 3.3× the settling run's error, and 91% of the
recovery's variance.** Running the challenger at ten times the baseline's size
bought precision on a number that is then differenced against a noisy one. The
sizing was wrong, and it was wrong in a way that was visible before the run
rather than only afterwards: nothing about the arithmetic above needed data.

This run fixes it.

## What

Same spec, more pairs. The arm is exactly the recorded `value pure` cell:

    x = fishbot4 {opponent_gamma: 0.35, objective: "value", value_turn: 0.15,
                  hsvalue_path: "checkpoints/hsvalue_v1.json"}
    y = fishbot4 {opponent_gamma: 0.35}

`value_keep` is absent, so it takes its default of 0.0, and
`test_zero_keep_reproduces_the_objective_exactly` asserts bit-identical scores
at that value — the arm is the same program it was, not merely a similar one.

- **2 blocks × 1000 pairs**, fresh seeds **33 000 000** and **33 200 000**,
  disjoint from the screen (31 000 000+) and the settle (32 000 000+).
- Expected SE ≈ 0.084, from the 200-pair run's implied per-pair sd of 3.75.
- Recovery SE then falls 0.277 → **0.117**, and its 95% half-width 0.544 →
  **0.229**.

### A determinism control, run first

Before the 2000 fresh pairs, the **original cell is replayed at its original
seeds** (base 2 000 000, agent 11 000, 200 pairs). It must return −7.355 to the
printed precision.

The recovery calculation assumes the baseline arm is the *same policy* it was
when first measured. Since then `keep_value` was added to
`score_asks_by_value` and a guard to `FishBot4.__init__`. Both are no-ops for
this spec and there is a unit test saying so — but that test compares scoring
functions on positions, not whole games. This compares whole games. If it does
not reproduce, the −7.355 is not a baseline for anything and this run stops.

It deliberately reuses the original seeds, which is what makes it a replication
rather than a new measurement, and it is kept out of `jobs/` so it does not
appear to `check_seeds.py` as a queued cell colliding with history.

## The replacement rule, fixed now

**The 2000-pair figure replaces −7.355 in every recovery calculation, whatever
it says.** Not the average of the two, not whichever is more convenient, not
the old one if the new one is awkward.

This is worth stating because the failure it prevents is easy and quiet: having
already reported "recovers about two thirds", a baseline that moves the recovery
somewhere less tidy is exactly the result one is tempted to treat as the
anomalous one. There is no selection here to justify that — the arm was never
chosen from a set, so there is no winner's curse and no reason to expect decay
in either direction.

The old 200-pair estimate stays in `results/v04_duels.jsonl` as history, and
the paper, if it ever quotes a baseline, quotes the 2000-pair one.

## The prediction

The 200-pair estimate is **unbiased** — it was a fixed arm, not a selected one.
So the re-measurement should land near it, and the honest prediction is simply

    -7.355 +/- 0.16   (i.e. within the old interval's own width)

A move of more than about 0.5 would mean the 200-pair run was unlucky, and a
move of more than 1.0 would mean something about the arm or the harness is not
what it is assumed to be — in which case the determinism control above should
already have caught it, and its silence would itself be informative.

## What this does not change

Nothing about the settling run, which is already in flight on its own seeds and
is not re-sized or re-analysed because of this. Nothing about the adoption
threshold, which is a statement about beating the champion and does not involve
the baseline at all. And nothing about the public table.

---

## AMENDMENT, written 2026-08-25 after the control ran

**The determinism control failed its stated criterion.** Replaying the original
cell at its original seeds returned **−7.345**, not −7.355. Everything else
about the two runs matches exactly — `pair_score` 0.03, `wilson_ci` identical to
sixteen digits, `nulls` 103 (X 59 / Y 44), 0 timeouts, 0 dropped — and the
differential moved by 0.010, which over 200 pairs is exactly two sets, with 11
more actions played.

The text above said: *"If it does not reproduce, the −7.355 is not a baseline
for anything and this run stops."*

### Why it failed, established rather than assumed

Not the `keep_value` edit. The original record carries `engine: null` — it
**predates the fingerprint mechanism entirely** — so the fingerprints could not
be compared and the question had to be answered from git. Between the commit
that recorded the cell and now, **nine of the eleven fingerprinted engine files
changed**, including `posterior.py`, `oppmodel.py` and `askfeat.py`, all of
which this arm executes.

So the arm is not the same program, and for a much larger reason than the one
the control was written to catch.

### What that changes, and what it does not

The control's stated inference is **confirmed**: −7.355 is not a baseline for
anything. The "stop" clause existed to prevent computing a recovery against a
number that does not describe the current policy — and that is exactly the
situation, so the clause did its job by identifying it.

Stopping the re-measurement, however, would leave the recovery quoted against
the stale number, which is the failure the clause was written to prevent rather
than a way of avoiding it. **The 2000-pair run therefore proceeds**, and its
result is now doing two jobs instead of one: it is more precise *and* it is
measured under the engine the challenger was measured under.

The old −7.355 is **retired**, not merely superseded. It stays in
`results/v04_duels.jsonl` as history and is not quoted again.

This is a post-hoc change to a pre-registered stopping rule, which is exactly
the kind of change that is usually self-serving. Three things are offered
against that reading, and the reader is entitled to weigh them: the amendment
is dated and appended with the original text untouched; the direction is
*against* convenience, since it discards a number already used in a reported
figure; and the substantive rule that governs the outcome — the replacement
rule — is unchanged and was fixed before any of this.

### A finding beyond this run

Checking the fingerprints against the pooled estimates, which nobody had done,
found that **three published pools average blocks played under different
engines on files their arms execute** — including `COMBINED`, the paper's
directly measured value for the configuration the website serves, whose two
blocks sit either side of a claim-logic bug fix. See
`scripts4/check_engine_provenance.py`. That is tracked separately from this
pre-registration and changes nothing about this run.
