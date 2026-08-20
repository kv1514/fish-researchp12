# Fish Strategy and Findings — Plain-English Translation

This translates the engine's technical results into advice a human Fish player
can use. It is deliberately honest about the difference between measured facts,
promising evidence, and ideas that have not yet been proven.

## The short version

Fish is not mainly a game of guessing individual cards. It is a game of managing
three things at once:

1. **Card value** — can this question win a card now?
2. **Information value** — what will both teams learn from the question and its
   answer?
3. **Turn-control value** — if the answer is no, are you happy to give that
   opponent the turn?

A strong move should be judged on all three. The most likely successful ask is
not automatically the best ask.

## What the simulations actually demonstrated

### 1. Remembering and using public information is enormously valuable

The probabilistic agent beat the basic heuristic in the first controlled run:

- 30 duplicate deals, replayed after swapping the teams;
- 60 games total;
- probabilistic-agent score: 86.67% of game points;
- 95% interval: 75.83% to 93.09%;
- average paired advantage: 2.97 half-suits.

This is strong preliminary evidence, but not the final size of the benefit. The
agents differed in claim behavior as well as belief tracking, and 30 deal pairs
is still a modest experiment.

**Human translation:** do not merely remember who asked for a card. Convert each
question into constraints:

- A normal legal ask proves the asker has another card in that half-suit.
- A failed ask proves the target did not have that card at that moment.
- A successful ask makes the new owner public.
- Later transfers can change ownership, so update the fact instead of preserving
  an obsolete location forever.

### 2. Obviously unsafe claims lose badly

The basic heuristic won all 200 team-swapped games against the deliberately weak
random claimer. Its 95% lower confidence bound was 98.12%, and its paired margin
was 6.13 half-suits.

This comparison is intentionally easy; it validates the rules and evaluation
framework more than it reveals expert strategy.

**Human translation:** a claim requires two separate beliefs:

1. your team owns all six cards;
2. you know the exact teammate holding each card.

Being sure of the first is not enough. Under the baseline rules, a wrong
within-team distribution makes the half-suit null, and an opposing card awards
the set to the opponents.

### 3. Legal games can cycle

Heuristic and belief agents sometimes entered long ask cycles without acquiring
enough information to make a confident claim. For reproducible tournaments, the
current baseline makes a documented speculative claim after 256 public actions
without a resolved set.

**Human translation:** a Fish position can become strategically stuck even when
questions remain legal. A completed, accurately known half-suit can be valuable
as a turn-transfer or “stalemate breaker,” depending on the house rule. Do not
confuse delaying a safe claim for strategic control with delaying because the
distribution is uncertain.

## Practical decision process for every turn

### Step 1: Update the ownership ledger

For every unresolved card, maintain:

- players who definitely cannot have it;
- the last definitely known owner, if any;
- players who have publicly shown participation in its half-suit;
- whether a later transfer invalidated an older conclusion;
- current hand sizes, which constrain all remaining possibilities together.

Exact hand sizes matter because card locations are correlated. If one player must
hold a card, that consumes one of their remaining slots and changes the
probabilities of every other unknown card.

### Step 2: Identify safe claims before asking

A safe claim needs the exact six-card allocation. State it card by card. If your
rules let a successful claimant choose the next teammate, include the value of
that turn transfer in the claim decision.

Do not claim merely because all six cards “feel like” they are on your team.

### Step 3: Score each possible ask three ways

For `ASK opponent X for card C`, consider:

- **Acquisition:** how likely is X to hold C?
- **Information:** how much will yes or no reduce uncertainty for your team?
- **Failure destination:** what can X do if the answer is no and X receives the
  turn?

An opponent with a dangerous, nearly completed half-suit can be a bad target even
when they are the most likely holder. A failed question may unlock their hand.

### Step 4: Prefer questions your teammates can interpret

Every legal normal question publicly says that you participate in the requested
half-suit and do not already own the requested card. That can help teammates, but
it also helps opponents.

Before revealing a new half-suit, ask whether the immediate card chance and team
signal are worth exposing your participation.

### Step 5: Re-evaluate after every answer

Do not plan a whole sequence as though the first answer is guaranteed. A success
retains the turn and changes ownership; a failure transfers control and creates a
new hard exclusion. Recompute.

## Strong hypotheses that still need larger experiments

These are research questions, not proven rules:

- Information-gain questions may beat the highest-probability card grab in some
  early and middle-game positions.
- Giving the turn to the wrong opponent can cost more than the expected value of
  the requested card.
- Players with few cards are more concentrated targets, but a failed ask against
  them may be especially dangerous.
- Delaying a completely known half-suit may be valuable when it can later move
  the turn to a teammate.
- The 8/Joker half-suit may play differently because the four 8s have a shared
  visible rank while `JK1` and `JK2` are unique askable identities. No simulation
  has yet demonstrated a reliable difference.
- The correct claim-confidence threshold should change with score, remaining
  sets, null-set rules, and who receives the turn afterward.

## What has not been discovered yet

The project does not yet have enough strong-search games to claim:

- an optimal opening question;
- a solved claim probability threshold;
- a proven Joker/8 strategy;
- a calibrated win probability for arbitrary positions;
- an emergent optimal teammate signalling convention;
- Stockfish-level or game-theoretically near-optimal play.

The current search agent is a sampled hidden-world retained-turn baseline. It is
useful for analyzing a position, but its Python implementation is far too slow
for millions of full search-vs-search games. Those discoveries require shared-
tree ISMCTS, faster incremental beliefs, batched inference, and a larger league.

## Evidence standard for future additions

A strategy moves into the “demonstrated” section only when it has:

- identical deals replayed with policies swapped;
- seat rotation;
- a recorded seed and configuration;
- enough games for a meaningful uncertainty interval;
- an ablation isolating the strategy from unrelated policy differences.

Until then, it remains a hypothesis rather than advice presented as fact.
