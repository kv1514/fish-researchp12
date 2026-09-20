# Pre-registration: P49, the channel the deficit is actually in

Written before any candidate game of this programme is played. One descriptive
scoring run (`scripts4/split_partner_model.py`, no duel games, ground truth used
as a label only) was in flight when this was written; its arms are named below
and its result is admitted as a **screen**, never as evidence of strength.

## What this programme is a response to

`prereg/kraken_v12_vs_sestina.md` ran three candidates against SESTINA v1.0 at
`BRIDGE_REV 3`, all four arms failed both halves of the bar, and the record
concluded:

> the residual half set is not reachable by any single knob this engine exposes
> at the power this project can buy; the next attempt would have to change what
> the engine computes.

**That claim is honestly stated and this document does not dispute it.** It is
narrower than "SESTINA cannot be beaten": it is a statement about single knobs,
at a stated power, and it explicitly invites the change of computation that this
programme proposes. P46 and P47 then went further and dueled a licensed arm that
P45's conclusion had not anticipated, so the search was not abandoned early.

What this document adds is where the three candidates were **aimed**, and it is
an aim the record can be checked against. `prereg/kraken_v12_vs_sestina.md` fixes
the target in one sentence — *"Candidates are therefore drawn from the ask
channel"* — on the strength of this table:

| | ours | theirs |
|---|---:|---:|
| declaration accuracy, repaired | 97.4% | 96.9% |
| ask hit rate, our arbiter repaired | 52.5% | 54.9% |

Both rows are rates. Neither row is a **volume**, and the deficit is a volume.

## The deficit, decomposed directly rather than by rates

`scripts4/margin_identity.py --base=persistent results/bridge_dealt_hand_price.json`,
600 paired games at `BRIDGE_REV 3`. The identity

    margin = 2*(d_us - w_us + w_them) - 9
           = 2*(d_us - 4.5)  +  (-2*w_us)  +  (2*w_them)
           =      RACE       +     OURS    +   THEIRS

holds per game with residual exactly zero, and the per-game integrality check
(our wrong-declaration count must solve to a whole number in `[0, d_us]`) passes
on all 600:

| | value |
|---|---:|
| margin | **−0.8733** [−1.110, −0.650] |
| RACE, `2*(4.1000 − 4.5)` | **−0.8000** |
| OURS, `−2*0.1383` | −0.2767 |
| THEIRS, `+2*0.1017` | +0.2033 |

**92% of the deficit is RACE.** We declare 4.100 half-suits a game; SESTINA
declares 4.900. The two accuracy channels together are **−0.073** — a rounding
error on a −0.873 margin. The headroom bounds from the same arm make the point
without any modelling:

| channel | most it could ever give |
|---|---:|
| OURS — declare perfectly, never wrong again | **+0.277** |
| RACE — declare all nine at our own accuracy | +9.266 |
| THEIRS — they never get one right | +9.597 |

**Perfect declaration accuracy loses to SESTINA by 0.60.** That single number
retires the accuracy channel as a route, and it was not available to the earlier
programme, because nothing had put the rev-3 counters through the identity.

This does not make the earlier programme wrong about what it measured. The
channels co-move — a half-suit we do not declare is one they do — so "the ask
channel" and "the race" are not disjoint, and a better ask is one way to declare
more. It does mean the three candidates were selected against a summary that
could not display the quantity carrying 92% of the loss, and that no arm in the
study was ever scored on declaration volume.

## The target, fixed now, at unchanged accuracy

`needed_declarations()` in `scripts4/split_partner_model.py` solves the identity
for the volume that reaches the standing +0.15 ship bar, holding both measured
per-declaration error rates (ours 0.03374, theirs 0.02075) fixed:

    w_us = e_us * x,  w_them = e_them * (9 - x)
    margin = 2*x*(1 - e_us - e_them) + 18*e_them - 9  =  +0.15
    =>  x = 4.6412,  and we are at 4.1000

**+0.5412 declarations a game.** Derived from a results file written before this
instrument existed, so it cannot be tuned to an arm. Note it is *larger* than the
naive +0.512 that holds the error counts fixed: every half-suit we take from them
is one they can no longer be wrong about, and we stop being paid for it.

An arm satisfies the target only at **unchanged or better accuracy**. Declaring
more by declaring worse is not progress: under `wrong_distribution_outcome =
"opponent"` a wrong declaration is a two-half-suit swing against a one-half-suit
gain, so a wrong one costs twice what a right one pays.

## Why the RACE channel was never searched, and what is actually in the way

Not an oversight — a defect with a location. On half-suits our team holds all six
of, `results/split_why.json` measures the split joint under-confident by −0.219:
it names the split right 0.7251 of the time and believes 0.5056. The bias is
**flat in draws** (−0.219 / −0.244 / −0.237 at 480 / 1920 / 5760) and **monotone
in gamma** (−0.337 / −0.219 / −0.143 / −0.025 at 0.0 / 0.35 / 0.7 / 1.4), so it
is the action model and not the sampler.

`ClaimEvaluator` gates a voluntary declaration on `prob_assignment >= 0.97`. An
under-confident joint is therefore a **volume** defect directly: the engine
declines to declare half-suits it would have named correctly. That is the RACE
channel, and it has a named cause.

The cause is on the **partner** side, and the exponent that controls it was never
swept into the region where the bias vanishes:

* `oppmodel.build` reads `g = gamma_team if gamma_team is not None else gamma`
  per slot, and `gamma_team` is `None` on the shipped path. `split_why.py` varied
  `bot.opponent_gamma`, so **one attribute moved both sides of the table** and the
  file cannot attribute its own finding.
* A frozen half-suit contains no opponent cards, so no opponent may legally ask
  there. The opponent model has almost nothing to say about how those six split
  among our three seats. The partner model has everything to say.
* The paper's invariance result says the same from the other end: `M[c, t1] /
  M[c, t2]` is invariant under the entire ask search tree, at every depth and
  every beam, because our asks only ever target opponents. **A split cannot be
  reasoned into existence by searching.** It can only be read off what partners
  did — which is exactly the partner action model.
* P46's Stage 0 grid swept `gamma_team` at **0.0, 0.35 and 0.7 only**
  (`results/p46_belief_grid.json`, `meta.cells`). The bias only reaches zero near
  1.4. P46 also licensed on held-card NLL / Brier / top-1, none of which is split
  correctness, and P47's G arm raised both exponents together.

So the region where the located defect disappears has not been scored, let alone
played, and the quantity that would have flagged it was not on P46's licensing
rule.

## The candidates, fixed now, in the order they run

Ordered by cost. Each stage's result is allowed to stop the programme.

### N0 — the partner exponent the grid stopped short of. *Not a new methodology.*

`scripts4/split_partner_model.py`, 300 self-play games, eight arms crossing
`gamma_opp` and `gamma_team` including `(0.35, 1.4)`, `(0.35, 2.0)` and the
one-sided controls `(0.7, 0.35)` and `(1.4, 0.35)`. Descriptive: every arm is
scored on the *same* belief at the *same* decisions and no arm acts.

This runs **first and alone** because if a single knob closes the gate, no new
methodology is needed, and it is honest to find that out before writing one. It
is also the direct test of the impossibility claim's own scope — "any single knob
this engine exposes" — against the one region that claim's search did not visit.

Reported: the joint at the gate (what `ClaimEvaluator` actually compares — the
earlier file's claim that its conditional column is the gate quantity is wrong
and is corrected in the new file's docstring), the conditional as calibration,
and the conversion to **distinct frozen half-suits per game that ever clear
0.97**, which is an upper bound on declarations and the only column comparable
with +0.5412.

**Screen rule, fixed now.** N0 promotes an arm to N1 only if its per-game upper
bound exceeds **+0.5412 with no loss of precision at the gate** — `d(wrong)`'s
95% cluster interval must not lie entirely above zero. A bound below the target
kills the arm outright: if every clearance became a declaration and it still
would not reach the bar, a duel cannot rescue it.

### N1 — duel the surviving exponent.

Standard dual-population duel of the best surviving `(gamma_opp, gamma_team)`
cell against SESTINA at `BRIDGE_REV 3` and in self-play, 300 deals × 2 parities,
fresh block **12,300,000**, paired within deal. Bar unchanged: **+0.15 with the
interval clear of zero in both populations.** An arm clearing one population only
is opponent-specific and does not ship, as in every programme before this one.

### N2 — two posteriors: recalibrate the declaration without touching the ask.

**The first candidate that changes what the engine computes.** `gamma_team` is a
single number reaching both the ask objective and the claim evaluator. The ask
channel is measurably fragile — three arms raised the ask hit rate by about a
point and two of them lost a third of a set (P44 D1, P45 F1) — so an exponent
that helps the declaration may be paid for in asks, and N1 cannot separate them.

N2 builds the claim evaluator's posterior at its own `gamma_team_claim` and
leaves the ask search reading the shipped posterior unchanged. Cost is one extra
posterior build at decisions where a claim is evaluated, bounded by the existing
0.35 screen. Registered whether or not N1 clears, because it is the only design
that can attribute N1's result; if N1 clears, N2 says what paid for it.

### N3 — characterise SESTINA's declaration trigger. *Measurement, ships nothing.*

Per-turn hazard: given a half-suit in a given public state, what is the
probability SESTINA declares it on this turn? Estimated from the existing rev-3
journals; no new games if the journals carry enough state, 150 games if not.

Needed by N4, and independently the first quantitative statement this project
would have about *why* they declare 4.9 to our 4.1 — the whole deficit, and
currently unexplained.

### N4 — price the wait: declaration as optimal stopping.

**The second change to what the engine computes.** `claim4.py`'s own docstring
records that 0.97 is a magic number and that its expected-value model was built
on "waiting is nearly free". Against an opponent who declares 4.9 a game, waiting
is not free: the half-suit may be declared out from under us. N4 replaces the
static bar with a comparison of declare-now value against wait value, where wait
value carries N3's hazard. Registered as a *shape*, not a threshold sweep — a
threshold sweep is the single-knob search the record already closed.

### N5 — invert the teammate's actual policy. *Registered, not scheduled.*

Our teammates run KRAKEN. The correct likelihood for a partner's ask is our own
ask objective, not a gamma-tempered depth heuristic. P46's E2 — teammate model
off — is a null in both populations (−0.0500 [−0.297, +0.197] and −0.0967
[−0.328, +0.135]), which is evidence that the current teammate *model* is worth
nothing. Given N0's structural argument that the partner channel is the only
channel carrying the split, "the model is worthless" and "the channel is
worthless" are different claims and E2 only establishes the first.

Expensive: scoring one partner ask requires running the ask objective over
candidate worlds. Registered here so that a later decision to run it is not a
new idea arriving after a disappointment, and **not scheduled** — it runs only if
N0 through N4 leave the RACE channel open with the split still the binding
constraint.

## The bar, and it does not move

Unchanged from `prereg/kraken_v12_vs_sestina.md`: **+0.15 sets/game with a 95%
interval clear of zero against SESTINA v1.0 at `BRIDGE_REV 3` AND in self-play
against the v1.1 champion**, both paired within deal, screen and confirm on
separate seed blocks and never pooled. A candidate clearing against SESTINA and
failing self-play is reported prominently as opponent-specific and left out.

## Multiplicity

N0 is descriptive and ships nothing, so it carries no alpha. Of the duelled
candidates, at most three reach a duel (N1, N2, N4); at 95% that is roughly an
11% chance of one false positive, and the two-stage screen/confirm rule is what
this programme relies on rather than a correction. Anything clearing a screen
re-runs on a fresh block at 600 deals × 2 parities and must clear again.

## Expected outcome, written down in advance

**That N0's bound clears +0.5412 and that no duelled arm clears the bar.** The
reasoning, in order:

1. N0's bound is an upper bound on a scoring run, computed on games the champion
   played. An arm that declares earlier faces a different game, and the effect of
   that is not signed by anything measured here.
2. The gate-clearing gain is concentrated where our team already owns all six.
   Those are half-suits we were going to win; declaring one earlier converts a
   *late* set into an *early* set, and only the ones SESTINA would have taken
   first are new sets. N3 is what would say how many that is, and it has not run.
3. Every previous exponent arm bought a sharper belief with a thinner effective
   sample (P46 records ESS ratio 0.68 at the licensed cell), and self-play pays
   that cost on all six seats.

Writing this here is the point. If an arm does clear, the first question is what
it is exploiting, and this paragraph is what makes that question askable.

## Withdrawal conditions

- Any duel arm with a non-zero fallback count is void, not adjusted.
- Any arm whose journal rows carry a `BRIDGE_REV` other than 3 is void.
- If N0's promoted arm's `d(wrong)` interval lies entirely above zero, it is
  dropped whatever its `d(right)` does: that is buying declarations with
  misdeclarations at the award rule's worst exchange.
- If a candidate's self-play arm moves negatively past the bar it is dropped
  immediately, whatever it does against SESTINA.
- If N3 cannot be estimated from the existing journals and a 150-game run does
  not resolve the hazard to better than ±50% of its own value, N4 is withdrawn
  rather than run on a guess.

## Analysis discipline

Paired per deal; intervals clustered over deals (duels) or over games (N0's
scoring run), never over decisions — rows inside one game share a hand and a
decision-level interval on this population is roughly an order of magnitude too
narrow. Every runner pins `wrong_distribution_outcome="opponent"` and records the
engine digest and `BRIDGE_REV`. No arm is inspected before its block completes.
