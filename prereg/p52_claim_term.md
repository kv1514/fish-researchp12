# Pre-registration: P52, the `claim` term — a zero that was never a measurement

Written before any P52 game.

## Why this is not a knob that was already rejected

`AskWeights` has thirteen terms and the champion ships **three** of them live:
`suit` 0.06, `turn` 0.6, `scarce` 0.2. The other ten sit at exactly 0.0. For most
of them that zero is a result — `deplete` is marked "v0.3 null", `locate` was
dueled to **+0.047 [−0.075, +0.168]** and diagnosed, `concent` was confirmed
negative at 4,000 games.

**`claim` is not one of those.** Its zero comes from a ridge fit whose stored
column described a formula the engine no longer computes. `fish4/askfeat.py`
says so by name:

> "The rest" is the whole point and was the bug. This used
> `ctx.p_team_all[hs]`, the product over all SIX cards — including the one being
> asked for, which by construction we do not hold. For a provably-certain steal
> that card's factor is exactly 0, so the product is 0 and the feature is 0: it
> scored zero on precisely the asks it was written to reward, and rose as the
> steal became less certain.

The paper records the consequence and the decision taken: the loader refuses that
column, the fit *"names it, zeroes it, and records that it was not fitted,
because a ridge coefficient of exactly 0.0 for `claim` reads identically to
'fitted and came out at zero', and those are different statements"* — and then
*"re-harvesting to recover the eleventh is a day of rollouts for a term the
champion already weights at zero"*.

That reasoning is sound about **re-harvesting** and does not apply to a **duel**.
A duel needs no harvest and no fit: it sets one flag that is already a
constructor parameter and plays the deals. `w_claim` reaches
`AskWeights(claim=...)` on the shipped path with no code change at all.

The formula is now the corrected one, `F[i, 6] = pi * rest ** (1/5)` over the
five cards other than the asked one, `TERM_VERSIONS["claim"] = 2`. (The paper's
feature table still printed the withdrawn $1/6$ form over all six; corrected in
the same commit as this registration.)

## Why this term and not another of the ten

Because it is the mechanism this session's measurements point at, and they point
at it from three directions.

* **The chain.** We declare less than SESTINA ($4.027$ against $4.832$), so
  half-suits stay live longer, so our acquired cards sit publicly located **25%
  longer** (windows $10.58$ plies against $8.49$,
  `results/disclosure_cost_15300000.json`), so they meet a free card **1.092×**
  as often as we do (`results/visit_ordering_15500000.json`), so they hit more
  often despite ordering a visit **worse** than we do — we bank a free card
  $0.7774$ of the time against their $0.7164$, and when we pass one over our
  alternative fails 7 times in 1,072 against their 147 in 1,564.
* **Per ply of exposure our cards are taken back LESS often** ($0.03895$ against
  $0.04148$). The wasted-hits gap of $+1.065$ a game is **exposure time, not
  exposure rate** — so the lever is half-suit *lifetime*, which is what `claim`
  prices and nothing live in the objective does.
* **The paper already names this gap as the untouched one:** *"no arm of this
  project has yet been aimed at it: every candidate the cross-engine programme
  drew was scored on hit rate, and hit rate is the one axis on which the two
  engines nearly agree."*

## The arms

One flag, four doses, nothing else changed. `w_claim` enters an objective whose
live terms sum to $0.86$, so the doses are scaled to that and not to 1.

* **A1** `w_claim = 0.10`
* **A2** `w_claim = 0.30`
* **A3** `w_claim = 0.60`
* **A4** `w_claim = -0.20` — **both signs.** The term rewards asks that complete
  a half-suit we can claim, and the measured chain says our problem is
  half-suits that stay open; but the same measurements say we already have the
  higher share of banked free cards, and `concent` — which expresses a related
  instinct — was confirmed *negative*. A dose sweep that only looks in the
  direction the story predicts is not a measurement of the term.

## Predictions, recorded before the run

1. **The dose response is monotone in the middle** (A1, A2, A3 ordered). If it
   is not, the term is interacting with `turn` or `scarce` rather than adding,
   and no single dose should be read.
2. **A4 is negative.** If the negative dose *helps*, the chain above has the sign
   of this mechanism backwards and everything built on it needs re-reading.
3. **The most likely outcome is a null below the bar.** Every arm this project
   has aimed at inference has failed at $+0.15$, and `claim` reaches the margin
   through declarations, whose accuracy channel is bounded at $+0.2017$. What
   makes this one worth running anyway is that it reaches them through
   *lifetime* rather than accuracy, and the RACE channel — declaration
   **count**, $-0.6433$ — is not bounded by that figure.
4. **The ask hit rate falls or is flat.** `claim` prefers completing over
   hitting, so a rise would suggest the term is not doing what it says.

## The bar and the withdrawal conditions

Unchanged: **+0.15 sets/game with the interval clear of zero against SESTINA at
`BRIDGE_REV 3` AND in self-play**, paired within deal, 300 deals × 2 parities,
cluster bootstrap over deals.

An arm is **withdrawn** if either population's interval lies entirely below zero.
An arm clearing in one population only is **opponent-specific and does not
ship**.

Two conditions aimed at the harness rather than the term:

* **A1 and A3 disagreeing in sign with both intervals clear of zero** — a dose
  response that changes sign inside the swept range is a harness fault or an
  interaction, not a dose.
* **Any arm whose `weights.claim` does not equal its registered dose** at run
  time. The whole point of this registration is that a zero which was never a
  measurement got read as one; a duel that silently ran the champion under a
  candidate's name would repeat that in a worse form. The runner asserts it.

No other weight moves in any arm. `scripts4/arm_overlap.py` is run on the result
to report how many deals each arm actually changes, because an arm that changes
almost nothing and an arm that changes nothing are different claims, and P51 made
that mistake already.

---

## OUTCOME, `results/p52_claim_term.json`

$7{,}200$ games on block 15,700,000, 300 deals × 2 parities, zero fallbacks,
zero unfinished. The dose check passed: every arm's `weights.claim` equalled its
registered dose and the champion's was still 0.0.

| arm | `w_claim` | vs SESTINA (rev 3) | self-play | verdict |
|---|---:|---|---|---|
| A1 | +0.10 | −0.0633 [−0.259, +0.133] | +0.1067 [−0.112, +0.325] | no |
| A2 | +0.30 | +0.0900 [−0.200, +0.380] | +0.2233 [−0.012, +0.458] | no |
| A3 | +0.60 | −0.0467 [−0.325, +0.232] | +0.1867 [−0.032, +0.405] | no |
| A4 | −0.20 | +0.2267 [−0.051, +0.505] | −0.2000 [−0.424, +0.024] | no |

**Nothing clears. No withdrawal fires.** All four arms are genuinely distinct —
`arm_overlap` puts every pair at 500+ of 600 pairings differing, so this is not
P51's case of two names for one arm.

### Prediction 1 failed, and it is the one that decides what may be read

**The dose response is not monotone in either population.** Against SESTINA:
−0.063, **+0.090**, −0.047. In self-play: +0.107, **+0.223**, +0.187. Up then
down, both times, with A2 the peak.

The registration fixed what that means before the run: *"If it is not, the term
is interacting with `turn` or `scarce` rather than adding, and no single dose
should be read."*

So **A2 is not readable as a dose effect** — and A2 is the most promising cell
this line of work has produced. It would not ship in any case: the bar needs
$+0.15$ clear of zero in *both* populations, and A2's SESTINA figure is $+0.0900$
with an interval covering zero. But the reason it is set aside is the registered
one, not the convenient one.

### Prediction 4 failed too, and it points the same way

The ask hit rate was predicted flat or falling, because a term that prefers
completing to hitting should cost hits. It **rose** in every arm — 0.5206,
0.5236, 0.5212, 0.5207 against the champion's 0.5194. Small, but the wrong sign,
and the registration said a rise *"would suggest the term is not doing what it
says."*

Two of four predictions failed and both say the same thing: at these doses
`claim` is perturbing an objective whose three live terms already interact,
rather than adding a preference for half-suit lifetime.

### Prediction 2 is half right

A4 is negative in self-play (−0.2000) and **positive against SESTINA**
(+0.2267). A term whose sign flips between populations is opponent-specific by
definition and does not ship, but it is also a warning about A2: if a *negative*
dose can look that good against SESTINA, a positive one looking good there is
worth little.

### Prediction 3 holds

A null below the bar, as registered. That was the predicted outcome and it is
what happened.

### What this does and does not close

It does **not** close the idea that declaration count is the channel with room —
the identity still says $D_{\text{us}}$ must rise by **+0.541** a game, from
4.100 to 4.641, and the external engine reaches 4.832. What it closes is
`w_claim` **as the lever at these doses**, and the reason is legible: the term
moved hits, not declarations. `scripts4/claim_term_mechanism.py` measures
$D_{\text{us}}$ directly, which this duel's harness does not record — because a
duel that cannot see the quantity its registration is about can say whether an
arm wins and not whether the mechanism fired.
