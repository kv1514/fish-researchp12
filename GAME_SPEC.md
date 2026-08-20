# Literature / Fish Game Specification

Status: normative simulator specification, version 0.1 (2026-08-20).

This document formalizes the six-player game implemented by the engine. Statements marked **Sourced rule** summarize published rules. Statements marked **Engine decision** resolve omissions or contradictions so that every game transition is deterministic. The project request takes precedence where it deliberately defines the 54-card variant or observable information.

## 1. Sources and precedence

1. **Project requirements**: six players, fixed teams, both the 48-card game and the 54-card main variant, exact ask and claim consequences, information-integrity requirements, and configurable house rules.
2. John McLeod, [“Literature” at Pagat](https://www.pagat.com/quartet/literature.html), especially *Players and Cards*, *Questions*, *Claiming*, *Public information*, *Endgame*, and *Variations*. This is the detailed source on which Wikipedia says its rule description is based.
3. [Wikipedia, “Literature (card game)”](https://en.wikipedia.org/wiki/Literature_%28card_game%29), the requested concise reference.
4. Mike Develin, [“Canadian Fish”](https://www.bantha.org/~develin/cardgames.html#9), used only to document alternate house rules where it conflicts with the baseline.

Published rules are not completely uniform. In particular, Pagat/Wikipedia permit a claim on the claimant's turn and make an incorrect within-team distribution a null set; Develin permits declarations at any time and awards any incorrect declaration to the other team. The default profile below follows the project request and Pagat/Wikipedia. Develin-like behavior is opt-in.

## 2. Terminology and mathematical model

- Players are `P = {0,1,2,3,4,5}` in alternating seats.
- `team(p) = A` for `p in {0,2,4}` and `B` for `p in {1,3,5}`. `mates(p)` includes `p` and the other two members of `team(p)`; `opponents(p)` contains the other three players.
- A **card** is a globally unique identifier. A **half-suit**, also called a book or set in the sources, is a fixed set of six card identifiers.
- A half-suit is exactly one of `UNRESOLVED`, `WON_A`, `WON_B`, or `NULL`. Won and null half-suits are collectively **resolved**.
- While a half-suit is unresolved, every one of its cards has exactly one current owner in `P`. When resolved, all six cards are removed from hands and their terminal ownership is retained only in the public record.
- `turn` is the player who controls the next ordinary action. `phase` is `PLAY`, `FORCED_CLAIMS`, or `TERMINAL`.
- An **ordinary action** is `ASK(target, card)` or `CLAIM(half_suit, assignment[, successor])`. Administrative choices required by a transition, such as selecting a successor, are modeled explicitly and are not policy-free hidden decisions.

The complete environment state contains the rules configuration, phase, exact hands, resolved-half-suit ledger, score, turn/forced claimer, public event log, initial-deal metadata, and deterministic RNG state. Only an observation projection of this state may be given to a playing policy (Section 10).

## 3. Deck profiles and deal

### 3.1 Baseline 48-card profile: `standard_48`

**Sourced rule.** Remove all four 8s from a standard 52-card deck. For each suit `C,D,H,S`, create:

- low half-suit: ranks `2,3,4,5,6,7`;
- high half-suit: ranks `9,10,J,Q,K,A`.

This is 8 half-suits, 48 unique cards. Deal every player 8 cards.

### 3.2 Main 54-card profile: `eights_jokers_54`

**Sourced variation plus project definition.** Use all 52 standard cards plus two distinct jokers. The eight low/high half-suits are unchanged. Add:

- `EIGHTS_JOKERS = {8C, 8D, 8H, 8S, JOKER_1, JOKER_2}`.

The jokers are not interchangeable: they are separate askable and assignable card identifiers. This is 9 half-suits, 54 cards, and 9 cards per player. `EIGHTS_JOKERS` obeys exactly the same ask, claim, resolution, and scoring rules as every other half-suit.

### 3.3 Deal procedure

**Sourced rule.** Shuffle and deal all cards singly and face down; players may see only their own hands. Pagat makes the dealer the first player, while Wikipedia says this is usual and documents other opening-player customs.

**Engine decisions.** A deal is a uniformly shuffled permutation generated from an explicit seed, distributed round-robin beginning left of the configured dealer. The dealer is the default first player. Tests and duplicate evaluation may inject a complete valid deal and a first player. The seed, shuffle permutation, other hands, and injected deal are privileged environment data and are never part of a policy observation. A valid initial state has the required number of cards per player, no duplicates or omissions, every half-suit unresolved, score `0-0`, no nulls, and phase `PLAY`.

## 4. ASK action

### 4.1 Legality

In `PLAY`, `ASK(a,t,c)` is legal if and only if all of the following hold at the moment of action:

1. `a == turn` and `hand[a]` is nonempty.
2. `team(t) != team(a)`.
3. `hand[t]` is nonempty.
4. Card `c` belongs to an unresolved half-suit `h`.
5. `a` owns at least one card in `h`.
6. Under the default `allow_owned_card_bluff = false`, `c not in hand[a]`. If that option is true, this last restriction is removed; the requested card itself may be the card satisfying condition 5.

Conditions 2–6 are the sourced question restrictions; the project explicitly requires the target to be an opponent and nonempty. Asking is mandatory when the actor ends an ordinary turn still able to play: a player may make zero or more claims allowed by the timing profile, but cannot voluntarily pass instead of asking.

### 4.2 Resolution and turn transition

- If `c in hand[t]`, transfer that one card from `t` to `a`, publish success and the card identity, and keep `turn = a`.
- Otherwise transfer nothing, publish failure, and set `turn = t`.

These are atomic transitions. A target who gives away their last card becomes inactive, but the successful asker still retains the turn. A failed ask cannot target an empty player, so its successor is always able to act at the instant of the answer.

**Owned-card bluff decision.** With `allow_owned_card_bluff = true`, a request for the uniquely owned card necessarily fails; the asker keeps the card and the target receives the turn. This follows Pagat's “bluff without penalty” variation. The separate Pagat variation in which the asker surrenders that card is not the default but may be represented by a distinct `owned_ask_result = SURRENDER_TO_TARGET` option if implemented.

## 5. CLAIM action

### 5.1 Claim payload and structural legality

`CLAIM(a,h,M)` contains claimant `a`, one unresolved half-suit `h`, and a total assignment `M` from each of the six distinct cards in `h` to exactly one player on `team(a)`.

It is structurally legal only if:

- claim timing permits `a` to claim now (Section 7);
- `h` is unresolved;
- `M` has exactly the six cards of `h`, with no missing, extra, or duplicate card;
- every assigned player is one of the claimant's three teammates (including the claimant).

Empty shares are allowed. A claimant need not hold any card of `h`. Claim legality does not depend on whether the prediction is correct and therefore must not leak true ownership.

### 5.2 Resolution

Let `O(c)` be the true owner immediately before resolution.

1. If any `c in h` is held by the opposing team, resolve `h` as won by the opposing team.
2. Otherwise the claimant's team owns all six. If `M(c) == O(c)` for every card, resolve `h` as won by the claimant's team.
3. Otherwise the claimant's team owns all six but the distribution is wrong. Under the baseline, resolve `h` as `NULL`; neither team scores it.

In every outcome, reveal the six pre-resolution owners, remove all six cards from all hands, resolve the half-suit exactly once, update the ledger, and publish the declared assignment, actual assignment, and outcome. Claiming never transfers cards between hands.

The baseline consequences are stated by Pagat and Wikipedia and required by the project. `own_team_misdistribution = AWARD_OPPONENT` selects the Develin/Pagat-house-rule alternative for case 3.

### 5.3 Post-claim control

Under baseline `post_claim_control = CONTINUE_TURN`, the current turn is unchanged after any claim while its current player still has cards. Therefore a claimant may make another legal claim and eventually must ask. If resolution empties the current player's hand, apply Section 8.1. Claim outcome does not otherwise determine turn control.

With `post_claim_control = CLAIMANT_SELECTS_TEAMMATE_ON_SUCCESS`, a successful claim additionally carries or triggers a public selection of any nonempty member of the claimant's team, including the claimant, who becomes `turn`. If none exists, enter the whole-team-empty transition. Failed or null claims leave turn control as in the baseline. This option formalizes the requested house rule and Pagat/Wikipedia's related “team chooses who asks next” variation; the engine assigns the choice specifically to the claimant.

## 6. Default rules profile

The normative Wikipedia-like engine profile is:

| Option | Default | Meaning |
|---|---:|---|
| `deck_profile` | `eights_jokers_54` for primary experiments; `standard_48` supported | Section 3 |
| `claim_timing` | `ON_TURN` | Only the current player may claim |
| `mandatory_personal_claim` | `false` | A personally complete half-suit may be retained |
| `post_claim_control` | `CONTINUE_TURN` | Section 5.3 |
| `allow_owned_card_bluff` | `false` | Asking for a card in one's hand is illegal |
| `own_team_misdistribution` | `NULL` | Wrong location, right team, scores for neither team |
| `invalid_action_policy` | `REJECT_NO_MUTATION` | Section 9 |
| `memory_model` | `PERFECT_RECALL_PUBLIC_EVENTS` | Section 10 |
| `opening_player` | dealer | Configurable/injectable |

The baseline ruleset name refers to behavior, not deck size: both deck profiles can run with these same defaults.

## 7. Claim timing and mandatory-claim options

### 7.1 `claim_timing`

- `ON_TURN` (baseline): only `turn` may claim during `PLAY`. This matches Pagat's operative rule and Wikipedia. The phrase “at any turn” in Pagat means on any of that player's turns; Pagat separately labels claiming when it is not one's turn as a variation and specifies a penalty for the irregularity.
- `ANY_TIME`: any player allowed by the empty-player option may interrupt between atomic actions to claim. The claim is fully resolved before play resumes. Except for a configured successful-claim transfer or an emptied current actor, the pre-claim `turn` remains unchanged. Simultaneous interrupts are serialized by the environment's received-action order; self-play environments should expose a deterministic interrupt window rather than use wall-clock races.

By default, a player with no cards cannot claim. An optional `empty_player_claims = true` is meaningful only with `ANY_TIME` and follows Pagat's variation; the claimant still may not see teammates' cards.

### 7.2 Mandatory immediate claims

**Sourced rule/engine definition.** The published variation requires a player to declare a book as soon as that player personally holds all six cards. It does not define an objective requirement based on what a player “knows” about a distributed team holding.

With `mandatory_personal_claim = true`, at every stable decision boundary, if an eligible player personally holds all six cards of one or more unresolved half-suits, their only permitted ordinary action is a correct claim for one such half-suit; repeat until none remains. If several exist, the player chooses the order. Under `ON_TURN`, this is enforced when that player controls the turn. Under `ANY_TIME`, mandatory claims are resolved in deterministic seat order starting at `turn` before voluntary actions.

The engine does **not** implement “must claim whenever the policy is certain that the team has the set”: internal knowledge is not an observable game-state predicate and inspecting it would couple legality to an agent implementation or leak hidden state.

## 8. Empty hands, endgame, and termination

### 8.1 Individual empty hand

**Sourced rule.** A zero-card player drops out and cannot be asked. If the current player loses all remaining cards because of a claim, that player chooses a teammate who still has cards to receive the turn.

**Engine decisions.** “Drops out” means only that ASK actions by or against that player are unavailable; public observation and any permitted out-of-turn claim participation remain governed by configuration. If claim resolution empties `turn` and the same team still has cards, the environment requires `SELECT_SUCCESSOR(p)` from the player who just held the turn, choosing a nonempty teammate, then sets `turn = p`. This public choice is part of the action history. If exactly one teammate is nonempty, selection is automatic but still logged. If the current player is emptied by another player's `ANY_TIME` claim, the current player—not the interrupting claimant—makes the baseline selection.

### 8.2 Whole-team-empty forced-claim phase

When all three players of one team have zero cards and unresolved half-suits remain, all unresolved cards necessarily belong to the other team. No further ASK is legal. Enter `FORCED_CLAIMS`:

- If `turn` belongs to the team that still has cards, `forced_claimer = turn`.
- If `turn` belongs to the empty team, that player publicly selects one nonempty opponent, who becomes `forced_claimer`.
- The forced claimer alone must resolve every remaining half-suit, sequentially, without consulting teammates. Only structurally legal CLAIM actions are available; no ask, pass, or teammate substitution is allowed.
- The forced claimer may continue declaring even after their own hand becomes empty. This is an **engine decision** needed to make “that player must make the remaining claims” total and deterministic; forced-claim authority is a role, not ordinary active-player status.
- Each claim uses the normal outcome rules, so a wrong own-team distribution becomes null in the baseline or goes to the opponent under the configured alternative. Continue until no half-suit is unresolved.

This adopts the specific Pagat/Wikipedia endgame procedure. Pagat also documents a different forced-claim rotation/pass system as a house rule; that is not baseline.

### 8.3 Other endgame edge cases

- If claim resolution leaves no unresolved half-suit, go directly to `TERMINAL`; no successor selection is required.
- If all active cards disappear but an unresolved half-suit exists, the state is corrupt: an unresolved half-suit must own six active cards.
- A normal actor with cards can have no legal ASK even while opponents hold cards: for example, every half-suit represented in the actor's hand may be wholly owned by the actor's team. Passing is still unavailable. The actor must make a structurally legal claim (possibly an uncertain distribution claim), after which ordinary control rules apply. While any half-suit is unresolved, at least one structurally legal claim payload exists, so this is not a rules deadlock.
- Multiple claims can resolve the last several half-suits without an intervening ask.

### 8.4 Result

The game terminates if and only if all half-suits are resolved. Team score is the count of half-suits it won; null sets score zero. The higher score wins. The 48-card profile can tie `4-4`; the 54-card profile normally cannot tie, but null sets make ties possible. Report `A_WIN`, `B_WIN`, or `TIE` from score comparison, not from card count.

## 9. Invalid actions and house-rule boundaries

Human sources prescribe group adjudication for many irregularities, and another description assigns penalties. Those procedures are unsuitable as an implicit simulator rule.

**Engine decision.** With baseline `REJECT_NO_MUTATION`, an invalid action returns a structured legality error and leaves hands, history, turn, RNG, score, and phase unchanged. Training action masks should prevent invalid choices; tests should submit them deliberately. Optional penalty profiles must be named and separately tested. In particular, “bluff asking” must be enabled explicitly and is not an invalid-action penalty.

No prearranged or secret communication channel exists. Teammates may coordinate only through actions and facts in their legal observations. The engine does not attempt to prohibit emergent public conventions: unlike a human social rule, that is not mechanically distinguishable from learned strategy.

## 10. Observations and information integrity

### 10.1 Policy observation

For viewer `v`, the policy-facing observation may contain only:

- viewer identity and team, public rules configuration, deck/half-suit definitions;
- the exact current cards in `hand[v]` and its own private hand history;
- current `phase`, `turn` or public forced claimer, and pending public selection state;
- exact current hand counts for all six players;
- the complete public event history: asks, target, requested card, success/failure, face-up transfers, claim declarations, revealed true claim distributions, outcomes, successor selections, and turn changes;
- the resolution state of every half-suit, scores, and null count;
- a legal-action description/mask computed solely from this observation and the acting player's own hand.

The project explicitly permits public action history. This models perfect recall: although Pagat forbids written records and lets players ask aloud only about the immediately preceding question, every ask and answer was public when made and a human may remember it. Alternative bounded-memory agents must forget internally; the environment must not erase public truth differently for different policy classes.

### 10.2 Data that must never reach an acting policy

- any other player's current or initial hand;
- the shuffled deck/permutation, deal seed, RNG state, or an identifier from which the deal can be reconstructed;
- unobserved current owner maps, sampled “true world” labels, future actions, or future random values;
- claim adjudication data before the claim has been committed;
- centralized-critic tensors, training targets, privileged replay fields, debug state, or handles/references through which these can be reached.

The environment may retain privileged state and a centralized critic may receive it during training, but the deployed action-selection policy has a separate typed input and call path. Search determinization samples worlds from the observation/belief state; it must not initialize simulations from the live hidden deal.

### 10.3 Information implied by public events

- A legal non-bluff ask proves that, immediately before the ask, the asker had at least one *other* card in the requested half-suit and did not have the requested card.
- With owned-card bluffing enabled, an ask no longer proves the second fact: the requested card itself may be the asker's only card in that half-suit.
- A successful ask makes the requested card's post-action owner known: the asker. A failed ask proves the target did not own it at that instant.
- Card movement after those facts can invalidate a naive current-owner conclusion, so beliefs must replay transfers and constraints temporally.
- Every resolved claim reveals all six pre-resolution owners and then removes those cards. Hand-count changes are public.

These are deductions available to agents, not extra privileged observation fields.

### 10.4 Integrity tests required

1. **Indistinguishability:** two true states with the same viewer hand and public history must serialize to byte-identical observations and legal ASK masks for that viewer.
2. **Permutation test:** permuting hidden cards among opponents while preserving counts/public constraints must not change the viewer observation before new public evidence.
3. **No-reference test:** mutating an observation or policy-owned buffer cannot mutate or expose environment hands; observations are immutable copies/isolated tensors.
4. **Seed canary:** deal seed, deck order, privileged IDs, and other hands cannot be found by recursive schema/serialization inspection.
5. **Claim mask test:** availability of a structurally legal claim is independent of its hidden correctness.
6. **Policy signature test:** production policies accept only the observation type, never `GameState`; privileged critics use a visibly separate interface.
7. **Search test:** search results are invariant to swapping hidden live deals that yield the same information state when the search RNG seed is fixed.

## 11. Public event semantics

Each accepted action appends enough information to replay the public game without the hidden deal. Recommended atomic events are:

- `GAME_STARTED(profile, dealer, first_player, initial_counts)` — never includes seed or hands;
- `ASKED(actor, target, card)` then `ASK_RESULT(success[, transferred_card])`;
- `CLAIMED(claimant, half_suit, predicted_assignment)` then `CLAIM_RESOLVED(actual_assignment, outcome)`;
- `HAND_EMPTIED(player, reason)`, `SUCCESSOR_SELECTED(selector, successor, reason)`;
- `FORCED_CLAIMS_STARTED(empty_team, selector, forced_claimer)`;
- `TURN_SET(player, reason)` and `GAME_ENDED(score_A, score_B, null_count, result)`.

Events are immutable and totally ordered. Ask/claim commitment and resolution are atomic from the next policy's point of view. Detailed research logs may additionally store the privileged deal, seed, beliefs, or training targets, but those fields belong to a separate record not accepted by policy inference.

## 12. State invariants

Check after initialization and after every accepted atomic transition in debug/property-test builds:

1. Every card belongs to exactly one configured half-suit; every half-suit contains exactly six unique cards.
2. Every card of every unresolved half-suit appears in exactly one player hand. No card of a resolved half-suit appears in any hand.
3. Hands are pairwise disjoint and contain only configured cards.
4. `sum(hand sizes) + 6 * resolved_count == deck_size`.
5. `won_A + won_B + null_count + unresolved_count == total_half_suits`.
6. Scores equal won-half-suit counts under unit scoring.
7. An ASK transfers exactly one card on success and zero on failure; all unrelated ownership is unchanged.
8. A CLAIM removes exactly the six cards of one previously unresolved half-suit and resolves it exactly once.
9. Every accepted ASK and CLAIM satisfies structural legality using only pre-action state; rejected actions cause no mutation.
10. In `PLAY`, `turn` has a card unless an explicit successor/forced-claim administrative choice is pending.
11. ASK success retains the asker; ASK failure transfers turn to the nonempty target.
12. In `FORCED_CLAIMS`, exactly one forced claimer exists, at least one half-suit is unresolved, no ASK is legal, and all unresolved cards belong to one team.
13. `TERMINAL` if and only if `unresolved_count == 0`; no action is legal in `TERMINAL`.
14. The public event log and hand-count deltas agree with the hidden transition.
15. Policy observations satisfy all noninterference tests in Section 10.4.

## 13. Conformance examples

### 13.1 Successful and failed asks

If P0 owns `2H`, asks nonempty opponent P3 for `6H`, and P3 owns it, the card moves P3→P0 and P0 acts again. If P3 lacks it, no card moves and P3 acts next. P0 could not make the ask without another low heart, could not target P2/P4, and under baseline could not already own `6H`.

### 13.2 Distributed claim

P0 declares low spades as `{2S,4S}->P0`, `{3S}->P2`, `{5S,6S,7S}->P4`.

- Exact actual match: Team A wins the book.
- Any actual owner is P1/P3/P5: Team B wins it.
- Team A owns all six but any A-player assignment differs: book is `NULL` in baseline.

All six actual owners become public and all low spades leave hands in every case.

### 13.3 Main variant

If P2 owns `8D`, P2 may ask a nonempty opponent for `JOKER_2`, `JOKER_1`, or any other card in `EIGHTS_JOKERS` that P2 does not own. Owning a low/high diamond does not authorize an `EIGHTS_JOKERS` ask. The two jokers must be named and assigned separately in claims.

## 14. Explicit non-baseline/undecided extensions

The following source variants are outside the initial normative profile and require their own configuration plus tests if implemented: eight-player teams; removing ranks other than 8; four-of-a-rank books; weighted high-book scoring; penalties that surrender an illegally requested card; hidden hand counts; forced-claim rotations/passes/challenges; and any out-of-turn race protocol other than deterministic interrupt windows.

No rules source specifies timing limits, policy timeouts, repetition draws, or a repetition penalty. Pathological policies can repeat failed asks forever without transferring or resolving a card, so termination is not guaranteed by the rules alone. A harness may impose an explicit `max_actions` and return `TRUNCATED` (not `TERMINAL`, a win, or a rules-level draw); training code must state how truncated episodes are valued or bootstrapped. Ordinary conformance tests should use terminating agents, while fuzz tests should treat reaching their cap as a diagnostic rather than silently inventing a winner.
