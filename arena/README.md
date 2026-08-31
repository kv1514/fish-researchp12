# KRAKEN arena

A seeded, reproducible duelling harness for **KRAKEN** and the policies it
ships beside. Clone it, run one command, and get a win-rate matrix over every
ordered matchup.

```bash
python -m arena                 # 200 duplicate deals per matchup (~an hour)
python -m arena 20 8            # 20 deals per matchup, 8 workers (a few minutes)
python -m arena 500 8 out.json  # and write the raw cells to out.json
```

---

## ⚠️ These numbers are not comparable to the 2026-08-20 baseline study

If you arrived here from a policy-archetype report — the one with *Focused
hunter*, *Adaptive diversifier*, *Bayesian detective*, *Misdirection artist*
and *Unpredictable novice* — **do not read the two tables against each other.**

They come from a different simulator with a different belief model, a different
declaration rule, and different archetypes. A win rate here and a win rate
there are the same word for two different measurements. Nothing in this
directory reproduces, replicates, or contradicts that study; it does not
contain those archetypes and makes no claim about them.

The only honest comparison is to run both policies **inside one harness**. This
one accepts foreign engines over a JSON-lines protocol (see *Bringing your own
policy* below), which is how KRAKEN was compared against an independently
written C++ engine.

---

## The field

| policy | what it is |
|---|---|
| `kraken` | KRAKEN v1.0, the deployed configuration: exact combinatorial inference, an opponent model, belief-space lookahead, and an exhaustive search on forced declarations. |
| `kraken-nolookahead` | The same inference and ask objective with the lookahead off and fewer posterior draws. The ablation that isolates what search is worth. |
| `tuned` | The v0.3 champion. Hand-tuned ask weights, no exact inference. |
| `probabilistic` | Picks the ask most likely to succeed, and nothing else. |
| `heuristic` | Public information only. No belief state. |
| `random` | Uniform over legal actions. The floor. |

## Method, and one decision that matters

**Duplicate deals.** Every deal is played twice with the sides swapped, and the
**pair** is the unit of analysis. Deal luck cancels within a pair, which is why
a few hundred deals here resolve what would need thousands of independent
games. A tied pair counts as half.

**Independent agent seeds, deliberately.** The underlying harness seeds agent
randomness *by seat* unless told otherwise. Under that default a policy played
against a copy of itself makes bit-identical decisions in both halves of a
pair, its differential is exactly `(a-b) + (b-a) = 0` on every deal, and the
diagonal of the matrix reads **50.0% by construction**.

That is not the sanity check it looks like. It would read 50.0% even if the
harness were completely broken, because no measurement is happening. This arena
therefore fixes `independent_seeds=True`, which makes the two sides break ties
differently and turns the diagonal into a real estimate of the harness's own
noise. **A diagonal that straddles 50% is evidence; a diagonal that is exactly
50.0% is a tautology.**

**No shared deals between cells.** Each ordered pair gets its own deal block,
so no two entries in the matrix are correlated through a common deal.

## What may never enter the field

This repository contains agents that see the true deal — `oracle` and
`oracle_gated`. They exist to price a **ceiling**: how much a perfect
card-reader would gain, which bounds what any honest inference could be worth.
They are not players.

`arena/roster.py` refuses them by name *and* by substring, and raises
`CheatingAgentRefused` rather than silently producing a number. A cheating
agent's win rate is indistinguishable in print from an honest one, and once
such a number is copied into a table nothing about it reveals the difference.

## Bringing your own policy

Two routes.

**In-process.** Add an entry to `ROSTER` in `arena/roster.py` mapping a name to
any spec `fish4.registry4.make_agent` understands.

**Out-of-process, any language.** `kraken/decide.py` is a JSON-lines decision
service: one request object per line on stdin, one action per line on stdout,
holding no state between calls because every request carries the whole public
record. Point it the other way and the arena can duel anything that speaks the
same protocol — which is how KRAKEN was matched against an independently
developed C++ engine over 10,000 duplicate deals.

## Sample sizes, and what a small run can and cannot say

The default is 200 duplicate deals per matchup. Below about 40 the per-cell
Wilson interval is wider than most of the gaps in the table, so a small run
orders the field correctly and should not be quoted to a decimal place. The
diagonal is the honest gauge of that: at 6 deals it sprawled from 41.7% to
66.7%, which is what six pairs of noise looks like.

One worked example of why the split matters. In a 6-deal pilot the
`kraken` self-match read **exactly 50.0%** with a margin of **+0.000** — which
is precisely what the structural tie of the harness default looks like. It was
not one: the split was W2/T2/L2, wins and losses that happened to balance. The
rate alone could not tell those two apart, which is why the report prints the
split underneath.

### The matrix disagrees with itself, and that is the calibration

A round-robin measures every matchup **twice** — once with each policy as side
A — on different deals. Those two cells are independent estimates of one
quantity, so the gap between them is a free read on the harness's noise at
whatever sample size you ran.

In the committed 40-deal run, `kraken` against `kraken-nolookahead`:

| | margin, from KRAKEN's side | 95% |
|---|---|---|
| KRAKEN as side A | **−0.80** | [−2.15, +0.55] |
| KRAKEN as side B | **+0.60** | [−0.83, +2.03] |

**The same matchup, 1.40 sets apart, opposite signs.** Neither cell is wrong;
40 pairs is simply not enough to separate two policies this close, and both
intervals comfortably contain the truth. For reference, a 6,000-pair
pre-registered duel puts the lookahead at **+0.104 [+0.020, +0.189]** — an
effect roughly a *fortieth* of the swing between these two cells.

So: **the matrix orders the field, it does not adjudicate close pairs.** The
shutouts at the bottom (100% against `heuristic` and `random`, by 13-17 sets)
are real at any sample size. The top two rows are not separated by this run and
should not be reported as if they were.

## Reading the output

Cells are the row policy's win rate as side A. Row averages are unweighted
across the row *including* the diagonal, so a strong policy's average is pulled
toward 50% by its self-match — that is a property of the summary, not of the
policy, and the per-cell numbers are the ones to quote.

The margin table beneath reports sets per game, which is the more sensitive
statistic: a policy can win 83% of pairs by a third of a set, or by three sets,
and those are very different engines.
