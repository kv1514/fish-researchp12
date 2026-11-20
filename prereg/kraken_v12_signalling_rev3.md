# P48 — KRAKEN v1.2, sixth attempt: the signalling protocol through the repaired bridge

Written 2026-09-19, after P47's outcome was on disk and before any P48 game.
Two arms, one fresh seed block, the dual bar, one registered secondary, one
prediction. Nothing here is amended after the run starts.

## Why there is a sixth attempt, and why it is this mechanism

Every margin the signalling line ever reported against an opponent was
measured through the bridge this project later found to be corrupting that
opponent's posterior (`BRIDGE_REV 2`, the current-hand `HAND` line): the
registered confirmation +0.1180 / **+0.1220** [+0.0291, +0.2149]
(`results/signal_gate_confirm.json`), the replication **+0.1435** [+0.0971,
+0.1899] (`results/signal_no_repeat.json`), the second replication
**+0.1605** ± 0.0471 (`results/signal_budget_11700000.json`), and the identity
run **+0.119** [+0.073, +0.165] (`results/where_the_margin_lives.json`) are all
`bridge_rev: 2` duels against `dylan_v07`. The paper's retraction withdrew
"contrasts run against `dylan_v07`" with the absolutes and kept only the
ablations against `ev_claim` and the self-play controls; the signalling
confirmations were never added to the withdrawn list, and the paper still
says of the protocol that "the mechanism's value is established and
positive" and that it is off "not because it does nothing". That sentence
rests on rev-2 numbers.

Worse than merely rev 2: the line's own ledger says where the gain lived.
`scripts4/margin_identity.py` splits any effect exactly into three counters,
and for the uncapped protocol against `dylan_v07` it read **race −0.1585,
ours +0.0465, theirs +0.2725** — most of the gross gain was *their extra
wrong declarations* (+0.1363 a game, their error rate 21.08% → 24.02%), which
is precisely the counter the bridge defect was inflating (their declaration
accuracy is 78.87% through the corrupted bridge and 96.68% through the
repaired one). Capping the dose to six signals a game deleted that channel
(+0.0073 [−0.0063, +0.0208]) and with it most of the gain; the self-play
control, which never had the bridge in the loop, read **+0.0200 [−0.0232,
+0.0632]** — a null. The line concluded "volume is the whole of what it
buys". The alternative reading, never testable at rev 2, is that volume
bought a corrupted opponent's confusion.

So the protocol is the last v1.1 mechanism with a positive reading on the
record, its reading is unrepaired, and it is aimed at the one deficit every
later instrument located (the declaration latency: we sit on a completed
half-suit 16.80 plies to SESTINA's 7.84). It has never been played through
`BRIDGE_REV 3`, and it has never been put to the dual bar.

## What is deliberately not registered, and why

| candidate | why not | record |
|---|---|---|
| `signal_no_repeat = True` | refuted twice at rev 2 (−0.0715, −0.1075) and, if the gain was the exploit, refuted for a reason that no longer applies; but it is a third arm on a question two arms answer, and it is added only if S1's theirs channel survives the repair | `prereg/signal_no_repeat.md`, `prereg/signal_value_after_exhaustive.md` |
| `signal_mode = "dead"` | fires only in a dead position (1.5% of decisions, P44); measured +0.002 [−0.086, +0.090] in the void era | `prereg/deadline_signalling.md` |
| "aimed" signalling (Direction 2) | the signalling ask already points at a stuck half-suit on 208 of 208 opportunities (`results/signal_aim.json`); there is nothing to aim | `RESEARCH_FRONTIER.md` |
| the deferred gate (`C_defer`) | pre-empted by signalling (0 of 400 games changed with both on) and the graded claim gate was P44's D2, stopped on futility | `prereg/signal_vs_defer_additivity.md`, P44 |
| any `signal_max_p` other than 0.50 | 0.15 and 0.50 moved three declarations in a thousand games apart; the gate was not the binding constraint | `prereg/deadline_signalling.md` |

## Standing discipline, unchanged

* **Ship bar**: +0.15 sets/game with the 95% interval clear of zero in **both**
  populations — against SESTINA v1.0 through `BRIDGE_REV 3`, and against the
  v1.1 champion in self-play — paired within deal. An arm clearing one
  population only is opponent-specific and does not ship.
* Every knob bit-identical to the champion at its default: `signal_mode =
  "off"` is the champion, and `signal_budget = 0` is bit-identical at any
  mode (`tests4/test_signal_budget.py`).
* Screen and confirm never pooled; a confirm at 600 deals × 2 parities on a
  block named in the outcome, only for an arm that clears both halves here.
* `wrong_distribution_outcome = "opponent"`; `BRIDGE_REV` recorded per row.
* Void conditions: any fallback, any unfinished game, any zero-width interval,
  any `IllegalAction`, any game on which the margin identity does not close
  (margin ≠ 2·(D_us − W_us + W_them) − 9 on a terminal game).

## Seeds, all new

* **Deal seed base 11,400,000**: 300 deals × 2 parities = 600 pairings per
  arm, both arms on the same deals, 3,600 games. Barred from every block on
  the record (the v1.2 programme's 10,000,000–11,100,000; the signal
  programme's 9,300,000–10,900,000, 11,300,000, 11,700,000, 12,100,000;
  everything below 9,300,000).
* **Agent seed base 114,000**: seat *p* in deal *d* seeds at 114,000 + 13*d* + *p*.

## The arms

| arm | change from `V06_DEPLOYED` | what it is |
|---|---|---|
| **S1** | `signal_mode = "stuck", signal_max_p = 0.5` | the registered, confirmed, replicated arm C of the signalling line, verbatim |
| **S2** | S1 + `signal_budget = 6` | the dose at which the rev-2 opponent channel vanished and the own-error channel was largest (+0.0795) |

`scripts4/p48_screen.py`: the P43–P47 dual-population design (`p46_screen`'s
`_play`, `_paired`, `_by_deal`, `_self_play`), with a scorer that also reads
each game's `ClaimEvent`s into the identity's four counters — declarations
made and lost, by team — and the arm's signals a game from the agents'
own counters. No futility screen: the mechanism's dose and effect at rev 2 are
on the record, and the question is whether they survive the repair.

## The registered secondary: where the effect lives

For each arm and population, paired within deal and reported with 1.96-SE
intervals over the 600 pairings: **race** = 2·ΔD_us, **ours** = −2·ΔW_us,
**theirs** = 2·ΔW_them, their sum equal to the margin effect on every
pairing (the void condition above); signals a game; both teams' declaration
error rates. The one contrast the reading rule keys on is **S1's theirs
channel against SESTINA at rev 3**, against its rev-2 value of +0.2725
[+0.2270, +0.3180] (2 × [+0.1135, +0.1590]).

## Reading rule for the paper, fixed now

* If S1's theirs channel against SESTINA has an interval whose upper bound is
  below +0.2270 (the rev-2 lower bound) and is consistent with zero, the
  paper's sentences "the mechanism's value is established and positive" and
  "not because it does nothing" are rewritten: the signalling gain was an
  exploit of the corrupted bridge, its value through the repaired bridge is
  [S1's interval] against SESTINA and [S1's self-play interval] in self-play,
  and the line's own "volume is the whole of what it buys" becomes "volume
  bought a corrupted opponent's wrong declarations". The signalling
  confirmations join the withdrawn list.
* If S1's theirs channel against SESTINA is clear of zero and positive, the
  sentences stand with the rev-3 numbers beside the rev-2 ones, and the
  ship question is the dual bar as always.
* Anything else is recorded as "not separated at this power" and the
  sentences are weakened to "measured positive through a bridge later found
  corrupt; not separated at 600 pairings through the repaired one".

## The predicted outcome, committed before the run

**S1**: vs SESTINA **−0.10 [−0.40, +0.20]**; self-play **+0.02 [−0.20, +0.24]**.
Channels against SESTINA: race −0.15, ours +0.04, **theirs +0.01 [−0.05,
+0.07]** — the opponent channel gone, the turn cost still paid. Signals a
game against SESTINA about **3** (down from 8.94), because "89.6% of stuck
turns clear the cheapness bar against `dylan_v07`" was a property of an
opponent whose corrupted posterior left us with nothing worth asking; in
self-play about 0.5. Their declaration error rate with S1 within a point of
the champion's 3.3%.

**S2**: vs SESTINA **+0.05 [−0.25, +0.35]**; self-play **0.00 [−0.22, +0.22]**.

**Nothing clears either half. Nothing ships; the champion is unchanged**, and
the first bullet of the reading rule fires: the signalling line's gain was
the bridge defect, measured from the other side. If S1's theirs channel
survives the repair instead, the prediction is wrong in the direction it
prefers not to be, and the mechanism is real against the real opponent.

## Withdrawal conditions

An arm is void, not reported, if: its knobs are not bit-identical to the
champion at their defaults; it is byte-identical to the champion on every
deal (the mechanism never fired); any interval is zero-width; any fallback or
unfinished game occurs; either side raises `IllegalAction`; the identity
fails to close on any terminal game.

---

# OUTCOME, recorded 2026-09-19

**Nothing clears. Nothing ships. The champion is unchanged. The first bullet
of the reading rule fires: the signalling line's gain was the bridge defect,
measured from the other side.**

`results/p48_screen.json`: 1,200 pairings, 3,600 games at seed base
11,400,000, agent base 114,000, 1,074 s at four workers; **zero fallbacks,
zero unfinished, the identity closes on every one of the 3,600 games**, no
zero-width interval, no `IllegalAction`; both arms fired (S1 signalled in
one game in five against SESTINA, 112 of 600). No withdrawal condition fires and the
numbers are read as they stand.

| arm | vs SESTINA | self-play | verdict |
|---|---:|---:|---|
| S1 `signal_mode = "stuck"`, `signal_max_p = 0.5` | **+0.0033 [−0.078, +0.085]** | **+0.0267 [−0.205, +0.258]** | no |
| S2 = S1 + `signal_budget = 6` | **−0.0233 [−0.109, +0.063]** | +0.0100 [−0.223, +0.243] | no |

## The registered secondary: where the effect lives, through the repaired bridge

Against SESTINA, paired within deal, in margin units (two sets a
declaration), with the rev-2 reading of the same arm beside it:

| channel | S1 at rev 3 | S1 at rev 2 (`results/signal_budget_11700000.json`) |
|---|---:|---:|
| race (half-suits we get to declare) | −0.0733 [−0.152, +0.005] | −0.1585 |
| ours (our wrong declarations, sign flipped) | **+0.0600 [+0.020, +0.100]** | +0.0465 |
| theirs (their wrong declarations) | **+0.0167 [−0.010, +0.044]** | **+0.2725 [+0.2270, +0.3180]** |
| effect | +0.0033 | +0.1605 |

Signals a game: **0.623** against SESTINA, 0.467 in self-play (rev 2: 8.94
against `dylan_v07`, 0.49 in self-play). Their declaration error rate with S1
on the table: **3.58%** against **3.43%** with the champion (rev 2: 24.02%
against 21.08%). Our own: **1.46%** against **2.17%**. Ask hit rate 0.5199
against 0.5242 — a signal is a deliberately failed ask.

In self-play the identity reads differently (one game, two sides:
race = D_us − D_them, and the two error counters collapse into one channel,
2·(W_them − W_us), because a symmetric game cannot separate "we declared
better" from "they declared worse"): race −0.0267 [−0.255, +0.202], errors
+0.0533 [−0.021, +0.128], summing to +0.0267.

**The theirs channel is gone.** Its rev-3 interval, [−0.010, +0.044], lies
entirely below the rev-2 lower bound of +0.2270 and covers zero. The channel
that was most of the gross gain at rev 2 — the opponent's extra wrong
declarations, +0.1363 a game, their error rate lifted from 21.08% to 24.02% —
does not exist against an opponent whose posterior we are not corrupting.
"Volume is the whole of what it buys" was right about rev 2 and wrong about
the mechanism: the volume was the defect's. Through the repaired bridge the
protocol fires 0.62 times a game, not 8.94, because "89.6% of stuck turns
clear the cheapness bar against `dylan_v07`" was a property of an opponent
whose corrupted posterior left us with nothing worth asking; against the
real one we are stuck less and, when stuck, usually have an ask worth
making.

**The ours channel survives, and it is the whole of what the mechanism was
built to do.** A signal proves to a partner which card this seat does not
hold, and partners then place splits they would otherwise get wrong: our
wrong declarations fall from 2.17% to 1.46% of the ones we make, +0.0600
[+0.020, +0.100] in margin, clear of zero, replicating the rev-2 +0.0465
through the repaired bridge. And each signal is a conceded turn: race
−0.0733 [−0.152, +0.005]. The two cancel to +0.0033. The protocol does
exactly what it says and pays exactly what it buys.

## The prediction got the verdict right, the direction of every channel right, and the dose wrong by five

Predicted: S1 −0.10 [−0.40, +0.20] against SESTINA and +0.02 [−0.20, +0.24]
in self-play; theirs +0.01 [−0.05, +0.07]; race −0.15; ours +0.04; about 3
signals a game against SESTINA; S2 +0.05 / 0.00. Found: +0.0033 and +0.0267;
theirs +0.0167; race −0.0733; ours +0.0600; 0.62 signals a game; S2 −0.0233
/ +0.0100. The verdict, the sign of every channel and the vanishing of the
opponent channel were predicted. Two things were not. The vs-SESTINA
interval is three and a half times narrower than predicted — ±0.08, where
every earlier arm in this programme read ±0.29 — because a mechanism that
touches 0.6 decisions a game leaves most pairings identical, and **the
result is a null whose interval excludes the ship bar itself** (upper bound
+0.085 against +0.15), the first arm in six registrations for which that is
true. And the dose collapsed fourteen-fold, not three-fold: the prediction
kept a third of the rev-2 volume for the mechanism, and the mechanism owns
a fourteenth of it.

**S2 is S1.** At 0.57 signals a game the six-signal budget almost never
binds; the two arms differ on a handful of pairings and their contrasts are
the same reading twice. The prediction that a budget would keep the own-error
channel and return the race was a rev-2 prediction about a rev-2 dose.

## What this closes, and what it withdraws

The signalling line. Its registered confirmation (+0.1180, +0.1220), its
replications (+0.1435, +0.1605), its identity run (+0.119) and its dose
studies were all `bridge_rev: 2` duels against `dylan_v07`, and the paper's
sentences that the mechanism's "value is established and positive" and that
it is off "not because it does nothing" are withdrawn by the rule fixed
above: through the repaired bridge the protocol is +0.0033 [−0.078, +0.085]
against SESTINA and +0.0267 [−0.205, +0.258] in self-play, and its rev-2 gain
was the bridge defect, measured from the other side. The confirmations join
the paper's withdrawn list beside R2, R6, the dialect gaps and the
contestation port. What survives is smaller and exact: the mechanism cuts our
own wrong declarations by a third of their rate and pays for it in turns.

Not registered next, and why: `signal_max_p` above 0.5 (the gate was never
the binding constraint: 0.15 and 0.50 moved three declarations in a thousand
games apart, and at 0.62 fires a game there is no volume to widen into); a
per-opponent dose (the dose is set by how often we get stuck, which the real
opponent makes rare); the deferred gate (`C_defer`, +0.0455 [+0.0134,
+0.0776]) — also a `bridge_rev: 2` duel against `dylan_v07`, recorded here
as unre-read rather than as withdrawn, because its channel split at rev 2
was ours-dominated (its value was our own errors halved) and nothing in P48
measures it.

Seventeen duels of sixteen arms across six registrations. `V06_DEPLOYED` is
byte-for-byte unchanged. KRAKEN v1.1 still loses to SESTINA v1.0 by −0.5250.

*Recorded with the outcome:* the harness's self-play channel split, as first
written, applied the two-game coefficients to one-game counters and
double-counted every self-play channel; the residual exposed it (9, not 0)
and the vs-SESTINA split, which the reading rule keys on, was exact
throughout. The split was corrected and the results file's summary was
rebuilt from its own per-pairing rows (`--rescore`), with no game replayed;
the file carries `rescored: true` and the rows are unchanged.
