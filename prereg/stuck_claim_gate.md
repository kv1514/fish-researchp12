# Pre-registration: the 0.5 declaration gate, and whether it should read p_team

Written before any confirm pair is played. The screening measurement described
in §3 has already been run; its result is stated here so that it cannot be
re-described after the fact.

## The defect, verified in the code and not taken on report

`fish4/agent4.py`, in the doomed-ask branch:

    if p[order[0]] <= 0.0:
        best = claims.best_candidate()
        if best is not None and best[0] >= 0.5:
            return best[2]

This is a second claim policy. It bypasses `ClaimConfig.threshold` -- the 0.97
bar that governs every voluntary declaration this engine makes -- and declares
at a coin flip. `best_candidate` (`fish4/claim4.py`) is

    return max(cands, key=lambda t: t[0])

an argmax over `p_exact` that never reads `t[1]`. That second element is
`p_team_holds_all` (`claim4.py:157,194`), and it is not an incidental field:
`forced_claim`, seventy lines below in the same module, prices its own version
of this decision with an `ev()` that reads exactly it (`claim4.py:301-305`).
So the module contains two declarations-of-last-resort, one that asks whether
our own team holds the set and one that does not.

The module docstring says waiting is nearly free while our team holds the set,
because an opponent who claims it is wrong and hands it to us under the award
rule. `p_team = 1` is precisely that case, and it is precisely the case this
gate does not look at.

The bar has been 0.5 since v0.3. `grep` finds it in no results file, no
pre-registration, and nowhere in `paper/fishbot_v06.tex`. The code comment
above it already concedes the point:

> "whether a higher bar plays better is an open empirical question,
> deliberately not settled here by fiat."

This registers that question.

## What is NOT being registered

Not "raise the bar". Raising it uniformly to 0.97 deletes every gate
declaration, and the screen below says three quarters of them are right. The
uniform version is the obvious move and it is the wrong one.

## The knob

Two `FishBot4` kwargs, `fish4/agent4.py`:

    claim_stuck_threshold = 0.5     # the incumbent bar
    stuck_team_certain    = 1.01    # ...applied unless p_team is at least this

`p_team` is a probability, so at 1.01 the second test can never pass and the
gate keeps one bar at 0.5. Defaults are bit-identical, guarded by
`tests4/test_stuck_gate.py`, which also proves the branch is REACHED before
concluding anything from a bit-identity check: the gate fires about 0.3 times
a game across six seats, so a knob wired to nothing would pass a naive
identity test on a handful of deals.

## 3. The screen, already run

120 self-play deals at `V06_DEPLOYED`, award rule, all six seats ours, and an
independent 20-deal replication run in this session for corroboration. Full
declaration ledger, 1080 sets, every set declared, so sets are conserved and
nothing escapes the ledger:

| path | n | per game | wrong | error rate |
|---|---|---|---|---|
| voluntary (bar 0.97) | 871 | 7.258 | 0 | 0.000 |
| exact / tablebase | 124 | 1.033 | 0 | 0.000 |
| **the 0.5 gate** | 38 | 0.317 | 10 | **0.263** |
| **forced** | 47 | 0.392 | 24 | **0.511** |

995 of 1080 declarations are error-free. All of the loss lives in 85
declarations, 7.9% of the total.

The split that matters: 19 of the 38 gate claims have `p_team == 1.0` exactly
and are right 12/19 (63%); the other 19 have `p_team` in [0.50, 0.89] and are
right 16/19 (84%). Seven of the ten gate errors sit in the `p_team == 1`
bucket and all seven are allocation-class -- right team, wrong split, which
under the award rule loses the set outright.

So the gate is least accurate exactly where waiting is cheapest. That is the
whole hypothesis.

Independent replication of the rate, this session, 20 self-play deals: 6 gate
firings (0.30/game), 3 with `p_team >= 0.999` and `p_exact < 0.97`, i.e. 3
that the armed configuration would defer. Consistent with the screen.

## Arms

- **A** = `V06_DEPLOYED`, unchanged.
- **B** = A + `stuck_team_certain=0.999`, `claim_stuck_threshold=0.5`.
  (Defer to the 0.97 voluntary bar when our team certainly holds the set;
  leave the uncertain half of the population exactly as it is.)
- **B2** = A + `stuck_team_certain=0.999`, `claim_stuck_threshold=0.70`.
  A middle rung, because the `p_team < 1` half is 84% correct and must not be
  deleted by accident.

## Design

Duplicate-deal paired: every deal played once in each seat parity, so neither
side opens more often. Fresh seed block, disjoint from the screen's. Award
rule pinned explicitly in the runner. Standard errors clustered over deals.
Primary opponent dylan_v07 through `BRIDGE_REV = 2`; the winning rung, if any,
is then re-run against the v0.3 champion.

**n.** 1000 pairs per rung against v0.7. `results/r5_signal_check.json` gives a
paired-difference SD near 1.15 sets/pair, so 1000 pairs is about +/-0.071 --
enough to resolve the predicted effect from zero, and honest about the fact
that this is a 0.16-events-per-game intervention.

## Primary outcome, fixed now

Paired difference of set margins, B minus A, against dylan_v07.

## Secondary outcomes, fixed now -- the mechanism check

Per-arm declaration path ledger: gate claims/game, gate error rate, voluntary
claims/game, forced claims/game, forced error rate, wrong declarations/game.
Reported for both arms whatever the primary says.

## Ship bar

- Point estimate >= **+0.15** with the interval clear of zero: ships. This is
  the same bar `jobs/PREREGISTRATION_at_ask.md` fixed, and which this project
  honoured by NOT shipping a demonstrated +0.102.
- Point estimate in [+0.05, +0.15) with the interval clear of zero: ships
  **only if** the ledger confirms the mechanism -- gate claims fall, voluntary
  claims rise, and forced claims do not rise by more than gate claims fall --
  **and** the v0.3 guard does not sit below zero.
- Otherwise: does not ship, and the screen's ledger result is reported as a
  real reduction in wrong declarations that bought no sets.

## Withdrawal conditions, fixed now

1. The ledger moves and the margin does not. Report as a null in play with its
   interval; leave the knob off. A defect that is real and costs nothing is
   still worth writing down, and this project has published that outcome
   before.
2. Forced claims rise by more than gate claims fall. The deferral is being
   paid for at the deadline rather than avoided; withdraw.
3. The v0.3 guard interval sits entirely below zero. A repair that helps only
   against v0.7 is an exploit wearing a bug-fix's clothes, and this project
   has withdrawn one of those already (the deception ladder, §critic).

## Expected outcome, written down in advance

The screen's paired delta is -0.0833 +/- 0.0595 wrong declarations per deal
across both teams, i.e. about -0.042 per treated team. At +2 sets of
differential per avoided error that is roughly **+0.08 sets/game**, which sits
in the conditional band and below the unconditional bar. The honest prediction
is therefore: a real, small, mechanism-confirmed effect that does not clear
0.15 on its own. If it comes in above +0.15 I should be suspicious of the
seating, not pleased.
