# Pre-registration: is the information we are missing our teammates', or theirs?

Written before the runner exists. Every input below is a figure this project
already holds.

## A SAFETY RULE THAT GOVERNS THIS ENTIRE FILE

Every arm here except the baseline **cheats**. `fish4/oracle.py` is handed the
true deal. Its margins are **bounds on what better inference could buy**, and
they are not strength measurements. They must never appear in a strength
ladder, never be quoted beside an honest engine's margin as though the two were
comparable, and never enter the head-to-head table. Any figure this produces
carries the word *ceiling* wherever it is written down.

`OracleBot` already refuses to act unless `see_deal` has been called, precisely
so a cheat cannot silently degrade into an honest agent and put a number in a
results file that means neither thing. Nothing here relaxes that.

## The question, and why nothing answers it yet

Over 10,000 games (`results/margin_decomposition.json`):

| our wrong declarations | per game |
|---|---|
| **allocation** — our team held all six, we named the wrong split | **0.1676** |
| ownership — an opponent still held one | 0.0083 |

**95.3% of what we get wrong is our own team's split.** Those are two different
inference problems with two different cures. Knowing where a *teammate's* cards
are fixes the first; knowing where an *opponent's* are fixes the second.

`results/inference_ceiling.json` measured the ceiling once, at **+17.3
sets/pair** [+16.58, +18.02] over 10 pairs — and it measured full omniscience,
which tells you the value of everything at once and therefore the value of
nothing in particular. It cannot say which of the two problems the headroom is
in, and the project's largest open lever (transcript inversion, task #53) is
aimed squarely at one of them.

## The instrument

`OracleBot(side=...)`, added today with `TERM`-style tests
(`tests4/test_oracle_side.py`): the revealed pool is restricted to cards held
by the seat's own team (`"team"`), by the opposition (`"opp"`), or both
(`"all"`, the historical default, verified bit-identical so no stored ceiling
figure changes meaning). A seat is never told its own cards under any setting,
because its own hand is already pinned and `reveal` is a fraction of what is
genuinely hidden.

## THIS IS NOT A DECOMPOSITION, and the report must say so

Telling a seat every one of its teammates' cards also tells it, by elimination,
that the remaining cards sit with opponents — it just does not say *which*
opponent. So the two arms are **two bounds on two different questions**, not
two halves that sum to omniscience. The `"all"` arm is included specifically so
that the temptation to add them is visibly wrong: if team + opp exceeds all,
that is the elimination effect being double-counted, not a paradox.

## Arms

Our three seats only; the opposition is `dylan_v07` at `BRIDGE_REV = 2`
throughout, and never cheats.

- **A** = `V06_DEPLOYED`, honest. The baseline every effect is measured against.
- **T** = `OracleBot(side="team", reveal=1.0)`. Perfect knowledge of teammates'
  cards, ordinary inference about opponents'.
- **O** = `OracleBot(side="opp", reveal=1.0)`. The mirror.
- **F** = `OracleBot(side="all", reveal=1.0)`. Omniscience, as the consistency
  check described above and as a replication of the existing $+17.3$ figure at
  a sample size that can support it.

## Design

Duplicate-deal paired, both seat parities, fresh seed block, award rule pinned.
**600 games per arm.** The effects here are expected to be enormous — the
existing omniscience figure is $+17.3$ sets/pair off 10 pairs — so this is
sized for the *smallest* arm rather than the largest, and 600 games puts the
standard error near 0.11 sets/game against effects expected in whole sets.

## Primary outcome, fixed now

Paired difference of set margins against v0.7: T minus A, and O minus A,
reported separately and never summed.

## Secondary outcomes, fixed now

1. **Wrong declarations per game split by class, per arm.** This is the
   mechanism and it is the reason the run exists: T should crush the allocation
   count and leave ownership roughly alone; O should do the reverse. If T fixes
   ownership errors more than allocation ones, the story in
   `results/margin_decomposition.json` is wrong and that matters more than any
   margin here.
2. The declaration path ledger per arm.
3. `pinned_by_cheat` per arm, so the size of each cheat is reported rather than
   implied.

## Ship bar

**None. Nothing here can ship, ever.** There is no bar because there is no
decision: an arm that cheats is not a candidate. The output is a bound, and its
use is to decide whether task #53 is worth building.

## What would make this worth acting on, fixed now

If T minus A is large and O minus A is small, transcript inversion on
**teammates** is the priority, and it is the safe half of that idea: we know
our teammates' policy exactly, because they run the same engine, whereas the
opponent choice model has already been measured with the wrong sign
(`-1.0041` [-1.1434, -0.8648] against our own `+1.2071`).

If the two are comparable, then the allocation/ownership split in the error
ledger does not translate into an information-value split, and the reason for
that would be the most interesting thing here.

## Expected outcome, written down in advance

I expect **O to beat T**, and I expect that to be surprising to anyone reading
only the error ledger. The reason is that knowing opponents' cards makes every
ask land, and asks are how sets are acquired at all — while knowing teammates'
cards only improves the declaration you make once the set is already assembled.
The error ledger counts mistakes; it does not count the sets we never got near.
So the two arms measure different currencies, and the ask currency is bigger.

If that is right, then the allocation finding is about where our *errors* are
and not about where our *headroom* is, and those are different questions that
this project has been at risk of conflating — including in the bottleneck table
I rewrote in `RESEARCH_LOG.md` this morning, which ranks the teammate problem
first on error share alone.

---

# Outcome: the prediction was wrong, and the error ledger was right

Run 2026-08-28, `scripts4/ceiling_split.py 300 3`, 600 games per arm on
identical deals, both parities, `BRIDGE_REV = 2`, zero fallbacks, zero
unfinished. `results/ceiling_split.json`.

**Every figure below is a bound obtained by cheating.** None is a strength
measurement, none belongs in a ladder, and none may be quoted beside an honest
margin.

| arm | margin | ceiling over honest |
|---|---|---|
| A honest | +2.3033 | — |
| **T** teammates' cards known | +5.7133 | **+3.4100** [+3.1625, +3.6575] |
| **O** opponents' cards known | +3.6100 | **+1.3067** [+1.0070, +1.6063] |
| F everything known | +8.9100 | +6.6067 [+6.4004, +6.8129] |

## The registered prediction, and how wrong it was

I predicted **O would beat T**, reasoning that knowing opponents' cards makes
every ask land while knowing teammates' cards only improves a declaration on a
set already assembled — and I wrote that this would be "surprising to anyone
reading only the error ledger", and that the error ledger measures where our
mistakes are rather than where our headroom is.

T beats O by a factor of **2.6**. The error ledger was right and my gloss on it
was wrong: the allocation/ownership split *does* translate into an
information-value split, and the bottleneck table in `RESEARCH_LOG.md` that
ranks the teammate problem first on error share alone is ranking it correctly.

## What the mechanism table does and does not show

| arm | allocation/game | ownership/game |
|---|---|---|
| A honest | 0.1533 | 0.0083 |
| T | **0.0000** | 0.0000 |
| O | **2.4950** | 0.0000 |
| F | 0.0000 | 0.0000 |

**T's zero is definitional, not evidence.** A seat that knows every teammate's
cards and its own knows the whole team's holding, so the split is not inferred
— it is read off. Registering that as a mechanism check was a mistake: the
check cannot fail, so it cannot confirm anything either.

**O's 2.4950 is the informative cell**, and it is sixteen times the honest
baseline. Perfect opponent knowledge means never claiming a half-suit an
opponent still holds — ownership errors go to zero, as expected — while the
split among teammates stays exactly as hidden as before. The engine assembles
far more sets and misplaces a far larger share of them.

There is a hypothesis for *why* the rate rather than merely the count rises,
and it is this session's own mediator result: what a declaration risks is how
many of its six cards have never been publicly located. An engine that never
misses an ask assembles half-suits **fast**, before the public record has
located anything, so it declares sets whose cards have never moved. That is
consistent with `results/declarer_holding_self.json` and it is **not measured
here** — the ceiling runner does not record the unlocated count, and this
paragraph is a hypothesis rather than a result.

## Sub-additive, which is the opposite of what the registration braced for

$T + O = +4.7167$ against $F = +6.6067$. The registration included the
omniscient arm expecting the *elimination* effect to make the two halves
over-count — "if team + opp exceeds all, that is the elimination effect being
double-counted". They fall short instead by $1.89$ sets, so the two kinds of
knowledge are **complementary**: holding both is worth more than the sum of
holding each alone. The reason is plain once seen — knowing where a card is not
only helps if you can act on it, and acting requires knowing whose turn it is
worth taking.

## Consequence for task #53

Transcript inversion aimed at **teammates** is the priority, and this is the
run that licenses saying so. It is also the safe half of that idea: teammates
run the same engine, so their policy is known exactly, where the opponent
choice model has already been measured with the wrong sign ($-1.0041$
[$-1.1434$, $-0.8648$] against our own $+1.2071$).

The ceiling is $+3.4100$ and no realistic inference gets near it. But it is now
a measured target rather than a guess, and it is 2.6 times the other one.
