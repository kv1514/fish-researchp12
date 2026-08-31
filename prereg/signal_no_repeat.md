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
