# Beating the Canadian-Fish-Demo bots

`github.com/MeagerPotato/Canadian-Fish-Demo` at `822776646bbfc0c7ef6df1aacac9924cbf50bced`.

## Their game is a configuration ours already supports

Read off `lib/engine/reduce.ts` rather than from any prose:

* **48 cards**, 8 books of 6, 6 seats of 8, teams by seat parity
* a miss passes the turn to the target; a hit keeps it
* you must hold a card of the book and may not ask for a card you hold
* a claim names only your own team's seats
* claim resolution is **three-way**: any card with an opponent → the
  **opponents** score it; all on your team and the split right → you score it;
  all on your team and the split wrong → **void**, nobody scores

That last rule is `wrong_distribution_outcome="null"` in our `RuleConfig`, term
for term with `fish/engine.py::_apply_claim`, and `variant="48"` gives the eight
half-suits. **`RuleConfig(variant="48", wrong_distribution_outcome="null")` is
their game** — a configuration this project already supported and used as its
default through the v0.4 era.

It also makes claiming *cheaper* than in our usual rules: a wrong split voids
(−1 against what you would have won) instead of gifting the book (−2). Our
`ClaimEvaluator.forced_claim()` already reads the variant off the observation
and prices both, so nothing had to be retuned for this.

## The duel runs inside THEIR engine

`their_harness/kraken_vs_mp.ts` copies the loop and the seeding from their own
`scripts/simulate-main.ts`: seats 0/2/4 = team A, 1/3/5 = team B, seeds
`sim-{pairing}-{i}`, starting seat rotating `i % 6`, `decide()` seeded
`hash(seed:moveIndex)`. Their `reduce` arbitrates, their `seatView` projects,
their `decide` plays one team. Ours plays the other through `serve.py`.

**Their bot is not bridged at all.** It reads `seatView(state, seat)` straight
from its own engine; both sides receive the identical object from the identical
function, and `bridge.to_observation` consumes only its fields. So their side
cannot be handicapped by anything here, and any error in the bridge
disadvantages **us**.

That is the point of the arrangement. A previous cross-engine bridge in this
project handed the foreign bot a subtly wrong view for weeks, was worth
**+3.0833** sets a game to us, and invalidated a published headline. Running
inside the opponent's own arbiter removes the entire class of error.

Two further guards: the card map is dumped from **their** `ALL_BOOKS` /
`bookCards` / `cardBook` into `cards.json` and asserted against our own
`card // 6` half-suit rule for all 48 cards before a game is played; and their
reducer rejects any malformed action, so **zero illegal actions over a run is
the bridge's self-test** and a broken translation cannot hide.

## One real rule difference, and how it is translated

Their `endgame` phase keeps the turn with the claiming seat, which claims the
remaining books one at a time — even holding no cards itself, since its
teammates hold them. Our engine's rule for a cardless seat whose teammate has
cards is that it **must pass**, and `reducePass` refuses a pass outside
`awaitPass`. The first power run aborted two sides on exactly that.

`bridge.endgame_claim` translates the trigger using **our own machinery** —
`ClaimEvaluator` with the agent's own configuration, then `voluntary_claim()`
or `forced_claim()`, which is the method our engine uses in this position and
the same concept their bot reaches for (`forcedClaim`). The policy stays ours;
only the choice of *when a claim is required* is translated.

Their `awaitDesignate` has no analogue in our engine at all, so that one **is**
bridge logic and is labelled as such in `bridge.designate`: the acting team is
out of cards and the remaining books go to the opponents either way, so it
names the opponent with the fewest cards, deterministically.

## Result

`results/mp_duel_hard_report.json`, 800 games, 400 per seat parity:

| | |
|---|---:|
| book margin a game | **+1.7700** [+1.6062, +1.9312] |
| books: ours / theirs | 4.731 / 2.961 (of 8) |
| wins / losses / ties | 531 / 108 / 161 |
| win rate, all games | 0.6637 [0.6300, 0.6963] |
| **win rate, decided games** | **0.8310** |
| illegal actions / errors / capped | 0 / 0 / 0 |

And `results/mp_duel_medium_report.json`, 500 games: **+2.3640** [+2.1420,
+2.5800] a game, 0.8857 of decided games, books 5.028 / 2.664.

The whole ladder, their three tiers measured by their own harness unmodified,
plus ours measured in it:

| pairing | win rate of decided games |
|---|---:|
| their `hard` vs their `medium` | 0.585 |
| their `hard` vs their `easy` | 1.000 (200–0) |
| their `medium` vs their `easy` | 1.000 (200–0) |
| **KRAKEN vs their `medium`** | **0.886** |
| **KRAKEN vs their `hard`** | **0.831** |

KRAKEN takes more off their `hard` than their `hard` takes off their `medium` —
a wider gap than a full tier of theirs.

Intervals are 2,000 bootstrap replicates over games. Games are independent by
construction here (fresh seed, fresh deal, and the two seat parities run as
separate games), so the game is the resampling unit and no clustering is
needed — unlike this project's own duels, which pair within a deal.

**What this is not.** Their bot is a constraint-propagation heuristic with
candidate sets and at-least-one-of constraints; ours runs exact combinatorial
inference over a sampled posterior with lookahead. That a much heavier engine
wins is not a surprise and is not presented as one. What the run establishes is
that it wins *by this much*, under their rules, in their arbiter, on
information that is symmetric by construction.
