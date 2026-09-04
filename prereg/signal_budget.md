# Is the signalling exchange rate flat?

Registered 2026-08-31, **before `signal_budget` exists**. The arms, the seed
base, the sample size, the primary contrast, the verdicts, the withdrawal
conditions and the power limit are fixed here and chosen nowhere else.

## What is at issue

`scripts4/margin_identity.py` splits a margin into three channels that sum to
it exactly. Signalling, across five arms and 10,800 games spanning the
exhaustive-search engine change, is the same shape every time:

    effect +0.1435 = race -0.1695 + ours +0.0505 + theirs +0.2625

It buys a quarter of a set a game of the opponent's mistakes and hands back two
thirds of that in half-suits it never gets to declare, because each signal is a
deliberately doomed ask and a doomed ask loses the turn. About 8.3 signals a
game, 19.7 per stuck episode over 1.74 distinct cards.

The gross gain is +0.2625. If the first few signals buy most of the confusion
and the rest only burn turns, a **budget** keeps the opponent channel and
returns some of the race, and the arm clears the +0.15 roster bar it currently
misses at +0.1435. If the exchange rate is flat, a budget takes the channel
away in proportion and there is nothing here.

`prereg/signal_no_repeat.md` already fixed one end of the dose-response and
REFUTED it: suppressing repeated cards drops the mechanism to 1.5 fires an
episode, keeps the own-error saving, and deletes the opponent channel entirely
(+0.0030 against +0.2625). So "one signal is enough" is already false. This
registration asks about the interior.

## Arms

Four, each played once per deal on the **identical** deal.

| arm | parameters |
|---|---|
| `A_shipped` | `{}` — the champion, and the identity's base |
| `B_uncapped` | `signal_mode="stuck"`, `signal_max_p=0.50` — the incumbent |
| `C_budget6` | `B_uncapped` + `signal_budget=6` |
| `D_budget2` | `B_uncapped` + `signal_budget=2` |

`signal_budget` is a cap on signals **per game**, `0` meaning unlimited. Per
game rather than per stuck episode because there are about 0.42 stuck episodes
a game: nearly every game that has one has exactly one, so the two budgets are
close to the same intervention, and per game is the one a player could adopt
without tracking episode boundaries. A budget spent early in a game is not
available later; that is a property of the intervention, not a defect, and a
per-episode variant is the follow-up if this one lands.

`signal_budget=0` must be **bit-identical** to the current champion.

## Sample and seeds

2,000 deals x 2 parities = 4,000 games an arm, 16,000 games in total. Seed base
**11,700,000**, barred from 2,400,000 (the gate registration), 3,600,000 (the
signalling confirm), 9,300,000 (descriptive), 9,700,000 (withdrawn), 9,900,000,
10,100,000, 10,500,000, 10,900,000 and 11,300,000. Agent seed base 117,000.
Clustered on the deal, t at k-1 df, k = 2,000.

## Primary

    D = margin(C_budget6) - margin(B_uncapped)

Fixed here. Not "the best cap against the incumbent" — `D_budget2` is an
interior descriptive point and is not eligible to become the primary after the
fact.

| outcome | verdict |
|---|---|
| interval clear of zero, positive | **REAL.** A ship-candidate: it buys a further duel against the champion, it does not enter `V06_DEPLOYED`. |
| interval clear of zero, negative | **REFUTED.** The tail of the signal sequence is doing work, or the exchange rate is flat. |
| covers zero, half-width <= 0.05 | **NULL AT POWER.** The budget is not worth carrying and the arm retires. |
| covers zero, half-width > 0.05 | **UNDERPOWERED**, and it retires nothing. |

## Withdrawal conditions

1. **Replication.** `B_uncapped - A_shipped` must agree with the +0.1435
   +-0.0464 measured at seed 10,100,000, judged on a two-sample z using BOTH
   uncertainties. Comparing a fresh interval against a bare published point is
   the defect that withdrew the 9,700,000 run, and it is not repeated here.
2. **Manipulation.** Signals a game must satisfy
   `B_uncapped > C_budget6 > D_budget2`, with `C_budget6 <= 6.0` and
   `D_budget2 <= 2.0`. If the cap did not bind, nothing below it can be read.
3. **Identity.** `margin_identity.verify()` must return empty on the payload:
   the counted opponent declarations must agree with the identity and
   `d_us + d_them` must be 9.000 per arm. A run whose ledger does not close
   cannot be decomposed, which is the whole reason for running it.

If any fails, the run is withdrawn and the discrepancy is reported instead of
the primary.

## Power, stated in advance

The paired 2,000-deal contrasts this instrument has produced came in at half
widths of 0.032 to 0.036. So this run can answer REAL or REFUTED for an effect
around +-0.09 and can call NULL AT POWER at +-0.05. **It cannot resolve an
improvement of +0.03**, which is a plausible size for this intervention, and a
covers-zero result at this width will not be presented as evidence the budget
does nothing beyond what the verdict table above allows.

## Secondary, descriptive, no verdict attached

The channel decomposition of every arm, via `scripts4/margin_identity.py`. The
mechanism claim — that a budget trades race back for theirs — predicts that
`C_budget6` shows a smaller `race` penalty and a smaller `theirs` gain than
`B_uncapped`, and the question is only the ratio. This is stated so that a
decomposition that shows something else (say `ours` moving) is visibly a
surprise rather than a story fitted afterwards.

## What is not at issue

Nothing ships on this run. The roster bar is +0.15, set before any of these
arms was seen, and a ship-candidate buys a duel and nothing more.
