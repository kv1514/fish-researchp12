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
