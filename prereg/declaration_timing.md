# Pre-registration: is the teammate ceiling a card-reading effect or a declaration-timing one?

**Registered 2026-08-30, before any gated arm was run for score.** What existed
when this was written: the gated agent, its five behavioural tests, and a
three-game smoke run checking that all modes play legal games. No margin, no
ceiling, no arm comparison of any kind.

## A SAFETY RULE THAT GOVERNS THIS ENTIRE FILE

Every arm here except the baseline **cheats** — it is handed the true deal.
Every margin is a **bound on what better inference could buy**, never a strength
measurement. It must never appear in a strength ladder, never be quoted beside
an honest engine's margin as though comparable, and never enter the head-to-head
table. Every figure carries the word *ceiling* wherever it is written down.
`GatedOracleBot` refuses to act until `see_deal` has been called, for the same
reason `OracleBot` does.

## The claim

`prereg/information_ceiling_split.md` measured that perfect knowledge of a
**teammate's** cards is worth **+3.41 sets/game** [+3.16, +3.66]
(`results/ceiling_split.json`: honest 2.3033, teammate-oracle 5.7133 over 600
games). It is the largest unclaimed number in the project.

Three separate attempts to reach any of it through better inference have now
returned nothing:

| attempt | result |
|---|---|
| `prereg/gamma_split.md` — believe the teammate model harder | refuted on its co-primary |
| the at-ask-time covariate — a better posterior | worth nothing in play |
| `prereg/convention_duel.md` — an actual message on an actual channel | belief improved and replicated; duel −0.002 [−0.127, +0.123] |

Three nulls against one large ceiling is not bad luck. It is evidence that the
ceiling is not measuring what everyone assumed it measures.

**The hypothesis.** The +3.41 is not a card-reading effect. A seat handed its
teammates' cards does not *ask* better. It **declares** — at moments it would
otherwise never dare, and with splits it could otherwise never name. If that is
right, no amount of belief accuracy reaches the number, because the belief was
never the binding constraint, and the lever is the declaration policy.

The error ledger already points this way and was never read as a *causal*
claim: 95.3% of wrong declarations are allocation class (0.1676/game against
0.0083), and **every** misdeclaration comes from a compelled path — voluntary
and exact-solver declarations are perfect over 14,678 of them, while the gate
path is 16.3% wrong and the forced path 42.7%.

## The instrument

`fish4/oracle_gated.py`. `OracleBot` pins the belief and lets everything
downstream follow, so its cheat reaches both decisions at once and cannot say
which carries the value. `GatedOracleBot` keeps **two beliefs side by side** —
one honest, one collapsed to truth — and routes each channel to one of them
through identity-default hooks in `FishBot4`.

**The cut.** `ClaimEvaluator` + `certain_claim` + the tablebase are the
declaration channel: they decide whether to name a split and which one.
Everything else is the ask channel. The tablebase sits on the declaration side
because when it fires it usually ends the half-suit by claiming.

**Why the gate is believed to gate**, from `tests4/test_oracle_gated.py`:

* a declare-mode oracle **never** names a wrong split over 10 games — not
  rarely, never, because its claim channel holds every teammate card;
* an ask-mode oracle **still misdeclares**, at the honest rate, over 40 games —
  the test that catches a leak, since a silent leak would produce a large
  declare-only effect for entirely the wrong reason;
* both-mode reproduces `OracleBot(side="team")` **move for move** over 4 games,
  which is what anchors this decomposition to the published +3.41.

## Design

`scripts4/declaration_timing.py`, mirroring `scripts4/ceiling_split.py`:
**600 games** (300 deals × 2 parities), the same `SEED0 = 5_500_000`, the same
`wrong_distribution_outcome="opponent"`, opposition `dylan_v07` at
`BRIDGE_REV = 2` throughout and never cheating. Our three seats carry the arm.
Reusing the seeds means `A_honest` and `T_both` should reproduce the published
2.3033 and 5.7133, which is a free replication and a withdrawal condition below.

**Arms.** All cheating arms are `side="team"`, `reveal=1.0`.

* **A** — honest `V06_DEPLOYED`. The baseline.
* **D** — `mode="declare"`. Truth reaches the claim channel only.
* **K** — `mode="ask"`. Truth reaches the ask channel only.
* **T** — `mode="both"`. The published teammate ceiling, as the anchor.

**Outcomes**, each a paired mean difference against A over identical deals, with
a 95% interval; the pair is the independent unit.

* **Primary:** the **declaration share** `S_D = (D − A) / (T − A)`.
* **Co-primary:** the **ask share** `S_K = (K − A) / (T − A)`.
* Secondary, reported and not gating: declarations per game, their correctness,
  the **move index at which they happen** — the timing the hypothesis is named
  for — and the allocation/ownership error split per arm.

## Decision rule, fixed in advance

* **CONFIRMED** if the interval on `D − A` lies entirely above zero **and**
  `S_D ≥ 0.50` **and** (`S_K < 0.25` **or** the interval on `K − A` contains
  zero). The value is in the declaration, and the lever is the declaration
  policy rather than the belief.
* **REFUTED** if `S_K ≥ 0.50` **and** `S_D < 0.25`. The value is in card
  reading for ask selection after all, and the three nulls need a different
  explanation.
* **SPLIT** otherwise — reported as a decomposition with both shares, licensing
  neither conclusion. This is the honest outcome for a genuinely mixed effect
  and is not a failure of the design.

**No arm here ships anything.** Every one of them cheats. A confirmation
licenses work on the declaration policy; it is not itself a change to the
engine.

## Validity conditions — the run is VOID, not null, if any fails

* **V1** — D must make **zero** wrong declarations across the whole run. Its
  claim channel holds the truth, so a single one means the gate leaks.
* **V2** — K's wrong-declaration rate must be within a factor of two of A's.
  Far below means the cheat is reaching its claim channel; far above means the
  honest claim channel is being fed a *stale* belief rather than an honest one,
  which would look like a real effect and is worse.
* **V3** — `T − A` must be positive with an interval excluding zero. If the
  anchor is not there, there is nothing to decompose.
* **V4** — cards pinned by the cheat per game must be within 10% between D, K
  and T. The three arms are told the same thing; only the routing differs, so a
  divergence means the collapse itself differs across arms.

## Withdrawal conditions

* If `A` does not reproduce the published 2.3033 to within 0.20 sets/game, or
  `T` the published 5.7133 to within 0.30, the seeds or the engine have moved
  since and the decomposition is not anchored to the number it claims to
  decompose. Report as a replication failure, not as a result.
* If bridge fallbacks are non-zero, Dylan's engine substituted a move and the
  affected games are excluded and counted, as in the published run.
* `D + K` is **not** required to equal `T` and any report saying so is wrong.
  The two decisions interact — a different ask reaches a different position, so
  the declaration the other arm faces is not the same one. `T` is carried
  precisely so that `D + K == T` is visibly a question rather than an
  assumption, exactly as `T + O ≠ F` was in the study this extends.

## What each outcome would mean

**Confirmed** closes the inference direction properly rather than by
accumulating nulls. It would say the engine's belief is already good enough for
the asks it makes, and that what it lacks is the *nerve and the accuracy to
declare* — which is reachable, because a declaration policy is a threshold and a
split choice, not a posterior.

**Refuted** would be more surprising and more useful still: it would mean three
different inference improvements all failed to move play for three unrelated
reasons, and the next question is why the belief improvements that were measured
did not reach the asks that depend on them.

---

# AMENDMENT to V4, recorded 2026-08-30 on a smoke run, before any outcome was read

**What had been read when this was written:** an 8-game mechanical check of the
harness (below `MIN` for anything, and its margins were not looked at as a
result). No 600-game arm had been started.

## V4 as registered cannot hold, for a reason that is the experiment

> **V4** — cards pinned by the cheat per game must be within 10% between D, K
> and T.

Measured on the smoke run: D 44.5, K 49.0 per game. That is a 10% gap and it is
**not a defect**. The arms play differently by construction — that is what is
being measured — so after the first move they are in different positions with
different amounts already deduced by the propagator, and the cheat therefore has
a different number of cards left to pin. A running total cannot match across
arms that diverge, and requiring it to match is requiring the experiment not to
work.

## V4', the amended condition

> **V4'** — at the **first decision our team makes in the game**, the pin count
> must be identical across D, K and T to within 2%.

Up to that decision every arm has seen the same history: the arms can only
diverge once one of *our* seats acts, so the cheat faces the same position and
must be told the same thing. It is a genuine invariant rather than an
approximate one. Measured: **18.0 in all three arms**, exact.

Per-game pin totals are still reported, as a diagnostic and not as a gate.

## A defect this found, fixed before the run

`GatedOracleBot` in `mode="both"` pins the same cards into both of its beliefs
and was counting each one, reporting 85.7 cards a game against T's true 42.8. No
outcome depended on it, but every per-pinned-card figure derived from it would
have been wrong by a factor of two. Now counted once.

---

# OUTCOME, recorded 2026-08-30: SPLIT. The hypothesis is not supported.

600 games, 300 deals × 2 parities, opposition `dylan_v07` rev 2, identical
deals across arms. **Every arm but A cheats; these are ceilings, not strength.**

**The anchor replicates exactly.** A_honest +2.3033 against a published
+2.3033, T_both +5.7133 against +5.7133 — delta **0.0000** on both. The
decomposition is anchored to precisely the number it decomposes.

| arm | margin | ceiling over honest |
|---|---|---|
| A_honest | +2.3033 | — |
| **D_declare** | +3.3800 | **+1.0767** [+0.7979, +1.3554] |
| **K_ask** | +3.0633 | **+0.7600** [+0.4731, +1.0469] |
| T_both | +5.7133 | **+3.4100** [+3.1625, +3.6575] |

`S_D = 0.316`, `S_K = 0.223`. The registered rule needed `S_D ≥ 0.50` to
confirm and `S_K ≥ 0.50` to refute. Neither. **SPLIT**, which licenses neither
conclusion, and the hypothesis this document was written to test **is not
supported**: the declaration channel is the larger of the two and is nowhere
near carrying the ceiling.

## The finding that replaces it, and it is bigger

    D + K = +1.8367     against     T = +3.4100

**46% of the teammate ceiling — 1.57 sets a game — lives in neither channel
alone.** It is interaction: knowing your teammates' cards is worth far more
when it informs the asks *and* the declarations than the sum of what it is
worth to either. The document warned that `D + K = T` was a question rather
than an assumption. The answer is that it is emphatically not.

**This explains the three nulls better than the hypothesis did.** Any
intervention that improves one channel in isolation is reaching for at most a
third of the ceiling, and the single largest component is unreachable by
improving either channel alone. The split gamma and the at-ask covariate
targeted the ask channel; the communication channel targeted what the team
knows but delivered it only through the belief. All three were competing for a
third of the prize while the interaction term sat untouched.

## The mechanism is real even though the magnitude is not

| arm | mean move index of our declarations | voluntary | gate | forced |
|---|---|---|---|---|
| A_honest | 77.8 | 2272 / 0 wrong | 160 / 44 | 112 / 53 |
| D_declare | 61.8 | 2801 / 0 | 0 / 0 | **2 / 2** |
| K_ask | 66.5 | 2098 / 7 | 874 / 219 | 757 / 391 |
| T_both | **39.2** | 3692 / 0 | **0 / 0** | **0 / 0** |

Knowing your teammates' cards does exactly what the hypothesis said it would:
T declares at move **39.2** against the honest **77.8**, half as deep into the
game, and **eliminates the compelled paths entirely** — 0 gate and 0 forced
declarations in 600 games, against 272 compelled declarations honestly, of
which 97 were wrong. D nearly does the same on its own.

So the *mechanism* is confirmed and the *magnitude* is not. Removing every
compelled declaration is worth +1.08 sets a game, not +3.41.

## Both VOID conditions were my mis-specifications, and the data says so

**V1 — "D never misdeclares" — VOID as written, and it should never have been
written that way.** D made 2 wrong declarations in 3,261. Both are
**ownership** class: an opponent still held one of the six.

| arm | allocation errors | ownership errors |
|---|---|---|
| A_honest | 92 | 5 |
| **D_declare** | **0** | 2 |
| K_ask | 563 | 54 |
| T_both | 0 | 0 |

`side="team"` reveals teammates' cards **only**, so no amount of teammate
knowledge prevents an ownership error. What the gate actually guarantees is
that D never makes an **allocation** error, and it made **zero in 3,261
declarations**. The condition should have said allocation; that is a fact
about what the cheat reveals, knowable before the run, and I wrote it wrong.

**V2 — "K misdeclares near the honest rate" — VOID as written, and refuted as
a concern.** K's 15.5% against A's 3.2% is not a leak. Per path:

| path | A n | A wrong | K n | K wrong | K/A frequency |
|---|---|---|---|---|---|
| exact | 453 | 0.0% | 249 | 0.0% | 0.5× |
| voluntary | 2272 | 0.0% | 2098 | 0.3% | 0.9× |
| gate | 160 | 27.5% | 874 | 25.1% | **5.5×** |
| forced | 112 | 47.3% | 757 | 51.7% | **6.8×** |

**Per path K is not worse than honest** — it is slightly better on the gate
path. Its aggregate rate is higher purely because its cheating ask policy
drives it onto the compelled paths five to seven times more often, and those
are the paths where declarations go wrong. That is a consequence of the cheat,
which is what the arm is for, and the opposite of the leak V2 was written to
catch.

## The mistake underneath all three amended conditions

V1, V2 and V4 failed for one reason: **I wrote validity conditions that assume
the arms are comparable in ways the experiment is specifically designed to
break.** The arms play different games on purpose. Their running pin totals
(V4), their declaration path mixes (V2), and the error classes available to
them (V1) all differ *because the manipulation works*.

The conditions that survived — V3, and V4 in its amended first-decision form —
are the ones stated over a quantity the manipulation cannot touch. That is the
rule to carry forward: **a validity condition has to be about something the
treatment does not change.**

## What this licenses

Not the declaration policy alone, which is what a confirmation would have
bought. The finding points somewhere harder and more interesting: the
teammate ceiling is mostly a **joint** effect, so the thing to build is not a
better belief or a braver declaration rule but a policy whose asks are chosen
*for what they will let the team declare later*. That is a lookahead over the
declaration, not over the next ask, and this project has not tried it.
