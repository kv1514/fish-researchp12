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

---

# CORRECTION, before any candidate game was played

Written the same day, after checking a premise of the document above against
`fish/engine.py` rather than against my own summary of it. **The central claim
of the section "Why the RACE channel was never searched" is wrong, and the N0
screen rule above cannot do what it says.** The decomposition is unaffected;
the inference drawn from it was not checked.

## What is wrong

`GameState._apply_claim` (fish/engine.py:327) awards a half-suit to the
declaring team only when the declared assignment matches the revealed holders
exactly, and to the **opponents** whenever any revealed holder is on the other
team (line 345). So a team that does not hold all six cannot take a half-suit by
declaring it, under any award rule. Correct declaration requires outright
ownership.

The counters say the same thing, from `results/bridge_dealt_hand_price.json` at
`BRIDGE_REV 3`:

| | per game |
|---|---:|
| half-suits collected outright and declared correctly | **8.7600** of 9 |
| declarations involving any error at all, both sides | 0.2400 |
| their ownership errors — the only "contested" case | 0.0233 |

**Contested half-suits essentially do not happen.** Every half-suit is collected
outright by one team and then declared by that team; the declaration is a
formality. We complete 3.9617 a game and SESTINA completes 4.7983.

So RACE is not a timing channel and cannot be moved by declaring earlier. A
half-suit our team already owns will be declared by us whether the gate opens on
turn 12 or turn 30; the gate changes *when*, not *whether*. **RACE is a
card-collection deficit, which is the ask channel** — exactly where
`prereg/kraken_v12_vs_sestina.md` aimed. That document's aim was right and this
one said otherwise on a premise I did not check.

## What survives

The identity work and the decomposition stand: they were measured, and the
per-game integrality check passes. What changes is the *ceiling on the
declaration channel*, which the same table already gave and which I did not
carry into the candidate design:

> OURS — declare perfectly, never wrong again — **+0.277**

That is the entire headroom of every declaration-side candidate, N0 through N4.
It is a third of the deficit. **No amount of declaration work beats SESTINA**,
and the correct reading of "declaring perfectly still loses by 0.60" is not that
declarations are the route but that they are *not*.

## What replaces it

The finding that survives is narrower than the one above and, unlike it, is
checkable against the record: the ask channel has always been scored by **ask
hit rate** — 52.5% against 54.9% in the earlier registration's own table — and
hit rate is not half-suit completion. The record already contains the evidence
that they come apart:

> "The hit rate rose again — 0.5289 against 0.5173 — and for the first time the
> arm did not lose." (P46 Stage 1)

Three arms raised the hit rate by about a point. P44's D1 and P45's F1 each lost
about a third of a set; P46's G was the first not to. **A point of hit rate has
never once bought a set**, and no arm in this study has ever been scored on
half-suits completed, which is the quantity the margin is made of.

## The replacement N0, and it is a measurement

`scripts4/completion_ledger.py`: instrument a `BRIDGE_REV 3` block and record
per game, for both engines, turns taken, asks made, asks that hit, half-suits
completed, and **asks per half-suit completed**. Ships nothing; it is the
diagnostic that should have preceded the whole SESTINA programme.

The two readings it separates, fixed now:

* **tempo** — they complete more because they take more turns, at a similar
  asks-per-completion. Then the lever is turn retention and the hit rate was
  the right proxy after all, measured on the wrong margin.
* **concentration** — they complete more per ask, at similar turn counts. Then
  the lever is *which* half-suit an ask is spent on, the hit rate is actively
  misleading (an ask that hits in a half-suit we will never complete is a
  wasted hit that also looks like a success), and the candidate is an ask
  objective scored on completion rather than on `p`.

Prediction, recorded before the run: **concentration**, on the reasoning that
three arms raised the hit rate without buying a set, which is hard to reconcile
with tempo being the binding channel.

N1 through N5 above are **not withdrawn but demoted**: they are bounded by
+0.277 and cannot reach the bar alone, so none of them is a route to beating
SESTINA and none may be reported as one. N0's scoring run
(`scripts4/split_partner_model.py`) is still worth finishing — it answers why
the split joint is under-confident, which is the OURS channel's mechanism — and
its per-game column is now to be read against **+0.277 of available headroom**,
not against the +0.5412 target, which no declaration-side arm can address.

---

# OUTCOME, recorded against the registration and its correction

## N0-split — the partner exponent. Registered prediction 1 holds, 2 falsified.

`results/split_partner_model_12000000.json`, 300 self-play games, **16,438**
frozen (decision, half-suit) pairs over 299 games, cluster bootstrap over
games, paired within the resampled game.

| arm | cond | names it right | bias | d(right) vs deployed |
|---|---:|---:|---:|---|
| deployed .35/.35 | 0.544 | 0.715 | −0.171 | — |
| team 0.7 | 0.617 | 0.721 | −0.104 | +0.006 [+0.002, +0.010] |
| team 1.0 | 0.664 | 0.720 | −0.057 | +0.006 [+0.001, +0.010] |
| **team 1.4** | 0.704 | 0.720 | **−0.016** | +0.005 [−0.000, +0.010] |
| team 2.0 | 0.742 | 0.720 | +0.022 | +0.005 [−0.001, +0.011] |
| opp 0.7 | 0.548 | 0.706 | −0.158 | −0.008 [−0.013, −0.004] |
| opp 1.4 | 0.564 | 0.680 | −0.116 | **−0.035 [−0.045, −0.025]** |
| both 1.4 | 0.706 | 0.707 | −0.001 | −0.007 [−0.014, +0.000] |

**Prediction 1 holds decisively.** `(0.35, 1.4)` takes the bias from −0.171 to
−0.016; `(1.4, 0.35)` only reaches −0.116. The correction belongs to the
**partner** model. `split_why.py`'s finding is now attributed, and its
inability to attribute it was the `gamma_team=None` fallback, exactly as this
document said before the run.

**Prediction 2 is falsified, and in the useful direction.** It said the
correction costs top-1 accuracy. It does not: the partner exponent *gains* a
little (+0.006 [+0.002, +0.010] at 0.7) and is free at 1.4. What costs
accuracy is raising the **opponent** exponent — −0.035 [−0.045, −0.025] at
1.4 — which is the knob P46 raised and P47 dueled to a null. The two sides of
the table want opposite things and the shipped fallback forces them to share
a number.

At the gate the deployed arm clears 0.97 on **0.000** of these rows: on a
frozen half-suit whose partner cards are not yet publicly located, the
shipped engine never declares from inference and waits for deduction. `team
1.4` clears on 0.082 at 99.8% precision, `team 2.0` on 0.191 at 99.0%.

**What this does and does not license.** It is a scoring run, it acted on
nothing, and by the correction above its channel is `OURS`, whose entire
headroom is **+0.2017**. The per-game conversion column reads `team 1.4` at
+0.846 net, but that number is an upper bound on *declarations*, and on a
half-suit our team already holds the declaration was coming anyway — so it
buys timing, not half-suits. The one mechanism by which timing could pay,
freeing us from the doomed asks a held half-suit generates, was dueled as C2
`avoid_doomed_asks` at −0.0933 [−0.196, +0.010].

**Verdict: N1 is licensed as a cheap arm and not as a route.** The belief
demonstrably improves in a region P46's grid never visited, the improvement
is free in accuracy, and that is worth 600 paired games. It is not worth
being described as a way to beat SESTINA, and this document will not describe
it that way.

## N0-assembly — the replacement diagnostic. Prediction holds: concentration.

`results/completion_ledger_12500000.json`, 1,600 games at `BRIDGE_REV 3`
through the persistent bridge, zero fallbacks, zero unfinished, paired within
the deal.

| per game | KRAKEN | SESTINA | ours − theirs |
|---|---:|---:|---|
| turn acquisitions | 23.184 | 23.091 | **+0.093 [+0.060, +0.127]** |
| asks | 46.374 | 48.184 | −1.810 [−2.206, −1.414] |
| asks that hit | 23.914 | 25.849 | −1.936 [−2.337, −1.535] |
| hit rate | 0.5157 | 0.5365 | −0.0218 [−0.0260, −0.0175] |
| assembled and named right | 4.078 | 4.730 | **−0.6525 [−0.786, −0.519]** |
| hits kept | 16.346 | 19.347 | −3.001 [−3.656, −2.345] |
| hits **wasted** | 7.568 | 6.503 | **+1.065 [+0.758, +1.372]** |
| wasted share of hits | 0.3164 | 0.2516 | +0.0715 [+0.0550, +0.0881] |
| plies sitting on a set | 68.922 | 36.282 | +32.640 [+29.8, +35.4] |

**Tempo is out.** Turn acquisitions are level to a tenth of a turn in 23, and
the tenth is ours. We take marginally more turns and assemble two thirds of a
half-suit a game fewer.

**Conversion decomposes further, and the second half is the finding.** Kept
hits per half-suit assembled: **4.009 for us, 4.090 for them.** The two
engines are indistinguishable in what they do with a card once it is on the
winning side. The entire gap is which side a hit lands on — 68.4% of our hits
are kept against 74.8% of theirs.

Arithmetic, labelled as arithmetic: holding our hit count and our
kept-hits-per-half-suit fixed and moving only our kept share to theirs gives
4.465 half-suits a game, which through the identity is **+0.205 instead of
−0.525**. The wasted-hit gap is larger than the deficit.

**The two warnings that keep this from being a plan.** A pure half-suit-value
objective was built and lost by **−7.195 [−7.356, −7.034]** over 2,000 pairs,
picking asks at success probability 0.457 against the heuristic's 0.551. The
additive concentration term was confirmed negative at 4,000 games. Trading
hit rate for concentration is a measured disaster, twice.

What makes the gap a target rather than a tradeoff is that **SESTINA does not
trade**: it has the higher hit rate *and* the lower wasted share. There is no
frontier here being moved along; there is a point off the frontier. And the
reason no arm has been aimed at it is visible in the same table — every
candidate the cross-engine programme drew was scored on hit rate, and hit
rate is the one axis on which the two engines nearly agree.

## What the programme is now

N1 runs as a cheap arm, bounded and labelled. N2 through N5 stand registered
and demoted. The open question this outcome creates, and which nothing in the
record answers, is **why 31.6% of our hits land in half-suits we never
finish** — which is a question about ask selection, not about the objective's
weights, and it is not answered by any arm scored on `p`. That is the next
registration, and it is not written here, because writing it in the same
document as the measurement that motivated it is how a measurement becomes
a hypothesis without anyone deciding to let it.

## N1 — dueled, and dropped on a registered withdrawal condition

`results/p49_n1.json`, 300 deals × 2 parities on block 12,300,000, 1,800
games, zero fallbacks, zero unfinished, paired within the deal and clustered
on it (both intervals agree to three decimals, so the parities were not
pretending to be independent).

| arm | vs SESTINA | self-play | verdict |
|---|---:|---:|---|
| N1 `gamma_team = 1.4` | −0.1433 [−0.452, +0.166] | **−0.2533 [−0.478, −0.028]** | no |

**It is not a null.** Against SESTINA the interval covers zero. In self-play
it does not: −0.2533 with the whole interval below zero. This document's
withdrawal conditions read *"if a candidate's self-play arm moves negatively
past the bar it is dropped immediately, whatever it does against SESTINA"*,
and it does. N1 is dropped, and it is dropped by a rule written before the
run rather than by a reading taken after it.

**The registered prediction was a null in both populations. It is half
right**, and the half it got wrong is the more useful half: the arm does not
merely fail to pay, it costs a quarter of a set in self-play. The belief it
buys is better — `results/split_partner_model_12000000.json` measures that
directly, on the same decisions, and the bias goes from −0.171 to −0.016 at
no cost in accuracy. A better belief that loses is the shape this project has
now seen four times, and it is the reason the dual-population bar exists.

**The fourth arm to raise the ask hit rate by about a point, and the third to
lose doing it.** Candidate 0.5409 against champion 0.5236, $+1.73$ points ---
the largest single-arm rise on record here, from a knob that touches the
*partner* model and has no business improving the asking. It does because
`gamma_team` reaches the ask objective through the same posterior: one
attribute moves the declaration and the search together.

| arm | hit-rate rise | result |
|---|---:|---|
| P44 D1 | ~1 point | lost about a third of a set |
| P45 F1 | ~1 point | lost about a third of a set |
| P46 G | +1.16 points | first not to lose |
| **P49 N1** | **+1.73 points** | **−0.2533 in self-play, interval clear of zero** |

Four arms, four hit-rate rises, and not one set bought. That is the same
finding the assembly ledger reached from the other end, arriving here by
accident: **hit rate is not the quantity**.

**What this licenses, and what it does not.** It does not license reading the
loss as "the partner model is wrong" — the belief measurably improved. It
licenses N2 exactly as registered, and for the reason registered: N1 moves the
declaration posterior and the ask posterior with one number and cannot say
which one paid. N2 gives the claim evaluator its own exponent and leaves the
ask search on the shipped posterior. That is now the only way to find out
whether the +0.2017 in the OURS channel is reachable at all, and it remains
bounded by +0.2017 whatever it returns.

**Nothing ships. `V06_DEPLOYED` is unchanged.**
