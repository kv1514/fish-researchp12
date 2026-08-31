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
