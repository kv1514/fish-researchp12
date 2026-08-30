# Pre-registration: a different action model for the declaration than for the ask

**Registered 2026-08-30, before any duel of `claim_gamma` was run and before any
margin of any kind existed.** What existed when this was written: the parameter,
its five tests, the confirmation that the champion is bit-identical at zero, the
measured cost gate (~40 extra posteriors a game, ~40% of decisions), and the
diagnostic run below — which contains no margin.

## The finding this acts on

`results/split_calibration.json`, 7,384 (decision, live half-suit) predictions
against `post.prob_assignment` conditioned by `prob_all_with` — what
`ClaimEvaluator` tier 3 actually reads against its 0.97 threshold:

| population | predicted | actual | bias |
|---|---|---|---|
| all live half-suits | 0.428 | 0.453 | −0.024 |
| **our team holds all six** | **0.453** | **0.650** | **−0.197** |

Calibrated everywhere; under-confident by 20 points in exactly the half-suits
we declare from, at every card count `k`, and detectable from `p_team_joint`.

`results/split_why.json` then found the mechanism, 1,619 frozen pairs re-scored
on the **same belief at the same decisions**:

| | 480 draws | 1920 | 5760 | | γ=0.0 | γ=0.35 | γ=0.7 | γ=1.4 |
|---|---|---|---|---|---|---|---|---|
| bias | −0.219 | −0.244 | −0.237 | | −0.337 | −0.219 | −0.143 | −0.025 |

**Flat in draws, monotone in γ.** Twelve times the sampling moves it 0.02; four
times the action-model weight nearly eliminates it. It is not the sampler.

Silence was ruled out before running: `silence_delta` is 1.0 on the shipped
path so the mechanism never fires, and it re-weights worlds by team ownership,
which is the event this measurement conditions on.

## Why a *separate* γ and not a higher one

`prereg/gamma_split.md` already refuted a uniform raise, on teammate top-1. The
reason the two can differ is that **the two decisions are scored differently**:
an ask reads the argmax, a declaration is compared against 0.97. At that gate,
on those 1,619 positions:

| arm | clears 0.97 | right when it does |
|---|---|---|
| deployed γ=0.35 | 277 (17.1%) | 0.996 |
| **γ = 0.7** | **312 (19.3%)** | **0.974** |
| γ = 1.4 | 549 (33.9%) | 0.918 |

γ = 1.4 doubles the volume and is wrong 8.2% of the time; under
`wrong_distribution_outcome="opponent"` a wrong declaration hands the set over,
so that is the misdeclaration v1.0 measured, not a trade.

## The weight, fixed here, on a mechanism and never on a margin

**γ = 0.7.** It is the only arm in the table that buys volume at near-equal
precision, and the table is precision-and-volume at the gate — a mechanism
quantity on the champion's own transcripts, which cannot be traded for a
margin. That is the same licence the `declare_bite` screen ran under.

`claim_gamma` is inert at 0.0 and the champion is bit-identical there, asserted
by `tests4/test_claim_gamma.py`, which also asserts that a zero weight pays for
no posterior and that the cost gate actually bites.

## A mechanism screen first, with its rules fixed here

`scripts4/path_ledger.py --arm claim_gamma=0.7` against the same run at the
default, 120 deals. **Both rules below are about quantities the treatment is
supposed to move, and both are answerable by this run** — the discipline this
project has now had to learn four times.

* **If declarations per game do not rise by at least 5%**, the parameter is not
  reaching the decision the operating-point table describes, and **no duel is
  run.** A parameter that changes the belief but not the declaration count is
  the `locate` failure again.
* **If wrong declarations per game more than double**, the precision cost is
  worse in play than at the gate and **no duel is run at this weight.**

Neither rule can be met by an arm that is merely noisy: both are ratios of
counts on 120 deals, where the champion makes ~4.6 declarations a game.

## Design of the confirmation

`scripts4/duel.py`, duplicate deals, the pair as the independent unit.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same plus `claim_gamma = 0.7`. Everything else identical —
  `opponent_gamma` stays 0.35, so the ask channel is untouched by construction.
* **3,000 pairs at fresh seeds**, half-width ~0.11.
* Rules `wrong_distribution_outcome="opponent"` throughout.

## Decision rule, fixed in advance

**Primary:** mean paired difference in sets/game, Y − X, 95% interval.

**Ship bar: +0.15 sets/game** — the bar the signalling channel, the convention,
`locate` and the declarability term were all held to.

* lower bound > 0 and point ≥ +0.15 → **ships**, after re-measuring every
  affected figure and re-checking the site's move latency against the cost.
* lower bound > 0, point < +0.15 → real but sub-bar. Recorded, not shipped.
* interval contains 0 → the calibration gap does not convert into sets.
* upper bound < 0 → harmful, and the direction closes.

## Secondary outcomes, reported and not gating

* Declarations per game by path (voluntary / gate / forced / exact).
* Allocation and ownership wrong-declaration rates per game.
* **Mean move index of our declarations.** The ceiling arm declares at **39.2**
  against the honest **68.0**; `locate` moved it 0.3. This is the number the
  whole story predicts should fall.
* Wall-clock per decision and extra posteriors per game — a shipping cost, and
  never a strength claim.

## Withdrawal conditions

* `IllegalAction`, a null action, or an unfinished game on either side → void.
* Y's mean moves per game differing from X's by more than 8 → the parameter is
  changing the length of games rather than their outcome, and the effect is
  reported as tempo. Measured separately, as `scripts4/duel.py` does not report
  it.

## The question a duel answers that no table above can

Whether the extra correct declarations are **sets we would have won anyway**,
later, by a safer route. The operating-point table counts opportunities per
decision, and the same half-suit appears at many decisions; declaring at move
50 rather than move 70 gains nothing if nobody was going to contest it. That is
precisely what a paired margin measures and a reliability diagram cannot, and
it is the most likely way this comes back null.

## What a null would mean

That the engine's under-confidence is real, detectable, mechanistically
explained — and worth nothing, because the declarations it withholds are not
contested. That would be a fifth measured case of a better belief buying
nothing in play, and at that point the honest conclusion is that this engine's
remaining loss is not an inference problem at all.

---

# SCREEN OUTCOME, recorded 2026-08-30: the rule fires, no duel is run

## The mechanism screen

`scripts4/path_ledger.py --vs=self`, 480 games (240 deals × 2 parities),
identical deals and agent seeds, our seats only:

| path | deployed n | /game | wrong | γ=0.7 n | /game | wrong |
|---|---|---|---|---|---|---|
| exact | 252 | 0.525 | 0 | 236 | 0.492 | 0 |
| voluntary | 1703 | 3.548 | 1 | 1681 | 3.502 | 0 |
| gate | 106 | 0.221 | 21 | 108 | 0.225 | 19 |
| forced | 99 | 0.206 | 41 | 93 | 0.194 | 39 |
| **TOTAL** | **2160** | **4.500** | **63** | **2118** | **4.413** | **58** |

**Declarations per game FELL by 1.9%** against a rule requiring a 5% rise.

> If declarations per game do not rise by at least 5%, the parameter is not
> reaching the decision the operating-point table describes, and no duel is run.

**The rule fires. No duel is run.** The arm's own margin on those games is
−0.1833 sets/game, which is not a pre-registered outcome and is recorded only
because it points the same way.

## The mechanism check the registration named

90 deals × 2 parities, our three seats carrying the arm:

| arm | mean declaration move | declarations/game | wrong/game |
|---|---|---|---|
| deployed | **70.6** | 4.500 | 0.0889 |
| γ = 0.7 | 69.6 | 4.489 | 0.1056 |
| γ = 1.4 | 66.5 | 4.528 | **0.1500** |

The registration predicted this number should fall materially if the story were
right. It moves **1.0** at γ=0.7 and **4.1** at γ=1.4, against the **31.4** that
separates the honest engine from the teammate oracle's 39.2. And misdeclarations
per game rise by 19% and 69%.

So the calibration gap is real, detectable, mechanistically explained — **and
correcting it does not move the declaration decision.** That is the fifth
measured case in this project of a better belief buying nothing in play.

## Why, and this is worth more than the parameter

The ledger says it plainly. **The voluntary path is already 1 wrong in 1,703.**
The 0.97 gate is not what holds declarations back — the engine is already
declaring nearly everything it safely can, and a sharper joint gives it almost
nothing new to declare.

**62 of the 63 errors come from `gate` and `forced`:**

| path | /game | error rate |
|---|---|---|
| voluntary | 3.548 | **0.06%** |
| gate | 0.221 | **19.8%** |
| forced | 0.206 | **41.4%** |

Those are not declarations the engine chose while feeling under-confident. They
are declarations it had **no alternative to** — `gate` fires when the ask we
were about to make cannot land, `forced` when no legal ask exists at all. No
amount of calibration helps a decision with one option.

## Where that points, and it is not a closed direction

Arriving in a forced position is an **ask-side outcome**. 0.427 declarations a
game are made from those two paths and they carry essentially the entire error
ledger, so the lever is not how well we declare when stuck — `prereg/
forced_exhaustive.md` already shipped the best available play there — but **how
often we get stuck at all.**

Nothing in the twelve-term ask basis prices this. `deplete` rewards draining an
*opponent*; `scarce` is our team's share of a half-suit. Neither prices **our
own remaining ability to ask** — the number of half-suits in which we still hold
a card and an opponent still plausibly holds one. That quantity is computable
from the belief already on the context, it is a property of the position we
choose to move into, and it has never been measured.
