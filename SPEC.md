# Fish Engine - Game Specification

Formal specification of Literature (Fish / Canadian Fish) as implemented by
this engine. Reference: https://en.wikipedia.org/wiki/Literature_(card_game).
Baseline rules follow the Wikipedia description; deviations and house rules
are explicit `RuleConfig` options.

## 1. Players and teams

- 6 players, seated in a circle, ids `0..5`.
- Team A = players {0, 2, 4}; Team B = players {1, 3, 5} (alternating seats).
- Clockwise order is ascending player id (mod 6).

## 2. Deck variants

Cards have stable integer ids. `card_id // 6` is the half-suit index;
`card_id % 6` is the position within the half-suit.

### Half-suit table (suit order: Clubs=0, Diamonds=1, Hearts=2, Spades=3)

| HS idx | Name          | Cards (position 0..5)      |
|--------|---------------|----------------------------|
| 0      | Low Clubs     | 2C 3C 4C 5C 6C 7C          |
| 1      | Low Diamonds  | 2D 3D 4D 5D 6D 7D          |
| 2      | Low Hearts    | 2H 3H 4H 5H 6H 7H          |
| 3      | Low Spades    | 2S 3S 4S 5S 6S 7S          |
| 4      | High Clubs    | 9C TC JC QC KC AC          |
| 5      | High Diamonds | 9D TD JD QD KD AD          |
| 6      | High Hearts   | 9H TH JH QH KH AH          |
| 7      | High Spades   | 9S TS JS QS KS AS          |
| 8      | Specials      | 8C 8D 8H 8S RJ BJ          |

- **48-card variant** (`variant="48"`): half-suits 0-7 only, 8 cards each.
- **54-card variant** (`variant="54"`, DEFAULT): all 9 half-suits, 9 cards
  each. The two jokers are distinct and colored: `RJ` is the **Red Joker**
  and `BJ` the **Black Joker**. They are individually askable, so a player
  can ask specifically for the red one or the black one. Name aliases
  (`X1`/`X2`, `joker1`/`joker2`, `red`/`black`) are accepted by the parser.
  The Specials half-suit behaves identically to every other half-suit for
  asking and claiming.

## 3. Deal

All cards are dealt evenly (8 or 9 each). The starting player is
`RuleConfig.starting_player` (default 0; evaluation harnesses rotate it).

## 4. Turn structure and actions

The player to move takes exactly one action.

### 4.1 ASK(target, card)

Legal iff ALL of:
1. `target` is on the opposing team and is a valid player id.
2. `target` holds at least one card (public knowledge via hand counts).
3. The asker holds at least one card of `card`'s half-suit.
4. The asker does not hold `card` itself (unless `allow_bluff_asks=True`).
5. `card`'s half-suit is unresolved.
6. The asker holds at least one card (a cardless player cannot ask).

Resolution:
- If target holds `card`: the card transfers to the asker **publicly**
  (everyone sees which card). The asker retains the turn.
- Otherwise: no transfer, and the **target** receives the turn.

### 4.2 CLAIM(half_suit, assignment)

`assignment` maps each of the 6 cards of `half_suit` to a member of the
**claimant's team** (the claimant may assign cards to themself; a teammate
may be assigned zero cards). Any length-6 sequence of valid team member ids
is accepted, and is compared as a tuple.

Legal iff:
1. `half_suit` is unresolved.
2. It is the claimant's turn, OR `claims_any_time=True` (baseline: own turn).
3. Every declared holder is a valid id on the claimant's team.

Resolution (all 6 actual locations become **public**, since players show
those cards):
- **Exact match** of declared assignment vs actual holdings: the claiming
  team scores the half-suit.
- Else, if **any** of the 6 cards is held by the opposing team: the opposing
  team scores it.
- Else (all 6 within the claiming team but the split was declared wrong):
  `wrong_distribution_outcome` applies, `"null"` (baseline; nobody scores)
  or `"opponent"`.

All 6 cards leave every hand. The turn does not change as a result of the
claim itself (see 4.4 for empty-hand consequences).

### 4.3 PASS(teammate)

Required when the player to move has no cards. Legal iff `teammate` is a
valid id on the same team and holds at least one card. (Wikipedia: a player
emptied by their own claim passes to any teammate with cards. We generalize:
any on-move cardless player passes. This only arises via claims or the
endgame, because a failed ask never lands on a cardless target and a
successful ask keeps the turn with the asker, who just gained a card.)

### 4.4 Turn and endgame edge rules

- If the player to move has no cards and **no teammate** has cards, the turn
  passes to the next opponent clockwise who has cards. (Their team
  necessarily holds all remaining cards, so play continues as forced claims.)
- If the player to move has cards but **no opponent** has cards, no ASK is
  legal and the player must CLAIM. Claims still resolve normally, so a
  mis-declared split can still null a set.
- The game ends when all half-suits are resolved. Final score is
  (team A sets, team B sets, null sets), summing to 8 or 9. Higher set count
  wins; equal is a tie.

### 4.5 Termination is not guaranteed by the rules

Nothing in the rules forces progress: two opponents can trade a card back
and forth forever, so the state graph is **cyclic** and a game can in
principle continue indefinitely. This is a genuine property of Literature,
confirmed by the exact solver. Agents therefore carry a progress rule (claim
when no half-suit has resolved within a window), and harnesses impose an
action cap. Any claim that "every game terminates" is a property of the
agents, not of the rules.

## 5. Public information (the observation boundary)

An agent acting as player `p` may see ONLY:
- Its own current hand.
- The full public event log: every ASK (asker, target, card, success), every
  CLAIM (claimant, half-suit, declared assignment, outcome, and the revealed
  actual locations of all 6 cards), every PASS.
- All players' current hand counts, resolved half-suits and scores, whose
  turn it is, and the rule configuration.

**Nothing else.** The engine's true state is never handed to a policy.
Training may use ground truth (the value network is trained on true states);
acting may not.

Agent RNG seeds are drawn from a stream independent of the deal, so agent
randomness cannot encode the hidden layout.

Key soundness fact the belief engine exploits: *every card movement is
public*. Therefore the current location of any card is a deterministic
function of the **initial deal** and the public log, and all hidden-state
inference reduces to constraints on the initial deal.

## 6. RuleConfig options (baseline value first)

| Option | Baseline | Alternatives |
|---|---|---|
| `variant` | `"54"` | `"48"` |
| `claims_any_time` | `False` (own turn only) | `True` |
| `allow_bluff_asks` | `False` | `True` (may ask for a held card) |
| `wrong_distribution_outcome` | `"null"` | `"opponent"` |
| `mandatory_claim_known` | `False` | `True` (reserved; not yet enforced) |
| `starting_player` | `0` | any id / harness-randomized |

## 7. Invariants (checked in tests and in debug mode)

1. Every unresolved card is in exactly one hand; resolved cards are in none.
2. `sum(hand sizes) + 6 * resolved sets == deck size` at all times.
3. Transfers conserve cards; a transfer moves exactly the asked card.
4. No action is ever applied that violates section 4 legality; illegal
   actions raise `IllegalAction` rather than corrupting state.
5. Score A + score B + nulls == resolved half-suits; at game end == total.
6. The turn holder is always a valid player id.
7. Observations contain no information beyond section 5 (proved by
   replay-reconstruction tests).
