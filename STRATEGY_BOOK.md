# Fish Strategy Book

What simulation says about strong Literature/Fish play. Every claim carries
an evidence tier:

- **DEMONSTRATED** - statistically significant, confidence intervals given.
- **PROMISING** - consistent signal, sample not yet decisive.
- **SPECULATIVE** - hypothesis with an experiment queued, no data yet.

Setup unless stated otherwise: 54-card variant (nine half-suits including
8s + Red Joker + Black Joker), Wikipedia-baseline rules, six players, teams
0/2/4 vs 1/3/5. Evaluation uses **paired deals**: every deal is played twice
with the teams swapped, on the same cards and the same agent randomness, so
"pair score" and "set differential" are luck-controlled. Analytics come from
400-game homogeneous tables at two skill tiers: `memory` (perfect logical
bookkeeping) and `probabilistic` (belief sampling).

---

## 1. What separates strong from weak players

### DEMONSTRATED - Turn retention is the single best skill statistic

A "possession" is a run of consecutive asks before losing the turn.

| tier | cards gained per possession | possessions gaining 0 cards |
|---|---|---|
| memory | 0.68 | 62% |
| probabilistic | 1.61 | 40% |

*(400 games each; 30,055 and 16,457 possessions.)*

Better belief tracking more than **doubles** cards extracted per turn. Note
the second-order effect: stronger tables have *fewer, longer* possessions
(16k vs 30k for the same number of games) because the turn changes hands
less often. If you want one number to measure a Fish player, measure how
many cards they collect before handing over the turn.

### DEMONSTRATED - Logical bookkeeping dominates everything below expert level

Perfect deduction alone (`memory`) beats a public-information heuristic by
**11.86 sets per deal-pair** (95% CI [11.66, 12.06], 400 pairs, winning
*every single pair*). Adding probabilistic inference over deal-consistent
worlds adds a further **2.07** [1.50, 2.63] (120 pairs).

Practical reading: the gap between a casual player and a good one is almost
entirely "did you track, and chain, every implication of every question".
The gap between good and expert is probabilistic judgement on top of that.

---

## 2. Asking

### DEMONSTRATED - Ask accuracy rises from the opening into the midgame

Success rate by game phase (thirds of each game):

| tier | phase 1 | phase 2 | phase 3 |
|---|---|---|---|
| memory | 38.1% | 43.5% | 40.8% |
| probabilistic | 57.7% | 65.9% | 63.4% |

Openings are the *least* informed part of the game, the midgame the most.
Information accumulates faster than cards leave the table, then late-game
attrition erodes the edge slightly.

**Implication:** early asks are cheap in information terms but expensive in
accuracy. The opening is where an engine should be most willing to trade an
uncertain ask for information; the midgame is where accuracy is cashed in.

### DEMONSTRATED - Think about who gets the turn when your ask fails

This is the first change that made our strongest agent measurably stronger.

The baseline policy ranks asks by success probability and how many cards it
already holds in that half-suit. It does not consider *which opponent
receives the turn* if the ask fails. Adding a penalty proportional to the
target's hand size (large hands convert a turn into more asks and more
claims; a player down to one or two cards can do little with it), applied
only to the failure branch, gains:

| penalty weight | gain over baseline, sets per deal-pair | 95% CI |
|---|---|---|
| 0.15 | **+0.48** | [+0.21, +0.75] |
| 0.30 | **+0.48** | [+0.19, +0.77] |
| 0.60 | **+0.81** | [+0.53, +1.08] |

*(600 duplicate deal-pairs per cell; all intervals exclude zero.)*

**Practical advice:** when two asks look equally likely to land, prefer the
one that, if it misses, hands the turn to the opponent holding fewer cards.
The cost of arming a card-rich opponent is real and measurable, and it is
the sort of thing a strong human already senses but rarely quantifies.

A caution about how this was measured: the first version of this experiment
reported the *opposite* conclusion with tight confidence intervals at n=1000
per cell. The agent used for the ablation had accidentally also weakened a
different term, so it compared two changes at once. The lesson generalizes
beyond this project: an ablation is only meaningful if the ablated agent
provably reduces to the baseline when the new weight is zero, and that is
now enforced by a test.

### DEMONSTRATED - These are tie-breakers, not primary criteria

Both winning ideas show the same shape when you push them harder: they help
at modest weight, stop helping at medium, and become actively destructive
at large weight.

| weight | turn-risk | scarcity |
|---|---|---|
| light (0.6 / 0.2) | **+0.56** | **+0.65** |
| medium (1.0 / 0.4) | +0.10 | +0.57 |
| heavy (1.6 / 0.8) | **-1.51** | **-1.32** |

*(600 duplicate deal-pairs per cell.)*

That inverted-U is the signature of a **tie-breaker**. Success probability
is still the main thing; these considerations are for choosing among asks
that are otherwise close. Let either one start overriding a materially
better chance of getting the card and you lose more than you gain.

The practical instruction is therefore precise: pick the asks most likely to
succeed, and *when two are close*, take the one that risks less turn and
fights for a suit you are winning. Do not go looking for clever asks at the
expense of likely ones.

### DEMONSTRATED - The two ideas stack

They are not redundant. Applied together at their individual best weights:

| policy | gain over baseline, sets per deal-pair |
|---|---|
| turn-risk 0.6 alone | +0.56 [+0.27, +0.86] |
| scarcity 0.2 alone | +0.65 [+0.37, +0.93] |
| **both together** | **+1.41** [+1.11, +1.70] |

The combination is worth slightly more than the sum of its parts, which
means the two terms are discriminating between different asks rather than
both re-ranking the same ones.

### DEMONSTRATED - Fight hardest for the suits your team is already winning

Adding a bonus for asking within contested half-suits where your team
already holds the majority gains **+0.55 sets per deal-pair**
[+0.26, +0.83] at weight 0.20 (600 pairs). Concentrating effort where you
are ahead converts near-misses into completed sets faster than spreading
attention evenly.

### DEMONSTRATED - Do NOT go hunting for players who are nearly out of cards

A term rewarding asks that drain an opponent toward zero produced
**+0.01 sets per deal-pair** [-0.24, +0.26] at weight 0.15: no effect
whatsoever. The popular intuition that you should "finish off" a
short-handed opponent is not supported. What matters about an opponent's
hand size is the *turn-risk* effect above (avoid arming a card-rich
opponent), not a bonus for emptying a poor one.

### PROMISING - Revealing a new half-suit has a small real cost

Penalizing asks that expose a half-suit you have not previously shown gains
**+0.29 sets per deal-pair** [+0.01, +0.57] at weight 0.15, with the
interval only barely excluding zero; a weaker penalty (0.05) showed nothing
[-0.14, +0.42]. So the cost of telegraphing your holdings appears real but
small, and it needs a larger sample before it belongs alongside the
demonstrated effects.

### DEMONSTRATED - Precision of card-tracking has not hit diminishing returns

Sampling more possible layouts before deciding keeps paying:

| comparison | result |
|---|---|
| 32 samples vs 8 | 32 better by **+0.93** [+0.63, +1.22] |
| 96 samples vs 32 | 96 better by **+0.54** [+0.25, +0.82] |

For a human the analogue is simple and unglamorous: the more carefully you
enumerate who *could* hold what before choosing, the better you play, and
you are probably not yet at the point where extra care stops paying.

### DEMONSTRATED - Failed asks are normal, not a mistake

Failure share: **59.2%** of asks at `memory` level, **37.8%** at
`probabilistic`. Even strong play fails about two asks in five. A failed ask
is a routine cost of doing business, and it hands information to *everyone*,
not just the target. Judge a player by cards per possession, not by their
failure rate.

---

## 3. Claiming

### DEMONSTRATED - Strong players claim sooner

Delay between "your team demonstrably holds all six cards" and the actual
claim, in actions:

| tier | median | mean | 90th pct |
|---|---|---|---|
| memory | 2 | 29.3 | 100 |
| probabilistic | 0 | 14.5 | 55 |

The stronger tier claims at the first opportunity (median 0) about twice as
often. The long tail is real though: a p90 of 55 actions means even good
agents sometimes sit on a completed set, usually because they hold the cards
but cannot yet prove *which teammate* holds what.

### DEMONSTRATED - Do not claim early. Claim confidence is effectively bimodal.

A direct sweep of the claim-confidence threshold, 150 paired deals per cell,
everything else held identical:

| threshold vs baseline 0.97 | pair score for 0.97 | set diff per pair | reading |
|---|---|---|---|
| vs 0.60 | 0.590 [0.510, 0.666] | **+0.71 [+0.34, +1.08]** | 0.97 clearly better |
| vs 0.70 | 0.570 [0.490, 0.647] | **+0.45 [+0.18, +0.72]** | 0.97 better on differential |
| vs 0.85 | 0.497 [0.418, 0.576] | -0.01 [-0.09, +0.06] | indistinguishable |
| vs 0.999 | 0.500 [0.421, 0.579] | +0.00 [+0.00, +0.00] | **identical play** |

Two findings, one of which refutes a prediction this project made:

1. **Claiming eagerly is a real, measurable mistake.** Dropping the bar to
   0.70 costs about 0.45 sets per deal-pair; 0.60 costs 0.71. An
   expected-value model built here had predicted an optimal threshold near
   0.70. The experiment **falsified it**. The model treated waiting as
   roughly a coin flip on resolving the split, when in practice continued
   play localizes teammate holdings much more reliably than that.

2. **Anywhere from 0.85 to near-certainty plays the same.** The 0.97 vs
   0.999 comparison produced a differential of *exactly zero* across 150
   paired deals: the two never diverged. That means strong agents essentially
   never hold a claim whose confidence sits in that band. Claim confidence
   is **bimodal**: you either know the split or you do not, and the
   in-between case that threshold-tuning worries about barely occurs.

Practical advice for a human: do not agonize over your claim threshold. Wait
until you actually know the distribution. The cost of guessing early is
real; the benefit of shaving your confidence bar is zero.

### DEMONSTRATED - Null sets are a skill signal

Sets nulled per deal-pair: random ~2.5, heuristic ~1.4, belief-tracking
tables ~0.6. Nulling a set is usually a bookkeeping failure, not a gamble
that did not pay off.

### PROMISING - The binding constraint is teammate localization, not card location

Agents that know their team holds a set still delay when they cannot place
cards *within* the team. This is the mechanism behind the claim-delay tail
and suggests a concrete human tactic: **asks that disambiguate teammate
holdings can be worth more than asks that win cards.** Watching engine
replays shows sets nulled precisely this way (a team holding five of six
cards mis-declaring the distribution).

---

## 4. The 8s + Jokers half-suit

### DEMONSTRATED - It plays essentially like any other half-suit

| metric | Specials (8s + Red/Black Joker) | the eight natural half-suits |
|---|---|---|
| mean resolution order | 3.97 | 4.00 |
| null rate | 4.75% | 6.0% |

*(probabilistic tier, 400 games, n=400 specials vs 3,200 natural sets; the
memory tier agrees: 4.08 vs 3.99, 5.75% vs 4.84%.)*

Neither difference is meaningful. Despite the intuition that a synthetic
suit of four 8s plus two jokers would resolve later or null more often, **it
does not**, at either skill tier. Treat it as a normal half-suit.

Caveat: measured under agents that do not deliberately conceal suits. If
deception strategies emerge in later training, re-test. Whether the Red and
Black Joker differ from each other after controlling for information state
is still open.

---

## 5. Structure of the game

### DEMONSTRATED - There is no measurable first-move or seat advantage

Set differential for the *starting* player's team, starting seat rotated
across deals:

| tier | mean differential | 95% CI |
|---|---|---|
| memory | -0.125 | [-0.367, +0.117] |
| probabilistic | -0.033 | [-0.275, +0.210] |

Both intervals comfortably contain zero at n=400. Six-player Literature
appears **seat-balanced**: moving first is worth nothing detectable.

### DEMONSTRATED - Fish positions can repeat forever

The exact solver proved the state graph is **cyclic**: two opponents can
trade a card back and forth and return to an identical position. Fish is a
*loopy* game, and stalemates are a genuine strategic feature, not a bug.
A side that can only lose by claiming will rationally stall forever, which
is why the engine needs an explicit progress rule and why human games need
a social convention to break deadlocks.

---

## 6. On thinking ahead (a methodological warning that is also strategy)

### DEMONSTRATED - Naive lookahead is worse than a good heuristic here

Two independent search designs lost badly to the simple belief policy they
were built on (ISMCTS scored 0.062 against it over 32 paired deals). The
measured cause: **the variation in a position's value across possible
hidden-card layouts is about 2.4x larger than the difference between the
best and worst candidate move**. Evaluating different moves against
different guessed layouts produces a ranking dominated by luck.

Once every candidate was compared against *identical* sampled layouts, the
deficit vanished (0.062 to 0.562, statistically neutral).

**The human lesson transfers directly:** when you reason "if the cards lie
like this, my best move is X", you must test *every* candidate move against
the *same* imagined layout, and repeat across several layouts. Judging move
A against one imagined world and move B against another is worse than not
thinking ahead at all.

---

## 7. Open questions (experiments queued)

- **SPECULATIVE** Is information leakage from asking a real cost? Asking in
  a half-suit publicly reveals you hold one of it.
- **SPECULATIVE** Optimal claim threshold, and how it should shift with the
  score and the number of unresolved sets.
- **SPECULATIVE** Target selection: should you interrogate the opponent with
  the fewest cards?
- **SPECULATIVE** Deliberately delaying a certain claim as a stalemate
  breaker.
- **SPECULATIVE** Whether coordination conventions emerge in self-play
  without any explicit communication channel, and whether they survive
  cross-play against independently trained partners. (This distinction
  matters: an engine that only succeeds with copies of itself using a
  private convention has not solved general Fish.)
