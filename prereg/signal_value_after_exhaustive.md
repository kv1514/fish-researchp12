# Does the signalling mechanism's +0.1220 survive the engine change?

**Registered 2026-08-31, before the run. A replication with a prior, not a new
hypothesis.**

## The question, and why it is narrow

`prereg/deadline_signalling.md` established the signalling mechanism's value
against the shipped champion and the interval is clear of zero
(`results/signal_gate_confirm.json`, 1,000 games, seed base 3,600,000):

| arm against A_shipped | effect | interval |
|---|---|---|
| B_incumbent, `signal_max_p` 0.15 | +0.1180 | [+0.0325, +0.2035] |
| C_measured, `signal_max_p` 0.50 | +0.1220 | [+0.0291, +0.2149] |

It did not ship because that registration's bar was a point estimate at or
above +0.15. **Nothing here re-opens the ship decision.**

What has happened since is that `claim_forced_exhaustive` shipped into the
champion, twenty minutes after that journal was committed — established, not
supposed, in `prereg/signal_no_repeat.md`'s ENGINE_DATED note and
`results/signal_deadline_noexhaustive.json`. That commit matters to this
mechanism specifically rather than incidentally: **signalling works by moving
declarations out of the gated path and into the forced path**, and the forced
path is exactly what that commit improved. Moving a declaration somewhere that
got better should be worth less.

`results/signal_no_repeat.json` puts the same contrast at **+0.0660 on 4,000
games of the current engine — about half — with no interval**, because that
run's payload did not keep per-game margins. The instrument now keeps them.

## Fixed before any data

* **Seed base 10,100,000.** Not 3,600,000 (the original), not 9,300,000 (the
  descriptive run), not 9,700,000 (withdrawn) and not 9,900,000 (which produced
  the +0.0660 that motivates this).
* **2,000 deals x 2 parities = 4,000 games per arm**, all arms on the same
  deals. `scripts4/signal_no_repeat_run.py` unchanged apart from the seed.
* **Clustered on the DEAL.**

## Primary outcome

`D = margin(B_incumbent) - margin(A_shipped)`, paired per game, 95% interval
clustered on the deal. Note this is a DIFFERENT primary from the one that
instrument last ran; `C_norepeat - B_incumbent` is reported as a registered
replication of that refutation and is not the primary here.

* **SURVIVES** if the interval is clear of zero AND contains +0.1220.
* **SHRUNK** if the interval is clear of zero and lies entirely below +0.1220.
  The mechanism is still real and the engine change re-priced it.
* **GONE** if the interval covers zero. With the precision below that would
  put a real ceiling on it, and would mean a published clear-of-zero effect
  did not survive an engine change — which is a result about this project's
  own record, not only about signalling.

**Precision, computed in advance rather than discovered.** The comparable
paired contrast `C_norepeat - B_incumbent` came in at half-width 0.0353 on
2,000 deals. `B - A` is a larger behavioural difference so expect wider, but
an interval near 0.04-0.06 separates +0.0660 from +0.1220 poorly and separates
either from zero well. **This run is powered to answer GONE, and is not
powered to distinguish SURVIVES from SHRUNK when both are positive.** That is
stated now so it cannot be presented afterwards as a clean discrimination.

## Withdrawal condition

The manipulation and distinctness guards in the instrument apply unchanged: if
the arms are not distinct, the run is refused. There is no replication gate
here, because this run IS the replication.

## What does not happen on any outcome

Nothing enters `V06_DEPLOYED`. `signal_mode` stays "off". A SURVIVES verdict
does not revive the ship question — that bar was set at +0.15 and not amended
after seeing +0.1220, and it is not amended now either.
