# Do not re-prove what the table already knows

**Registered 2026-08-31, before the switch exists in `fish4/agent4.py` and
before any game is played with it.**

## What is being changed, and why it has no free parameter

`perpetual.signalling_ask` picks the highest-entropy card among the legal asks
in a half-suit our team provably owns, and skips a card already placed. It does
not remember what this seat has already signalled. Proving *this seat does not
hold X* removes only OUR bit from X's holder mask; with two teammates left the
mask still has two bits, so X can remain the top pick and be re-asked forever,
saying nothing new after the first time.

Measured over 1600 games in `results/signal_deadline.json`, per episode
(one deal x parity x half-suit):

| | fires | distinct cards | repeats saying nothing new |
|---|---|---|---|
| target declared in time (n=355) | 5.6 | 1.27 | 4.3 |
| target declared too late (n=244) | 42.5 | 1.74 | 40.8 |

Ninety-six percent of the asks in a bad episode re-prove a public fact. Those
turns come out of the seat's own 80-action stall window, and the stall route is
what forces the declaration in 185 of those 244 episodes.

**The intervention:** `signal_no_repeat: bool = False` on `FishBot4`. When
true, the signal branch will not choose a card this seat has already signalled
this game, and falls through to ordinary ask selection once the candidates are
exhausted. `False` is bit-identical to today, as every knob on this branch has
shipped.

There is no grid because there is no parameter. This is two arms, not a sweep.

## The reason to doubt it, stated before the run

`prereg/deadline_signalling.md` measured the signalling mechanism itself at
`+0.068 [-0.033, +0.169]` — an interval covering zero. The mechanism is switched
OFF in the deployed configuration for that reason. Making a mechanism cheaper
whose value is not established is not the same as making the engine better, and
a null here is the expected outcome rather than a surprise. It is registered
anyway because the waste is large, measured, and cheap to remove, and because
the alternative — leaving 40.8 wasted turns an episode in a shipped code path
on the grounds that the path is off — is how dead code accumulates.

## Arms

    A_shipped     the deployed champion, signalling off
    B_incumbent   signal_mode="stuck", signal_max_p=0.50 -- arm C of
                  prereg/deadline_signalling.md, unchanged
    C_norepeat    B_incumbent plus signal_no_repeat=True

Opponents are `dylan_v07`, as in `scripts4/signal_gate_confirm.py`, so the
arms sit in the same population the earlier registration measured.

## Fixed before any data

* **Seed base 9,700,000.** Not 3,600,000 (which produced the 52-vs-72 lead) and
  not 9,300,000 (which produced the waste figures above). A registration must
  not be scored on the deals that motivated it.
* **2,000 deals x 2 parities = 4,000 games per arm**, all three arms on the
  same deals so the comparison is paired.
* **Clustered on the DEAL**, since both parities share a shuffle.

## Primary outcome

`D = margin(C_norepeat) - margin(B_incumbent)`, paired per game, mean with a
95% interval clustered on the deal.

* **SHIP-CANDIDATE** if the interval excludes zero and D is positive. A
  ship-candidate buys a further duel under its own registration; it does not
  enter `V06_DEPLOYED` on this run.
* **REFUTED** if the interval excludes zero and D is negative.
* **INCONCLUSIVE** if it covers zero. A null here is REQUIRED to be decomposed
  against the secondary outcomes below and recorded, not filed. This project
  has twice reported "the ledger moved and the margin did not" without being
  able to say why.

## Replication gate, checked first

`B_incumbent`'s mean margin must cover `+2.598`, the value that arm produces in
`results/signal_gate_journal.jsonl` over 500 deals x 2 parities. If it does not,
the two runs are not measuring the same thing and **this registration says to
withdraw the run and report the discrepancy**, exactly as the earlier one did.

## Manipulation check, which can fail on its own

Fires per episode and repeats-saying-nothing-new must both FALL in
`C_norepeat` against `B_incumbent`. If they do not, the switch is not doing what
it is named for and no reading of the primary outcome is valid. The arms must
also not be bit-identical: the same `_assert_arms_are_distinct` guard that
caught a silently-discarded parameter over 800 deals applies here.

## Secondary outcomes, pre-registered so they cannot be chosen afterwards

1. The declaration path ledger per arm (`scripts4/path_ledger.py` paths and
   error rates), so a null can be decomposed.
2. Which forced route fires — `not asks` against `stalled and claimable` —
   since the stall route is the mechanism this change is meant to relieve.
3. Fires per episode and distinct cards per episode, as above.

## What this registration does NOT claim

That removing the waste makes signalling worth switching on. That is a separate
question about the mechanism's value, already measured at an interval covering
zero, and nothing here re-opens it.


---

# AMENDMENT, 2026-08-31, after the first run was withdrawn

## What happened

The 9,700,000 run completed (4,000 games x 3 arms, 96 minutes) and **the
replication gate failed**, so the run is WITHDRAWN and its primary outcome is
not read. `results/signal_no_repeat_withdrawn_9700000.json` keeps it.

    B_incumbent   +2.4980 [+2.4118, +2.5842]   target +2.5980   FAIL

## The gate was mis-specified, and the defect is one I had already fixed once

The gate as registered asked whether THIS run's interval covers the published
POINT. That treats a 500-deal estimate as exact. It is the same defect found
and corrected in `scripts4/signal_deadline.py`'s path anchors earlier the same
day — where the voluntary rate rested on two wrong declarations out of 3,692
and was being compared as though it were certain — and it was then written
straight into this registration.

Its signature is unmistakable once looked for:

| run | same arm, same opponents | half-width | verdict under the registered gate |
|---|---|---|---|
| `signal_deadline`, 800 deals | +2.4962 | 0.1349 | PASS |
| this run, 2,000 deals | +2.4980 | 0.0862 | **FAIL** |

The same number, opposite verdicts, decided by nothing but how much data was
behind the interval. A gate that a run fails BECAUSE it gathered more evidence
is not a gate.

Against the published estimate and ITS uncertainty — +2.598 +- 0.1674 on 500
deals — the difference is -0.100 with a combined standard error of 0.0960:
**z = -1.04**. The two runs agree.

## The correction, and why the withdrawn run is not simply re-read

The gate is now a two-sample z using both uncertainties, with the published
mean and its interval READ from `results/signal_gate_journal.jsonl` rather than
retyped as a literal.

**The withdrawn run is not re-read under the amended gate.** A criterion
corrected after seeing an outcome may not then be applied to the data that
revealed it, however clearly correct the correction is. The re-run uses seed
base **9,900,000**; everything else in this registration is unchanged.

This matters in the direction that is easy to get wrong. The withdrawn run's
primary was **negative** — reading it would have produced a REFUTATION of my
own proposal, not a confirmation. Declining to read it is not protecting the
hypothesis; it is refusing to let a criterion be chosen after the fact in
either direction. When the re-run lands, the withdrawn run's primary is not
evidence and does not count as prior support for its verdict.

## What the withdrawn run does establish, being descriptive rather than inferential

The manipulation check passed decisively, and the forced-route counts show the
switch doing exactly what it was built to do:

| arm | fires/episode | wasted/episode | forced by `stalled` | forced by `not asks` |
|---|---|---|---|---|
| A_shipped | -- | -- | 129 | 619 |
| B_incumbent | 20.47 | 18.98 | **585** | 668 |
| C_norepeat | 1.58 | **0.00** | **156** | 649 |

Signalling adds 456 stall-forced declarations over the shipped champion, and
the switch removes almost all of them, back to near baseline. Whether that
buys anything in sets is the question the re-run answers.


---

# OUTCOME, 2026-08-31: REFUTED, and the premise was backwards

The re-run at seed base 9,900,000 completed (4,000 games x 3 arms, 97 minutes).
`results/signal_no_repeat.json`. **Both gates passed and the primary refutes
the proposal.**

    REPLICATION   B_incumbent +2.5110 +-0.0849 against the published
                  +2.5980 +-0.1674 on 500 deals, two-sample z = -0.91   PASS
    MANIPULATION  fires/episode 20.14 -> 1.53, wasted/episode 18.67 -> 0.00  PASS
    PRIMARY       D = -0.0715 [-0.1068, -0.0362]   REFUTED

Removing 40.8 wasted turns an episode makes the engine **worse** by 0.07
sets a game.

## Why, and it is not what the registration expected

The registration expected a null on the grounds that the mechanism's own value
is unestablished. The decomposition says something sharper. Per game:

| arm | gate declarations | wrong | forced declarations | wrong | signal turns | margin |
|---|---|---|---|---|---|---|
| A_shipped | 0.299 | 0.0750 | 0.181 | 0.0842 | 0.00 | +2.4450 |
| B_incumbent | **0.069** | **0.0070** | 0.315 | 0.1276 | 8.18 | **+2.5110** |
| C_norepeat | 0.226 | 0.0529 | 0.193 | 0.0857 | 0.63 | +2.4395 |

Total wrong declarations a game: A 0.1590, B 0.1383, C 0.1388. **B and C are
level on errors**, so the margin B loses under the switch is not paid in
mistakes.

What the repeats do is DRAIN THE GATE PATH. `agent4.decide` reaches the signal
branch BEFORE the gate branch, so a seat that can signal signals instead of
taking a gate declaration — and a gate declaration is wrong about a quarter of
the time. Signalling again next turn defers it again. B takes 0.069 gate
declarations a game against A's 0.299, at a tenth the error rate.

Turn off the repetition and the deferral goes with it: C's gate path returns to
0.226 at 23.4% wrong, and **C lands on A**, +2.4395 against +2.4450, a
difference of -0.0055. With the repeats removed, the signalling mechanism does
essentially nothing.

**So the value of this mechanism is the postponement, not the message.** The
96% of asks that carry no information are not waste — they are the only thing
buying the delay. The framing that motivated this registration, that a
signalling ask exists to prove a card's location and repeating it says nothing
new, is correct about the INFORMATION and wrong about the VALUE.

## What this does not establish

`B - A = +0.0660` is a point estimate with **no interval**: this run's payload
did not carry per-game margins, and that contrast was not fixed by this
registration in any case. Whether the mechanism itself is positive on 4x the
data of `prereg/deadline_signalling.md` is now the obvious next registered
question, and the instrument has been changed to store the rows so it can be
answered with an interval rather than a difference of two means.

Nothing enters `V06_DEPLOYED`. `signal_no_repeat` stays False and
`signal_mode` stays "off": the shipped engine is untouched by any of this.


---

# ERRATUM, 2026-08-31: the premise of the "reason to doubt" was a superseded number

The section above headed *The reason to doubt it, stated before the run* says:

> `prereg/deadline_signalling.md` measured the signalling mechanism itself at
> `+0.068 [-0.033, +0.169]` — an interval covering zero.

**That is the SCREEN, not the confirm, and it is superseded.** `+0.068` is
`results/r5_signal_check.json`, the screening estimate that arm B was required
to reproduce. The registered confirm in `results/signal_gate_confirm.json` is:

| arm against A_shipped | effect | interval |
|---|---|---|
| B_incumbent, `signal_max_p` 0.15 | +0.1180 | [+0.0325, +0.2035] clear of zero |
| C_measured, `signal_max_p` 0.50 | **+0.1220** | **[+0.0291, +0.2149] clear of zero** |

The mechanism's value is **established and positive**. It does not ship only
because that registration's bar was a point estimate at or above +0.15, and
+0.1220 clears zero without reaching it. `paper/kraken.tex` states this
correctly; the error was mine, in this registration and repeated in commit
messages and RESEARCH_FRONTIER.md through the day.

The section is left standing rather than rewritten, because a registration's
stated expectation is part of its record and editing it after the fact is the
thing registrations exist to prevent. What is corrected is the claim about the
world, here.

**What it changes.** Nothing about the primary: `C_norepeat - B_incumbent =
-0.0715 [-0.1068, -0.0362]` is measured directly on this run's own arms and
stands. What it changes is the follow-up. "Whether the mechanism itself is
positive is the obvious next registered question" was wrong — that question is
answered. The real one is narrower and more interesting:

**does +0.1220 survive the engine change?** This run puts `B - A` at +0.0660,
about half, on an engine that now carries `claim_forced_exhaustive`. That
matters mechanically rather than incidentally: signalling works by pushing
declarations out of the gated path and into the forced path, and the forced
path is exactly what that commit improved — so the benefit of moving a
declaration there should shrink. The +0.0660 has no interval because this
payload did not keep per-game margins, which is now fixed.
