# P45 — KRAKEN v1.2, third attempt: the free-message gate

**Written before any duel game was played. Arms, seeds, bars, the futility
screen and the expected outcome are fixed here and are not amended afterwards.**

## Why there is a third attempt, and why it is this arm

P43 put three candidates at the ask deficit and moved none. P44 put two at the
declaration latency; one never reached a duel and the other lost in both
populations. The post-P44 measurement
(`scripts4/ownership_estimators.py`, `results/ownership_estimators.json`,
1,000 games) then closed the inference side of it:

* All three estimators of "our team holds all six" cross 0.99 on **4.17%** of
  genuinely-owned half-suits, so no declaration gate is rescued by reading a
  different number. The sharpest of them, the weighted joint, is the **worst**
  at the job — `-0.0512 [-0.0517, -0.0506]` against the independence product.
* Sweeping the gate's ownership knob is **flat from 0.77 down to 0.20** at
  0.1030 new declarations a game against P44's 0.250 futility bar. Ownership
  was never the binding constraint. The **exactness band** is: we are almost
  never 77–97% sure of an exact split.

That leaves the split, and the engine's one mechanism aimed at the split is the
pre-play convention. This registration duels the single arm of it that has been
specified and never run.

## What is already known about this channel, and it is mostly bad

Recorded so the arm below is not mistaken for a fresh idea:

| result | where | finding |
|---|---|---|
| the aimed convention, gate 0.05 | `prereg/convention_duel.md` | **loses** +1.750 [+0.645, +2.855] to the champion |
| ablation: encoder only | same | **+1.467** [+0.818, +2.116] — all of the loss is speaking |
| ablation: decoder only | same | +0.033 [-0.646, +0.712] at 40 pairs — uninformative |
| the free read, decoder only | `prereg/convention_freeread.md` | **null at 3,000 pairs: -0.002 [-0.127, +0.123]** |
| the locating book, belief only | `prereg/convention_locate.md` | clears its gate, teammate top-1 **+0.0408** |

Two of these matter for what follows.

**The loss was a specification error and it is fixed.** `encode_cost` compared
*probability of success* while the agent ranks asks by `scores` — lookahead,
tempo, concentration, leak. A gate of "0.05" was routinely paying a median
**0.3596 objective units** out of a range of about 1.5. The gate now reads the
same `scores` the pick was made from. The old gate numbers therefore do not
transfer, and this document does not reuse one.

**The decoder side is already settled and is a null.** The free read — listen
to the 35.3% of asks that name the agreed card by pure coincidence, send
nothing — was dueled at 3,000 pairs and came back `-0.002 [-0.127, +0.123]`.
It is not re-run here. Anything this arm wins has to come from the sender.

## The arm

One. Fixed here; nothing is added to this list without a new registration.

| arm | change from `V06_DEPLOYED` |
|---|---|
| **F1** free-message gate | `convention_q = 0.5`, `convention_book = "locate"`, `convention_max_cost = 1e-9` |

`convention_max_cost = 1e-9` in the **re-priced** units is the free-message
gate: swap to the agreed card only when it **ties** the card the objective
already chose. The message then costs literally nothing in the objective's own
currency, which is the quantity the old gate got wrong, and **no calibration is
needed** — that is the whole reason this is the arm and not a swept threshold.

`convention_book = "locate"` is the strongest book measured on the belief
(`prereg/convention_locate.md`) and the one aimed at the split, which is the
error class the post-P44 measurement leaves standing. `convention_q = 0.5` is
that document's better flat sender setting. Neither is swept here.

At the champion's defaults (`convention_max_cost = 0.0`, `convention_q = 0.0`)
the encoder is off and the decoder term is skipped entirely, so the champion is
bit-identical — asserted by `tests4/`, not assumed.

### Why the prior is against this arm, stated before the run

The free read says the channel is worth `-0.002 [-0.127, +0.123]` when 35.3% of
asks carry a coincidental match. The corrected carry table in
`prereg/convention_duel.md` says the free-message gate moves that to **40.1%**.
So F1 buys about **4.8 points of carry**, of which only the increment is
deliberate signal — roughly 12% of what is on the wire is genuine, the rest
still coincidence the decoder reads as message.

For F1 to clear +0.15, that 4.8-point increment would have to be worth more
than the entire 35.3% base was measured to be worth at 3,000 pairs. **I do not
expect it to clear.** It is registered and run because it is the one
specification `prereg/convention_duel.md` fixed and never executed, and because
a channel this project has spent five documents on deserves to be closed by a
measurement rather than by an inference from two adjacent ones.

## The futility screen

Fixed before the run. **The arm must raise the carry rate by at least 2
percentage points over the champion measured on the same deals.** Screen: 200
deals × 2 parities at seed base **10,150,000**, instrumented only, no duel.

### The bar is on carry, not on "decisions changed", and why that changed here

This section first fixed P44's D1 bar — 2% of ask decisions changed — and that
is **not measurable for this arm**, which is a fact about the arm rather than
about the instrument. A free-message gate swaps only when the agreed card
**ties** the one the objective picked, and on a tie the champion picks
*uniformly at random from the tied pool*. So the gate changes no score: it
replaces a random tie-break with a deterministic one. Against a particular
champion draw it "changes" a decision; against the champion's distribution it
narrows a tie. A replay comparison therefore counts RNG tie-breaking as gate
firing — a methods probe on 10 games reported **16.45%** by that route against
a true carry gain of 0.7 points.

Corrected **before any screen or duel game was played**; no measurement is
withdrawn here because none had been taken. The replacement is the quantity the
registration already required to be reported, and it is the one
`prereg/convention_duel.md` states the claim in: carry goes from **35.3%** with
no encoder to **40.1%** at this gate, so +4.8 points is what the arm is
advertised to buy and **+2 points is a little under half of it**. Below that the
encoder is not doing enough to be worth 3,600 pairings.

The champion's carry is measured on the same block rather than carried across
from that table, so the comparison is within-block.

## Design

* Duel screen: 300 deals × 2 parities, seed base **10,200,000**.
* Confirm: 600 × 2 at **10,300,000**. Screen and confirm are **never pooled**.
* Both populations: **against SESTINA v1.0 through `BRIDGE_REV 3`** and
  **against the v1.1 champion in self-play**, paired within deal, the champion
  replaying every deal on this block.

**The dual population is new for this channel.** Every convention duel to date
— including the 3,000-pair free read — was self-play only. A convention is an
agreement between our own seats, so self-play is the natural population; but
the engine is judged against SESTINA, and an arm that helps our seats
coordinate against a copy of themselves and not against a foreign engine is
exactly the opponent-specific shape this project has withdrawn a feature for
before. Both are required.

## The bar

**Ships only on +0.15 sets/game with the 95% interval clear of zero in BOTH
populations.** Unchanged, and deliberately: `prereg/convention_duel.md` already
says a re-priced gate does not get a softer bar for having been wrong once.

## The predicted outcome

Recorded before the run so the result can be a result rather than a relief.

**F1 clears the futility screen and returns a null in both populations**, with
intervals tighter than the 40-pair ablation's and centred near zero — I expect
something in the neighbourhood of the free read's `-0.002 [-0.127, +0.123]`,
because it is the same channel with 4.8 more points of carry.

**Most likely outcome: nothing ships and there is no v1.2.** That is what P43
and P44 recorded in advance and got. If F1 does clear, the thing to be
suspicious of is the self-play arm, where our own seats share a code book and
the opponent does not.

## Withdrawal conditions

An arm is void, not reported, if: the champion is not bit-identical at the
defaults; the arm's carry rate does not exceed the 35.3% no-encoder baseline
(the encoder did not reach the code path); any interval comes back zero-width;
or either side raises `IllegalAction`. All four have happened in this project
or its neighbours.

If the realised carry rate differs from the **40.1%** that
`prereg/convention_duel.md` measured for this gate by more than 10 points, the
duel population is not the one that table describes and the comparison is
reported as such rather than read straight.

---

# OUTCOME, recorded 2026-09-16

**Nothing ships. There is no v1.2, and the champion is unchanged.**

600 pairings, 1,800 games at seed base 10,200,000
(`results/p45_screen.json`), **zero fallbacks, zero unfinished**, so no
withdrawal condition fires and the numbers are read as they stand.

| arm | vs SESTINA | self-play | verdict |
|---|---:|---:|---|
| F1 free-message | **−0.3067** [−0.607, −0.006] | **−0.8567** [−1.069, −0.645] | no |

The pre-registered rule fires unambiguously: the bar wants +0.15 with the
interval clear of zero in both populations, and both intervals are clear of
zero on the **other side**. The confirm stage at 10,300,000 is not run, for the
reason P44 did not run it for D1: the confirm exists to harden a clearing arm,
not to re-establish a decisive negative at twice the compute.

## The prediction was right about the verdict and wrong about the size

This document predicted "a null in both populations … centred near zero … in
the neighbourhood of the free read's −0.002 [−0.127, +0.123]". That is wrong.
F1 is not a null; it is a **significant negative in both populations**, and in
self-play it is nearly seven times the size of the free read's point estimate.

Writing the prediction down is what makes that visible. The reasoning behind it
— F1 is the free read plus 4.8 points of carry, so it should land near the free
read — was sound and still produced the wrong number, which means the extra
carry is not a small perturbation of the same channel. **Sending changes the
game in a way that receiving does not**, and the free read's null does not
bound it.

## The dual population earned its place, in the direction nobody guarded for

The registration added the SESTINA population because every convention duel to
date had been self-play only, and said in advance: *"If F1 does clear, the thing
to be suspicious of is the self-play arm, where our own seats share a code book
and the opponent does not."*

The opposite happened. **Self-play is where F1 loses most** — −0.8567 against
−0.3067, a factor of 2.8 — so the population added as a check on optimism is
the one that was optimistic. Had this been run self-play only, as every earlier
convention duel was, the arm would have been rejected roughly three times
harder than the engine's actual opponent justifies. The guard fired; it just
fired the other way.

## A free message is not free, and the objective is why

F1 costs **nothing in the objective's own units by construction** — it swaps
only when the agreed card ties the card already chosen — and it loses 0.86
sets a game in self-play. Whatever it is paying, `scores` cannot see it.

Offered as a hypothesis and not a finding, because nothing here separates them:
the gate replaces a **random** tie-break with a **deterministic** one, and all
three of our seats resolve ties the same way. The champion's uniform draw from
the tied pool is not obviously a placeholder — it decorrelates three seats that
share an objective — and the free-message gate removes it at every tie. That is
a real change to the policy that the one-step score is structurally blind to,
which is the same shape of error as the mis-priced gate this arm was written to
avoid: a cost that is genuinely zero in the quantity being measured and
non-zero in the game.

## The ask hit rate goes up again, and loses again

| arm | candidate ask hit | champion ask hit | vs SESTINA |
|---|---:|---:|---:|
| P44 D1 `dead_ask_threshold = 0.5` | 0.5245 | 0.5184 | −0.3233 |
| **P45 F1 free-message** | **0.5287** | **0.5136** | **−0.3067** |

Two arms, two registrations, two different channels — one filters asks by
ownership, the other renames the card on a tie — and both **raise the ask hit
rate by one to one and a half points and lose about a third of a set a game
against SESTINA**. P44 concluded from one instance that "the ask hit rate is
not a quantity to maximise, and the 1.95-point gap is not necessarily a gap to
close." That was a single arm and could have been the arm. It has now
replicated on an independent channel, an independent seed block and an
independent registration, and it is the most durable finding either programme
has produced.

## What this closes

The convention channel. `prereg/convention_duel.md` found the gate priced in
the wrong currency and re-registered the free-message gate as the specification
worth running; this is that run, and it loses. Together with the free read's
null at 3,000 pairs, both halves of the channel are now measured in play:
**receiving is worth nothing and sending costs, at every gate ever tried.**
The 1.72 bits an ask remains a true fact about the rules and remains
unrealisable by this engine.

`V06_DEPLOYED` is byte-for-byte unchanged. KRAKEN v1.1 still loses to
SESTINA v1.0 by −0.5250.
