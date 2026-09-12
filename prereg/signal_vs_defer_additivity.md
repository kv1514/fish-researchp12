# Are signalling and the deferred gate one effect or two?

**Registered 2026-08-31, before the arms exist in any runner and before any
game is played.**

## Why this is the question the line has converged on

Two interventions, built independently and from opposite sides of the engine,
produce the same movement in the declaration ledger.

| | gate declarations/game | forced/game | effect against shipped |
|---|---|---|---|
| **signalling** (ask side), 2,000 deals, seed 10,100,000 | 0.293 -> 0.069 | 0.183 -> 0.323 | **+0.1435** [+0.0971, +0.1899] |
| **`B_defer`** (declaration side), 500 deals, seed 2,400,000 | 0.317 -> 0.093 | 0.178 -> 0.262 | **+0.0580** [-0.0177, +0.1337] |

The mechanism is now understood well enough to say why they should coincide.
`agent4.decide` reaches the signal branch BEFORE the gated-declaration branch,
so a seat that can signal signals *instead of* declaring at a bar that is about
a quarter wrong, and signalling again next turn defers it again. `B_defer`
raises that bar directly. **Both are ways of not declaring at the gate.**

If they are one effect, the declaration-side version is the cheap one — it
costs nothing, where signalling spends about eight turns a game on deliberately
doomed asks — and signalling is elaborate machinery around a one-line
threshold.

## Arms, on the same deals

    A_shipped   V06_DEPLOYED, unchanged
    B_signal    A + signal_mode="stuck", signal_max_p=0.50
    C_defer     A + stuck_team_certain=0.999, claim_stuck_threshold=0.5
    D_both      A + all four

`C_defer` is `B_defer` from `prereg/stuck_claim_gate.md`, unchanged, so this run
also replicates that arm on the current engine — it was last measured before
`claim_forced_exhaustive` shipped.

## Fixed before any data

* **Seed base 10,500,000.** Not 2,400,000 (the gate registration), 3,600,000
  (the signalling confirm), 9,300,000 (descriptive), 9,700,000 (withdrawn),
  9,900,000 or 10,100,000.
* **2,000 deals x 2 parities = 4,000 games per arm**, all four on the same
  deals, clustered on the DEAL.

## Primary outcome: additivity

Let `b = D(B_signal - A)`, `c = D(C_defer - A)`, `d = D(D_both - A)`, each a
paired mean with a 95% interval clustered on the deal. The registered statistic
is the **interaction**, computed per game and clustered the same way:

    I = (D_both - B_signal) - (C_defer - A_shipped)

* **ONE EFFECT** if `I`'s interval excludes zero and `I` is negative — adding
  the second intervention buys materially less than it buys on its own, which
  is what redundancy looks like.
* **TWO EFFECTS** if `I` covers zero AND `d` is clear of both `b` and `c`.
* **INCONCLUSIVE** otherwise, which includes the likely case that `I` covers
  zero while `d` is not resolvably above `b`.

## What this run can and cannot resolve, stated in advance

The comparable paired contrast at this size came in at half-width 0.0353
(`C_norepeat - B_incumbent`, 2,000 deals). An interaction is a difference of
differences and will be wider — expect roughly 0.05-0.07.

So: this run **can** separate `d` from zero, and can very likely separate
`I` from a full-additivity value of about +0.06. It **cannot** finely estimate
a partial overlap. If `I` lands near -0.05 with an interval of +-0.06 the
honest reading is INCONCLUSIVE and it will be reported that way, not as
"consistent with one effect".

## Withdrawal conditions

1. **`B_signal` must replicate.** Its effect against A must agree with
   +0.1435 [+0.0971, +0.1899] under a two-sample z. This is the same gate that
   caught a mis-specified criterion once already; it compares both
   uncertainties, not this run's interval against a point.
2. **The arms must be distinct**, by the existing guard: identical margins AND
   an identical path ledger on every game means the knob never reached the
   engine.

## What does not happen on any outcome

Nothing enters `V06_DEPLOYED`. Neither component ships on its own today —
signalling is +0.1435 against a bar of +0.15, and `C_defer`'s published
interval covers zero — and ONE EFFECT would not make the pair shippable
either. A positive `d` clearing +0.15 buys a further duel under its own
registration, not a place in the champion.


---

# OUTCOME, 2026-08-31: NOT RUN. The design is degenerate, and that is the answer.

A 400-game probe at the registered arms (`results/signal_vs_defer_probe200.json`,
200 deals x 2 parities, 11 minutes) was taken before committing to the
registered 2,000-deal run. It found:

**`B_signal` and `D_both` produce identical margins in all 400 games.**

    b  B_signal  +0.1150 [-0.0563, +0.2863]
    c  C_defer   +0.0850 [-0.0367, +0.2067]
    d  D_both    +0.1150 [-0.0563, +0.2863]

    I = (D_both - B_signal) - (C_defer - A_shipped)
      = -0.0850,  which is exactly  -c

The two arms are not bit-identical in play — the ledgers differ by one gated
declaration, 19 against 18, two exact and one voluntary — so the knob does
reach the engine and the distinctness guard correctly declines to fire. It just
never changes a result.

## Why, and it was predictable from the branch order

`agent4.decide` reaches the signal branch at `p_best <= signal_max_p` (0.50)
and the gated-declaration branch at `p_best <= 0.0`, a strict subset. With
signalling on, the gate is reachable only where there is no stuck half-suit or
no available signalling ask — about 0.048 declarations a game — and the defer
knob binds on a subset of that. **Signalling does not merely coincide with
deferral; it pre-empts it.**

## Why the registered primary is therefore uninformative

If `D - B` is identically zero then `I = (D - B) - (C - A) = -c`. The
registered interaction reduces to minus the C effect and says nothing about
additivity. Running it over 4,000 games would measure `-c` more precisely and
then report **ONE EFFECT** — a verdict that would be true, but for a
code-path reason the statistic does not establish and a reader would take as a
statistical finding.

**So the run is not executed.** Spending 130 minutes to produce a correct
verdict by an argument that does not support it is worse than not running.

## What is established, stated precisely

Adding the deferred gate on top of signalling buys **nothing**: 0 of 400 games
changed. That is the additivity question answered, in the strongest available
form — structurally rather than statistically.

What is **not** established is that signalling and deferral are the same
mechanism. The order is asymmetric and only one direction was tested.
`C_defer` runs with signalling off, so nothing here says whether adding
signalling on top of deferral would buy anything. `b` and `c` remain two
separate estimates, +0.1150 and +0.0850 on 200 deals, of two interventions that
drain the same path.

## The one number worth carrying forward

`C_defer`'s ledger is the best of the four on this probe: 0.075 gated
declarations a game at 6.7% wrong, and **0.09 wrong declarations a game**
against A's 0.1375 and B_signal's 0.1475 — and it spends **zero** signalling
turns where `B_signal` spends 7.76. On 400 games those are noisy, and
`prereg/stuck_claim_gate.md` already measured that arm at +0.0580 [-0.0177,
+0.1337] over 1,000 games on an older engine. The live question is that arm on
its own at power, not this four-arm design.
