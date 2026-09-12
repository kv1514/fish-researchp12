# Where the margin lives: a prediction made before the run lands

Written 2026-08-31, while `scripts4/signal_vs_defer.py --prereg=where_the_margin_lives`
is running at seed 11,300,000. It has not printed anything yet. This document
states what it will print, from arithmetic on runs already on disk, so that the
run can refute it.

## The identity

Under `wrong_distribution_outcome="opponent"` — the award rule on every figure
in this line — the `NULL_TEAM` branch of `engine._apply_claim` is unreachable.
Every one of the nine half-suits is awarded to exactly one team, by exactly one
`ClaimEvent`, and by nothing else. Writing `D` for declarations a side makes
and `W` for the ones it loses:

    ours   = (D_us   - W_us)   + W_them
    theirs = (D_them - W_them) + W_us
    D_us + D_them = 9

    margin = 2 * (D_us - W_us + W_them) - 9

So the margin has exactly three channels, each worth two sets a declaration:

  * **RACE** — how many of the nine we get to declare at all.
  * **OURS** — how many of the ones we declare we get wrong.
  * **THEIRS** — how many of the ones they declare they get wrong.

Every instrument in this line reported OURS and neither of the others. That is
why the line has an open question: the margin was never going to be found in a
third of itself.

## What the identity already says, on data collected before it was written

`scripts4/margin_identity.py` solves for `W_them` as a residual and splits each
arm's effect into the three channels. On the two 4,000-game runs on disk:

| run | arm | effect | race | ours | theirs |
|---|---|---|---|---|---|
| `signal_no_repeat.json` | `B_incumbent` (signalling) | +0.1435 | −0.1695 | +0.0505 | **+0.2625** |
| `signal_no_repeat.json` | `C_norepeat` | +0.0360 | −0.0220 | +0.0550 | +0.0030 |
| `signal_vs_defer.json` | `C_defer` | +0.0455 | −0.0700 | **+0.1160** | −0.0005 |

The residual is zero to fifteen places in all four, which it must be: these are
integer counts over the same games, and the identity is arithmetic.

Read across the rows:

  * **Signalling is an opponent-error intervention.** Its own-error saving
    (+0.0505) is a fifth of its effect. It buys +0.2625 of the opponent's
    mistakes and pays −0.1695 of them back in sets it never gets to declare.
  * **Deferral is an own-error intervention.** +0.1160 of our own mistakes,
    nothing at all from theirs, and the race eats sixty per cent of it.
  * **They were never the same effect**, and the declaration ledger could not
    say so because it was showing one channel of three.
  * **Suppressing the repeats removes the opponent channel entirely** (+0.0030
    against +0.2625) while keeping the own-error saving. That is why
    `C_norepeat` is worse than the incumbent it was meant to tidy up: the
    repeats are not waste, they are the mechanism.

## The prediction

The running job plays `A_shipped`, `B_signal` and `C_defer` on the same 2,000
deals at seed 11,300,000, and is the first instrument in this line to **count**
the opponent's declarations rather than discard them. It will report
`both_sides`. I predict, before seeing it:

1. **`margin_identity.verify()` returns empty on the payload.** The counted
   `their_wrong` agrees with the solved one to within 1e-9 for all three arms,
   and `d_us + d_them = 9.000` exactly per arm. This is a check on the
   instrument, not on the theory; if it fails, `_play` is miscounting.
2. **`their_wrong_per_game(B_signal) − their_wrong_per_game(A_shipped)` is
   about +0.13 a game, and clear of zero.**
3. **`their_wrong_per_game(C_defer) − their_wrong_per_game(A_shipped)` is
   about zero, inside ±0.02.**
4. The paired `B_signal − A_shipped` margin lands near +0.14 and `C_defer −
   A_shipped` near +0.05, which is the contrast the earlier runs had to make
   across two seeds.

## What would refute it

Prediction 2 is the one with content. If the opponent's error rate does not
move under signalling, then the residual `W_them` computed above is absorbing
an error somewhere else — most likely a declaration path dropped from the
ledger, which would mean `D_us` is undercounted and the identity closes only
because `W_them` is defined to make it close. In that case the finding is
withdrawn and the defect is the result.

Prediction 3 is nearly as sharp: deferral changes only what our own seats do at
the gate, and it has no channel to the opponent's read. If theirs moves under
`C_defer` too, then something about playing the arm — not the intervention —
is moving the opponents, and both readings above are unsafe.

## What this does not decide

Nothing ships on it. The bar for the roster is +0.15 set before either arm was
seen; signalling is +0.1435 and deferral +0.0455 and neither clears it. This
document is about **why** those numbers are what they are.
