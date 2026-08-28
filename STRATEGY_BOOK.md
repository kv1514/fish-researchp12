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
"pair score" and "set differential" are luck-controlled — though see §1 on how
little luck there turned out to be to control. Analytics come from
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

### DEMONSTRATED - The cards you are dealt do not decide the game

Ten thousand deals, each played from both seat parities so that in the second
game one side holds exactly what the other held in the first. Under that
design the deal's share of a game's outcome variance is identically minus the
correlation between the two parities' margins, and that correlation is
**+0.0127** [−0.0150, +0.0404]. The share is **−1.3%** [−4.0%, +1.5%]: zero.

This is not what duplicate bridge finds, and the reason is structural. Fish has
**no high cards** — every half-suit is worth exactly one set, so a hand can be
awkwardly distributed but it cannot be strong — and cards move continuously, so
whatever the deal arranged is largely dissolved by the middlegame.

The deal does leave a *symmetric* trace: some deals are clumped enough that
asks land more often **for everybody**, and our ask hit rate correlates +0.087
[+0.060, +0.115] across the two parities of a deal. A deal can be textured
without being unfair, which is exactly why the texture shows up in the hit rate
and not in the margin.

**For a player:** losing a game is not evidence about the deal, and neither is
winning one. If you find yourself explaining a result by the cards, the
explanation is almost certainly wrong.

### DEMONSTRATED - One game tells you almost nothing about how you played

A game carries about fifty of your asks, so the binomial standard deviation of
your hit rate over one game is about 0.071. Across 10,000 games, the whole gap
between a won game (0.535) and a lost one (0.460) is 0.074 — one such
deviation.

Testing that properly: compare the observed spread of each rate across games
with the spread fifty coin flips at the pooled rate would produce on their own.

| rate | overdispersion | correlation across the two parities of a deal |
|---|---|---|
| our ask hit rate | 1.72 | +0.087 [+0.060, +0.115] |
| their ask hit rate | 1.71 | +0.073 [+0.046, +0.101] |
| our declaration accuracy | **1.07** | +0.018 [−0.010, +0.046] |
| their declaration accuracy | **1.03** | +0.027 [−0.001, +0.054] |

**Declaration accuracy has no game-level structure at all, on either side.**
There is no such thing as a game in which somebody read the cards better than
usual. "They declared unusually well today" is selection on coin flips.

The ask hit rate is the one rate with real structure, and it splits three ways:
**58.3%** binomial noise, **8.7%** the deal's texture, **33.0% the position you
built for yourself.** That last third is the only part any amount of skill can
move, and seeing it takes more than one game.

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

### DEMONSTRATED - Better judgement and sharper tracking are substitutes, not additions

Careful card-tracking and good ask-selection turn out to buy much the same
thing, so doing both is not worth twice as much.

Sampling more possible layouts (32 to 96) is worth **+0.54 sets per pair**
on top of the plain belief policy. Add it on top of the improved ask
scoring, though, and it is worth **nothing measurable**: played directly
against the same policy with 32 samples, +0.10 [-0.25, +0.44] over 400
duplicate deal-pairs.

For a human this is quietly encouraging. If you are already choosing your
asks well, you do not also need to hold a perfect probability distribution
over every unseen card. The two skills overlap, and the cheaper one is
enough.

### DEMONSTRATED - Card-tracking precision pays, up to a point

Sampling more possible layouts before deciding keeps paying for a policy
that is otherwise plain:

| comparison | result |
|---|---|
| 32 samples vs 8 | 32 better by **+0.93** [+0.63, +1.22] |
| 96 samples vs 32 | 96 better by **+0.54** [+0.25, +0.82] |

For a human the analogue is unglamorous: the more carefully you enumerate
who *could* hold what before choosing, the better you play. But see the
finding above, this stops paying once your ask-selection is good.

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

### DEMONSTRATED - Nearly everything you get wrong is your own team's split

Between engines, over 10,000 games, our wrong declarations break down as

| | per game |
|---|---|
| **allocation** — our team held all six, we named the wrong split | **0.1676** |
| **ownership** — an opponent still held one | 0.0083 |

**95.3%** of the errors are the split. Claiming a half-suit an opponent still
holds is, at this level, essentially a solved problem; saying which of your own
teammates has what is not.

### DEMONSTRATED - The split freezes, and it freezes before you decide

This is the structural fact behind the number above, and it follows from one
rule. You may only ask in a half-suit you hold a card of. So **the moment your
team holds all six, no opponent can legally ask there again** — and since you
cannot ask a teammate, no public event will ever touch that half-suit again.

The split is frozen at the instant the last card arrives, with exactly the
cards that were dealt and never asked for still unknown. Measured directly: of
the misplaced cards in a disclosure probe, **398 of 398** had never moved in
public.

Two things follow that matter at the table.

**Waiting gains you nothing.** There is no information coming. Whatever you
know about the split when the sixth card lands is what you will know at the
deadline. The usual instinct to hold off and watch is worthless here — it is
worthless specifically here, and not in general.

**It is a communication problem, not a deduction problem.** Every card is held
by someone who knows they hold it. The team collectively has the answer and no
member of it does, and the game supplies no channel to share it. The only
channel that exists is a deliberately failed ask in the frozen suit, which
certifies that you hold a card of it — and measured in play that costs a turn,
gains +0.12 sets a game, and *adds* an error almost as often as it avoids one.

**REFUTED, and it inverted.** The obvious lever is that any member of the team
may declare, on their own turn: someone holding four of the six guesses two,
someone holding one guesses five, and the information is frozen either way so
waiting for the better-placed teammate should cost tempo and nothing else.
Measured over 16,156 wholly-held declarations, the error rate goes the other
way — it *rises* with how much the declarer holds:

| the declarer's own cards | n | error rate |
|---|---|---|
| 1 | 2,640 | 0.017 |
| 2 | 2,024 | 0.048 |
| 3 | 1,282 | 0.042 |
| 4 | 1,494 | 0.063 |
| 5 | 1,830 | 0.068 |
| 6 | 6,468 | 0.000 |

Six is trivially perfect: you hold every card and there is nothing to name.
Over the rest it is selection. A player holding *one* card of a half-suit only
declares it when the other five are already pinned by the public record — those
are the positions where the information happened to be there. Holding *five*
leaves exactly one card unaccounted for, and if that card never moved in public
it is a coin flip between two teammates, on a set that feels certain.

**The lesson for a player is the useful part.** Your risk on a set your team
wholly holds is not proportional to how many of it you are missing. It is about
whether the cards you are missing have ever moved. Five in your hand and one
that was dealt and never asked for is a **worse** position than one in your hand
and five that have all been seen — and it does not feel that way.

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

### DEMONSTRATED - None of this is specific to our 54-card variant

Everything above was measured on the nine-half-suit deck (with the 8s and
jokers). If those findings were artifacts of adding a synthetic half-suit
rather than facts about Literature, they should evaporate on the classic
48-card game. They do not.

| measure | 54-card | 48-card (classic) |
|---|---|---|
| gain from the improved policy | **+1.51** [+1.17, +1.85] | **+1.37** [+1.01, +1.72] |
| cards per possession | 1.72 | 1.74 |
| ask success (early / mid / late) | 60% / 67% / 64% | 59% / 67% / 66% |
| failed-ask share | 36.3% | 36.0% |
| seat advantage | +0.03 [-0.26, +0.33] | +0.08 [-0.21, +0.38] |
| median claim delay | 0 | 0 |

*(300 games and 400 duplicate deal-pairs per variant.)*

The two rulesets play remarkably alike. The only clear difference is
length: 107 asks per game on 54 cards versus 93 on 48, which is simply the
extra half-suit and the extra card each. Everything strategic transfers.

So if you play the classic no-8s game, all the advice in this book applies
to you unchanged.

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

- **RESOLVED, and inverted.** Is information leakage from asking a real cost?
  The camping theory said our silence causes their misdeclarations; it was
  refuted, and the overdispersion measurement in §1 says there was never a
  channel for it to work through — declaration accuracy has no game-level
  structure on either side, so no amount of what we do makes them read better
  or worse *that game*.
- **SPECULATIVE** Who on a team should declare a frozen half-suit. Any member
  may, on their own turn; the one holding four of the six guesses two while the
  one holding one guesses five, and the information is frozen either way. See
  §3.
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
