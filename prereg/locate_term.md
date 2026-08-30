# Pre-registration: can an ask be priced by the declaration it enables?

**Registered 2026-08-30, before any duel of `w_locate` was run.** What existed
when this was written: the term, its seven shape tests, and the confirmation
that it is inert at zero and live above it. No margin of any kind.

## The claim, and why it is not another guess

`prereg/declaration_timing.md` decomposed the +3.41 sets/game that perfect
knowledge of a teammate's cards is worth, by routing the same cheat to one
decision at a time (600 games, anchor replicated to **0.0000**):

| the cheat reaches | ceiling over honest | share |
|---|---|---|
| the declaration channel only | +1.0767 [+0.7979, +1.3554] | 0.316 |
| the ask channel only | +0.7600 [+0.4731, +1.0469] | 0.223 |
| both | +3.4100 [+3.1625, +3.6575] | 1.000 |

`D + K = 1.84` against `T = 3.41`. **46% of the ceiling — 1.57 sets a game —
lives in neither channel alone.** It is interaction.

That result explains four consecutive nulls. The split gamma and the at-ask
covariate improved the ask channel's belief; the communication channel improved
what the team knows but delivered it through the belief; the declaration-timing
hypothesis targeted declarations. Each was reaching for at most a third of the
prize while the largest component sat untouched.

**An interaction term can only be reached by an intervention that couples the
two decisions.** This is the cheapest such coupling: price an ask by what it
will let the team *declare later*.

## The quantity is fixed by an existing finding, not chosen

What a declaration risks is how many of a half-suit's six cards have **never
been publicly located** — not how many the declarer holds. That is the paper's
mediator result and it is already established.

A successful ask locates exactly one card, permanently, for the whole table,
including our partners. So an ask's value to a future declaration is the share
of that half-suit's remaining location uncertainty it removes:

    locate = pi * rest^(1/5) / u

* `pi` — it locates nothing if it does not land.
* `1/u` — the fraction of remaining uncertainty removed, `u` being the
  half-suit's currently unlocated count. Two-to-one is worth more than
  six-to-five, which is the shape "risk tracks unlocated count" implies.
* `rest^(1/5)` — our team owning the **other five** cards. Locating a card of a
  half-suit we will never declare buys nothing. Excluding the asked card is not
  cosmetic: on a provably certain steal its own factor is exactly 0, and a
  formula that scores zero precisely where it should score highest is the bug
  both `claim` and `concent` shipped with at v1.
* **Zero when the asked card is already publicly located.** The ask then
  creates no location, and `certain` already prices a certain steal.

**Nothing in the existing basis prices this.** `claim` prices *ownership*
progress, `concent` prices concentration, and `signal` fires only on a
half-suit's first reveal and proxies by team share rather than location.

## Design

`scripts4/duel.py`, duplicate deals, the pair as the independent unit.

* **X:** KRAKEN v1.0, `V06_DEPLOYED`, unmodified.
* **Y:** the same plus `w_locate = w`, everything else identical.
* **Grid:** `w` in {0.15, 0.3, 0.6}, 400 pairs each, as a **screen**. The
  weights are in units of probability of success, the convention this basis
  already uses, and 0.3 is roughly the scale of the shipped `scarce` term.
* The best `w` by point estimate then gets a **fresh** 3,000-pair confirmation
  at new seeds. The screen's own number is never the result: picking a maximum
  out of three and reporting its interval is exactly how a null becomes a
  finding.
* Rules `wrong_distribution_outcome="opponent"` throughout.

## Decision rule, fixed in advance

**Primary:** mean paired difference in sets/game, Y − X, 95% interval, **on the
confirmation run only**.

**Ship bar: +0.15 sets/game** — the same bar the signalling channel and the
convention were held to. This is a policy change that consumes expected value
on every ask it redirects, so it earns the same bar those did.

* lower bound > 0 and point ≥ +0.15 → **ships**, after re-measuring every
  affected figure.
* lower bound > 0, point < +0.15 → real but sub-bar. Recorded, not shipped.
* interval contains 0 → the coupling does not pay at this weight. Recorded.
* upper bound < 0 → the term is harmful and the direction closes.

**Secondary, reported and not gating:** allocation and ownership error rates,
declarations per game by path, and the mean move index of our declarations —
the last because the ceiling arm declared at move 39.2 against the honest 77.8,
and if this term is doing what it claims, that number should fall.

## Withdrawal conditions

* If the screen's three arms are not **monotone or single-peaked** in `w`, the
  term is behaving unpredictably and the confirmation is not run.
* If `IllegalAction` is raised, void.
* If Y's mean moves per game differs from X's by more than 8, the term is
  changing the length of games rather than their outcome, and the effect is
  reported as tempo rather than as declaration quality.

## What a null would mean

That the interaction is real but not reachable by a one-ply proxy for it — that
pricing an ask by the location it creates is too shallow, and what is actually
needed is a search that evaluates the declaration itself at the leaf. That
would be a genuine finding rather than another unexplained null, because this
time the target is identified: `results/declaration_timing.json` says the prize
is 1.57 sets a game and says which coupling holds it.

**And a null here would NOT re-open the four closed directions.** They were each
refuted on their own terms.

---

# SCREEN OUTCOME and AMENDMENT, recorded 2026-08-30

## The screen

400 pairs per arm, identical deals and agent seeds. **Y − X**, positive means
the `locate` term is stronger:

| w | Y − X | 95% interval |
|---|---|---|
| 0.15 | +0.065 | [−0.150, +0.280] |
| 0.30 | −0.060 | [−0.407, +0.287] |
| 0.60 | +0.130 | [−0.180, +0.440] |

All three contain zero. The sequence is +0.065, −0.060, +0.130 — up, down, up.

## The withdrawal condition fires, and it fires on my design, not on the term

> If the screen's three arms are not monotone or single-peaked in `w`, the term
> is behaving unpredictably and the confirmation is not run.

A zigzag is neither, so the condition is met and **the confirmation as
registered is not run**.

**But the condition was untestable at this sample size, and that is my error.**
The screen's interval half-widths are 0.215, 0.347 and 0.310 — a mean of
**0.29, roughly twice the 0.15 ship bar**. Three arms whose true effects all
sit near zero will order themselves at random under that much noise. "Monotone
or single-peaked" was a condition this screen could not evaluate *whatever the
term does*, so its firing carries no information about the term.

That is the third condition in two days that the design could not support. The
earlier three assumed the arms were comparable in ways the experiment breaks;
this one assumed a precision the sample size does not provide. Same family:
**a condition has to be answerable by the run that is meant to answer it.**

## The amendment, and why it is not cherry-picking

The screen cannot select a weight — that is the whole point of the paragraph
above. So the weight is taken from the **registration itself**, which named one
a priori before any number existed:

> the weights are in units of probability of success, the convention this basis
> already uses, and **0.3 is roughly the scale of the shipped `scarce` term**.

**The confirmation runs at `w = 0.3`, 3,000 pairs, fresh seeds** — half-width
~0.106, which resolves the bar.

`w = 0.3` is the arm with the **worst** point estimate of the three (−0.060).
Choosing it is the strongest available evidence that the weight was not picked
off the screen. Had I taken the screen's best (0.60, +0.130) I would have been
reporting the maximum of three noisy draws as though it were an effect, which
is precisely what the registration forbade in advance:

> The screen's own number is never the result: picking a maximum out of three
> and reporting its interval is exactly how a null becomes a finding.

Everything else — the +0.15 ship bar, the four-way decision rule, the secondary
outcomes, the remaining withdrawal conditions — is unchanged.
