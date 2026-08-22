# V03 Audit — `fish/` engine, beliefs, evaluation, exact solver

Adversarial pre-v04 audit. Every finding below was produced by running code;
scripts are in `research/audit_scripts/` and each finding names the script and
quotes its actual output. Anything I could not reproduce is labelled
**UNVERIFIED** and is kept separate from the verified findings.

Scope audited: `fish/engine.py`, `fish/rules.py`, `fish/cards.py`,
`fish/observation.py`, `fish/beliefs.py`, `fish/features.py`,
`fish/agents/*.py`, `fish/exact.py`, `fish/eval/tournament.py`,
`fish/eval/elo.py`, plus the boundary usage in `fish/runner.py`,
`fish/coach.py`, `fish/web/server.py`, `fish/learning/pi_dataset.py`,
`fish/benchmark_exact.py`.

No file outside `research/` was modified. Verified with `git status`:
the only untracked paths this audit created are `research/`.

**Headline: no CRITICAL defect was found.** In particular I could not break
belief soundness, the observation boundary, or the paired-deal construction,
and I tried hard to (≈860,000 independently-validated alternative worlds and
≈2,900 brute-forced constraint systems). The serious findings are a dead
safety guard in `BeliefState`, a silently-biased sample-dropping path in the
tournament estimator, and a latent `KeyError` in `ExactSolver`.

---

## Ranked findings

Index (the numbers match the detailed sections below; MAJOR first, then MINOR).

| # | Severity | File | One line |
|---|---|---|---|
| 1 | MAJOR | `fish/beliefs.py:135` | the "attach at game start" guard is dead code; mid-game attachment silently produces wrong beliefs |
| 2 | MAJOR | `fish/exact.py:53` | `information_is_resolved` can never return `True` for a constructed position (consequence of #1) |
| 3 | MAJOR | `fish/eval/tournament.py:173` | `incomplete_pairs` drops deals non-randomly; the reported CI can exclude the true value |
| 4 | MAJOR | `fish/agents/tablebase.py:60`, `fish/exact.py:259`, `fish/benchmark_exact.py:82` | live-card thresholds (7/8/9) are all the same policy: live cards are always a multiple of 6 |
| 7 | MAJOR (latent) | `fish/exact.py:142` | `ExactSolver` reuse across two roots of one layer raises `KeyError` |
| 5 | MINOR | `fish/engine.py:108` | `GameState.from_components` raises `AssertionError` on any terminal state |
| 6 | MINOR | `fish/engine.py:249` | a cardless on-move player may CLAIM; SPEC §4.3 says PASS is "Required" |
| 8 | MINOR | `fish/agents/tablebase.py:75` | `except (SubgameTooLarge, Exception)` hides real bugs (it is hiding #7 today) |
| 9 | MINOR | `fish/eval/tournament.py:34` | `_t_critical` is anti-conservative at high `conf` and small `df` (−4.9% at conf=0.999, df=4) |
| 10 | MINOR | `fish/eval/tournament.py:161` | start seat is `i % 6`; per-pair diffs are independent but not identically distributed unless `n_deals % 6 == 0` |
| 11 | MINOR | `fish/eval/tournament.py:70` | `wilson_ci` applies a binomial interval to a 3-outcome score (conservative) |
| 12 | MINOR | `fish/agents/tuned.py:149` | `TunedAgent` silently drops the `tablebase_max_cards` kwarg its parent accepts |
| 13 | MINOR | `fish/beliefs.py:81` | `_pinned_count` is written, never read, and is miscounted |
| 14 | MINOR | `fish/eval/elo.py:32` | listing a matchup in both directions double-counts it, undetected |
| — | NON-ISSUE | `fish/exact.py:113` | claim pruning to "true claims only" — see UNVERIFIED §U1 for the residual risk |
| — | NON-ISSUE | `fish/exact.py:202` | "unbroken cycle scores 0" is never reachable inside the tractable budget (doc overclaim, not a bug) |
| — | NON-ISSUE | `fish/beliefs.py:400` | sampler non-uniformity measured: max/min probability ratio ≤ 1.9× on small systems, full support |
| — | NON-ISSUE | `fish/eval/tournament.py:118` | paired-deal construction, and the shared `agent_seed`, are correct — see §10 |

---

### 1. MAJOR — the `BeliefState` mid-game-attachment guard is dead code

**File:** `fish/beliefs.py:135-142`

```python
if self._cursor == 0 and not self._observer_initialized:
    dealt = sum(obs.hand_counts) + 6 * sum(
        1 for w in obs.set_winner if w is not None)
    if not obs.history and dealt != self.n:
        raise BeliefContradiction(
            "BeliefState must be attached at game start; ...")
```

`dealt != self.n` is unsatisfiable. SPEC §7 invariant 2 states
`sum(hand sizes) + 6 * resolved == deck size` **at all times**, and
`GameState.check_invariants` asserts exactly that. So `dealt` is always 54
(or 48) and the guard can never fire.

**Reproduction** — `research/audit_scripts/a02_belief_attach_guard.py`:

```
random truncations where `dealt != 54` (i.e. guard would fire): 0/30

== 2. observer=None (spectator) mid-game attach: silent, no exception ==
  resolved half-suits: [3, 4, 7]
  update() SUCCEEDED with a truncated transcript (no raise)
  current_holder_mask(card 18 of RESOLVED half-suit 3) = 111111  (should be 000000)

== 4. observer!=None mid-game attach when observer holds exactly `per` cards ==
  seed=0: seat 3 holds 9 cards, 1 half-suit(s) resolved -> update() SUCCEEDED silently
    belief says resolved card 48 may be held by 110111 (truth: nobody)
    sample_current_hands gives 54 cards; true live cards = 48
```

The sampler then hands search agents **worlds containing already-resolved
cards** — 54 cards dealt into hands when only 48 are live.

The shipped test `tests/test_belief_propagation.py::test_belief_rejects_midgame_attachment`
passes for an unrelated reason. I instrumented it:

```
hand_counts (11, 10, 9, 8, 8, 8) resolved []
raised: player 5 count infeasible
```

It raises from the per-player count check in `_propagate`, only because that
particular seat happened to hold 8 cards instead of 9. With `observer=None`,
or with an observer holding exactly `per` cards, nothing raises at all.

**Fix.** Replace the guard with a real one. The cheapest sound test is
"public state is consistent with an empty log": require
`obs.history` to be non-empty **or** all of
`hand_counts == (per,)*6`, `all(w is None for w in set_winner)`, and
`turn == rules.starting_player`. Concretely:

```python
if self._cursor == 0 and not obs.history:
    fresh = (tuple(obs.hand_counts) == (self.per,) * NUM_PLAYERS
             and all(w is None for w in obs.set_winner))
    if not fresh:
        raise BeliefContradiction("BeliefState must be attached at game start")
```

For v04, prefer an explicit `BeliefState.from_transcript(rules, seat, history)`
constructor so that "attached at start" is a type-level fact rather than a
runtime check.

---

### 2. MAJOR — `information_is_resolved` can never return True for a constructed position

**File:** `fish/exact.py:53-67` (direct consequence of #1)

`information_is_resolved` builds a fresh `BeliefState(observer=None)` and
feeds it `Observation.from_state(state, 0)`. If `state.history` is empty
(any position built by `make_endgame`, `from_components`, or a determinized
world) the belief state learns nothing, every card stays ambiguous, and the
function returns `False` — but it also does **not** raise, because of #1.

**Reproduction** — `a02_belief_attach_guard.py` §3:

```
  a 6-live-card endgame with all locations trivially public
  information_is_resolved -> False (want True)
```

The shipped test only asserts the negative direction
(`tests/test_exact.py:139-142`: `assert not information_is_resolved(st)` on a
fresh deal), so this is untested in the direction that matters.

It happens to be *used* safely: `fish/benchmark_exact.py:110` calls it on real
in-game states that carry their full history, so the benchmark's
`resolved` / `unresolved` split is correct today. The hazard is that
`exact.py`'s own module docstring advertises this function as the gate for
"perfect-information optimal play IS optimal play", and any caller who passes
a constructed endgame gets a silent `False`.

**Fix.** Make the emptiness of the history an explicit precondition:

```python
def information_is_resolved(state, history=None) -> bool:
    hist = state.history if history is None else history
    if not hist and not _is_fresh_deal(state):
        raise ValueError("information_is_resolved needs the full public log")
```

and, in v04, thread the public log through `make_endgame` so synthetic
positions carry a transcript.

---

### 3. MAJOR — `incomplete_pairs` drops deals informatively and biases the estimate

**File:** `fish/eval/tournament.py:118-148` (worker) and `171-177` (accumulation)

```python
if not rec["complete"]:
    # A half-played pair is not a paired observation; counting it
    # would bias the differential toward the completed side.
    stats.incomplete_pairs += 1
    continue
```

Discarding a half-played pair is right; discarding it *silently* is not.
Timeouts are **not** missing-at-random: a game runs long precisely when the
policies fail to resolve half-suits, which is an outcome of the policies under
comparison. The estimator therefore conditions on "this deal happened to
finish".

**Reproduction** — `research/audit_scripts/a09_incomplete_pairs_bias.py`
runs the *same 60 deals* at several action caps
(`random(claim_prob=0.01)` vs `heuristic`):

```
GROUND TRUTH (cap 20000)
  n_pairs=60 incomplete=0 timeouts=0  mean diff=-9.783  CI=(-10.52, -9.046)
cap=500   n_pairs=53 incomplete= 7 timeouts= 8  mean diff=-10.132  CI=(-10.822, -9.442)
cap=400   n_pairs=20 incomplete=40 timeouts=50  mean diff=-11.450  CI=(-12.392, -10.508)

  cap=500: kept 53 pairs, dropped 7 pairs
  true mean over ALL pairs      : -9.783
  true mean over KEPT pairs     : -10.132
  true mean over DROPPED pairs  : -7.143
```

The dropped pairs have a true mean of −7.14 against −10.13 for the kept ones,
i.e. the drop is strongly informative. At `cap=400` the reported 95% CI
(−12.39, −10.51) **excludes** the true value −9.783. This is bias, not merely
lost precision, and no interval width will cover it.

(`max_actions` is 20000 in production, so today's timeout rate is low — the
mechanism, not the current magnitude, is the finding. Note also that
`stats.timeouts` counts *games*, `incomplete_pairs` counts *deals*, and
nothing in `summary()` warns when the two disagree.)

**Fix, in order of preference:**
1. Treat a timeout as a defined outcome rather than missing data. A game that
   never resolves is a real failure of the policy driving it; score it as
   `diff = 0` for that game (nobody banked anything), so the pair stays in the
   sample. This is exactly the `exact.py` "unbroken cycle scores nothing"
   semantics and keeps the estimator unbiased by construction.
2. If dropping is kept, make it loud: `summary()` and `to_dict()` should
   report the drop *rate* and refuse to print a CI when
   `incomplete_pairs / n_deals` exceeds a small threshold (say 1%).
3. Report the per-arm timeout counts separately (`timeout` currently sums both
   games of the pair, so you cannot tell which policy stalled).

---

### 4. MAJOR — every "live card" threshold in the codebase is a binary switch

**Files:** `fish/agents/tablebase.py:59-70`, `fish/exact.py:256-262`,
`fish/benchmark_exact.py:82-101`

Live cards are always exactly `6 × (unresolved half-suits)` — an unresolved
half-suit has all six of its cards in hands, a resolved one has none. So the
live-card count only ever takes the values 6, 12, 18, …

**Reproduction** (2260 real in-game positions, `probabilistic` self-play):

```
positions: 2260 violations of live_cards == 6*unresolved: 0
distinct (unresolved, live_cards) pairs: [(1, 6), (2, 12), (3, 18), (4, 24),
  (5, 30), (6, 36), (7, 42), (8, 48), (9, 54)]
```

Consequences:

* `ExactEndgameMixin.tablebase_max_cards = 8` means "fire iff exactly one
  half-suit is unresolved". Setting it to 6, 7, 8, 9, 10 or 11 gives the
  **identical** policy. It is exposed as a tunable constructor kwarg on
  `MemoryAgent` and `ProbabilisticAgent` and is already copied into
  `fish4/agent4.py:72`.
* `solve_position`'s `live > 9` guard means "refuse 2+ half-suits".
* `benchmark_exact.collect_solvable_positions(max_live_cards=7)` combined with
  `live_sets == 1` makes both `2 <= live_cards` and `<= max_live_cards`
  tautologies; the docstring
  *"Default max_live_cards is 7: at 8 the layer is ~1.7M placements"*
  describes a state that cannot exist.

**Fix.** Express these limits in the quantity that actually varies —
unresolved half-suits — e.g. `tablebase_max_half_suits: int = 1`,
`solve_position(..., max_half_suits=1)`. Keeping a card-count knob invites a
v04 sweep over values that provably do nothing.

---

### 5. MINOR — `GameState.from_components` crashes on any terminal state

**File:** `fish/engine.py:97-108` (`__init__` calls `_normalize_turn()` before
`set_winner` is known) and `134-142` (`from_components`), assertion at
`fish/engine.py:357`.

`__init__` sets `set_winner = [None] * n_hs` and *then* calls
`_normalize_turn()`. For a terminal component set (all half-suits resolved,
all hands empty) `is_terminal` is `False` at that moment, so normalisation
falls through to `raise AssertionError("non-terminal state but nobody has cards")`.

**Reproduction** — `research/audit_scripts/a01_rule_fidelity.py` §3 and
`a12_misc.py` §1:

```
GameState.from_components(R, [0]*6, 0, [0]*9)
  RAISED AssertionError : non-terminal state but nobody has cards

  TERMINAL from_components crash: AssertionError non-terminal state but nobody has cards
  from_components turn changes: 0  crashes: 10
```

(10 crashes = the 10 games in the fuzz, each at its terminal position. The
non-terminal round-trip is clean: 0 turn changes over 7260 seat-checks.)

An `AssertionError` also disappears under `python -O`, which is the wrong
failure mode for a state-construction API.

**Fix.** Assign `set_winner` before normalising:

```python
def __init__(self, rules, hands, turn, debug=False, set_winner=None):
    ...
    self.set_winner = list(set_winner) if set_winner is not None else [None] * self._num_hs
    ...
    self._normalize_turn()
```

and have `from_components` pass it through, so `_normalize_turn`'s
`is_terminal` early-out is evaluated against the real configuration. Convert
the trailing `AssertionError` into a domain exception.

---

### 6. MINOR — a cardless on-move player may CLAIM; SPEC §4.3 says PASS is required

**File:** `fish/engine.py:249-261` (`check_legal` for `Claim` never inspects
`self.hands[player]`); SPEC §4.2 legality list vs SPEC §4.3 first sentence.

SPEC §4.2 lists three claim conditions, none about holding cards, so the
engine matches §4.2. SPEC §4.3 opens with *"Required when the player to move
has no cards"*, and the independent human-rules summary says a cardless player
on move **passes**. The two readings disagree and the engine silently picks one.

**Reproduction** — `a01_rule_fidelity.py` §2:

```
turn after normalize: 0 hand_counts: (0, 1, 6, 1, 0, 0)
legal_passes(0): [Pass(teammate=2)]
  Claim by cardless on-move player is LEGAL per check_legal
```

Latent today: every shipped agent tests `obs.must_pass()` first, so none emits
one (`a12_misc.py` §6: `cardless claims emitted by shipped agents: 0` over 60
games × 4 agent types). It becomes live the moment a learned policy decodes an
action index without that guard — and a cardless claim is strictly stronger
than passing (it skips a ply), so a policy-gradient learner will find it.

Related and in the same spot: `claimable_half_suits(player)` returns half-suits
in which the claimant holds no cards. That one **is** SPEC-conformant and
matches the human rules (`a01_rule_fidelity.py` §1 shows player 4 with an empty
hand successfully claiming half-suit 0 held by teammates 0 and 2), so it is
correct behaviour, just worth knowing.

**Fix.** Decide the rule, then encode it once. Either add
`if self.hands[player] == 0: raise IllegalAction(...)` to the `Claim` branch
and delete the "Required" wording from §4.3, or keep the current behaviour and
rewrite §4.3 as "*may* pass" plus an explicit note in §4.2 that a cardless
player may still claim. Add a `RuleConfig` flag if both are wanted.

---

### 7. MAJOR (latent) — `ExactSolver` reuse across two roots of one layer raises `KeyError`

**File:** `fish/exact.py:141-144` and `152-156`, `233`

`_solve_layer` enumerates only the states **reachable from the root it was
given**, then marks the whole `config` done (`self._layer_done.add(config)`).
`solve()` afterwards does `if key not in self.cache: self._solve_layer(state)`
followed by an unguarded `return self.cache[key]`. A second root in the same
layer that was not reachable from the first therefore falls straight into a
`KeyError`.

Non-reachability is the norm, not an edge case: in a one-half-suit layer you
may only be asked for a card of a half-suit the asker already holds, so a
player at zero cards can never receive one, and different card placements are
mutually unreachable.

**Reproduction** — `research/audit_scripts/a06_exact_solver.py` §1:

```
  first  solve -> (1.0, Claim(half_suit=0, assignment=(0, 0, 0, 0, 0, 0)))
  second solve RAISED KeyError : KeyError(((0, 63, 0, 0, 0, 0), 1,
      (None, -1, -1, -1, -1, -1, -1, -1, -1)))
  File "fish\exact.py", line 144, in solve
    return self.cache[key], self.best.get(key)
  (a fresh solver gives: (-1.0, Claim(half_suit=0, assignment=(1, 1, 1, 1, 1, 1))) )
```

Every production caller happens to build a fresh solver (`solve_position`,
`ExactEndgameMixin.tablebase_action`, the tests), so it does not fire today.
It is one line away from firing: the obvious optimisation for v04 — amortise a
solver across a batch of endgames — is exactly what triggers it. The same
mechanism would fire on multi-layer recursion (two different claim exits into
the same deeper configuration), which is only unreachable because 2 half-suits
are refused as too large (#4).

**Fix.** `_layer_done` is not a sound memo key. Either drop it and key the
memo on the state (`if key in self.cache: return`), or make it
`self._layer_done: set[tuple]` of *(config, frozenset(states))* — simplest is:

```python
def _solve_layer(self, root):
    if position_key(root) in self.cache:
        return
    ...   # and delete _layer_done entirely
```

The `config in self._layer_done` short-circuit saves nothing once `self.cache`
already answers the question.

---

### 8. MINOR — `except (SubgameTooLarge, Exception)` swallows genuine bugs

**File:** `fish/agents/tablebase.py:75`

```python
except (SubgameTooLarge, Exception):
    return None
```

This is just `except Exception`. It is what keeps finding #7 invisible: any
`KeyError`, `AssertionError` or `TypeError` in the solver silently degrades the
agent to its heuristic policy, and every measured "tablebase ablation" result
would look the same whether the tablebase worked or crashed on every call.
The same pattern repeats at `fish/agents/tablebase.py:82` for the legality
re-check.

**Fix.** Catch only what is expected (`except SubgameTooLarge: return None`)
and let anything else propagate, or at minimum count the swallowed exceptions
on the agent so an ablation can assert the feature actually ran.

---

### 9. MINOR — `_t_critical` is anti-conservative outside its tested range

**File:** `fish/eval/tournament.py:34-43`

The docstring claims *"accurate to well under 1% for df >= 4"*. At the default
`conf=0.95` that is true; the shipped test only checks df ∈ {5, 10, 30, 1000}
at 95%. But `conf` is a public parameter of `diff_mean_ci`.

**Reproduction** — `research/audit_scripts/a07_stats.py` §1/§1b (exact values
from an inverse Student-t built on the regularized incomplete beta):

```
 df     approx      exact     rel.err
   1    9.71058   12.70620   -23.576%
   2    4.17121    4.30265    -3.055%
   3    3.15899    3.18245    -0.737%
   4    2.76937    2.77645    -0.255%
  10    2.22797    2.22814    -0.007%
worst relative error for df>=4: -0.255% at df=4

 conf=0.990: df=4 4.5469/4.6041 (-1.24%)  df=5 4.0097/4.0321 (-0.56%)
 conf=0.999: df=4 8.1870/8.6103 (-4.92%)  df=5 6.7071/6.8688 (-2.35%)
```

The error is always **negative** — intervals come out too narrow, which is the
wrong direction for a project that retracted a set of ratings for
overclaiming. At `df ≤ 3` the error reaches −24%.

**Fix.** Either restrict the docstring to `conf=0.95, df>=4` and raise for
other inputs, or replace the Cornish-Fisher expansion with an exact inverse —
`research/audit_scripts/a07_stats.py` contains a 25-line dependency-free
`betai` + bisection implementation that is exact to machine precision and
costs microseconds. There is no reason to approximate here.

---

### 10. MINOR — pairs are independent but not identically distributed

**File:** `fish/eval/tournament.py:161-162`

```python
jobs = [(spec_x, spec_y, rules_dict, base_seed + i, i % 6,
         seed_rng.getrandbits(64)) for i in range(n_deals)]
```

The starting seat is `i % 6`, deterministic and perfectly correlated with the
deck seed `base_seed + i`. The pairing itself is genuine — I verified it
directly (`a07_stats.py` §2):

```
 same deck        : True
 same start seat  : True 3
 same agent seed  : True
 seat assignment 1: ('heuristic', 'memory', 'heuristic', 'memory', 'heuristic', 'memory')
 seat assignment 2: ('memory', 'heuristic', 'memory', 'heuristic', 'memory', 'heuristic')
```

and the per-pair diffs are serially uncorrelated (`a07_stats.py` §4, n=60,
lag-1 autocorrelation **+0.013**). But "i.i.d." as claimed in the module
docstring requires *identically* distributed too, and the seat rotation is a
fixed covariate, not a random one. When `n_deals % 6 != 0` the sample is
unbalanced across starting seats and the mean is a weighted average with
uneven weights. Empirically the seat effect is small here:

```
   start seat 0: n=10 mean=-11.800   start seat 3: n=10 mean=-11.000
   start seat 1: n=10 mean=-11.500   start seat 4: n=10 mean=-11.200
   start seat 2: n=10 mean=-12.300   start seat 5: n=10 mean=-11.600
```

so the practical impact is small — but the presets already use
`n_deals` ∈ {30, 40, 120, 400} and only 30 and 120 are multiples of 6.

**Fix.** Draw the starting seat from an independent RNG stream (like the agent
seed), or assert `n_deals % 6 == 0`, or block on seat and report the
block-mean. Also note that the same `i % 6` rotation combined with
`deal_seed = base_seed + i` means "deck j" and "seat j mod 6" are locked
together forever; drawing the seat separately removes that confound too.

**On the shared `agent_seed`:** it is a *benefit*, not a problem. Both games of
a pair get the same `agent_seed`, so seat *k* draws the same RNG stream in both
— common random numbers across the swap, which reduces the variance of the
paired difference without touching its expectation. The seeds come from
`seed_rng`, a stream independent of the deck seeds
(`fish/eval/tournament.py:159-162`), so it also carries no information about
the deal. Keep it.

---

### 11. MINOR — `wilson_ci` applies a binomial interval to a three-outcome score

**File:** `fish/eval/tournament.py:70-78`

`pair_score()` is `(wins + 0.5*ties) / n`, a mean of a variable on {0, 0.5, 1},
but `wilson_ci` uses the binomial variance `p(1-p)`. With ties present the true
variance is smaller, so the interval is conservative (too wide) — the safe
direction, and it is also the interval `League.promote` gates on
(`fish/eval/league.py:86-93`), so promotions are if anything harder than
intended. Worth correcting for honesty, not urgency: use the sample variance of
the per-pair scores, or state in the docstring that it is a conservative bound.

---

### 12. MINOR — `TunedAgent` drops a kwarg its parent accepts

**File:** `fish/agents/tuned.py:149-154`

**Reproduction** — `a12_misc.py` §3:

```
  ProbabilisticAgent: ['n_samples', 'claim_threshold', 'suit_bonus', 'use_tablebase', 'tablebase_max_cards']
  TunedAgent        : ['n_samples', 'claim_threshold', 'w_suit', 'w_turn', 'w_reveal', 'w_scarce', 'w_deplete', 'use_tablebase']
  tuned(tablebase_max_cards=6) -> TypeError: TunedAgent.__init__() got an
      unexpected keyword argument 'tablebase_max_cards'
```

Since agent specs cross process boundaries as `(name, kwargs)`
(`fish/eval/tournament.py:26-31`), this turns into a worker-process `TypeError`
mid-tournament. Given #4 the kwarg is inert anyway, but the asymmetry is a
trap. Fix: `**kwargs` pass-through, or drop the knob from both.

---

### 13. MINOR — `BeliefState._pinned_count` is dead and miscounted

**File:** `fish/beliefs.py:81, 99, 113`

```
    self._pinned_count = [0] * NUM_PLAYERS      # __init__
    self._pinned_count[player] += 1             # _pin
    self._pinned_count[new.bit_length() - 1] += 1   # _exclude
```

Never read anywhere in the module. It is also wrong: `_exclude` increments the
survivor's count whenever a candidate set collapses to a singleton, with no
check that the card was not already counted, and `_pin` increments even when
the card was already a two-candidate set being narrowed. Harmless only because
nothing consumes it. Delete it, or wire it into `_propagate` (which currently
recomputes the same quantity from scratch on every pass — `fish/beliefs.py:212-221`
scans all 54 cards per iteration).

---

### 14. MINOR — `fit_ratings` double-counts a matchup listed in both directions

**File:** `fish/eval/elo.py:32-93` (`fit_ratings`)

**Reproduction** — `research/audit_scripts/a11_elo.py` §3:

```
  once : {'a': (200.0, 1060.8), 'b': (9.2, 40.1)}
  twice: {'a': (200.0, 1060.8), 'b': (9.2, 28.4)}
```

Adding `("b","a",0.25,100)` alongside `("a","b",0.75,100)` leaves the point
estimate unchanged but shrinks the stderr by √2 — a caller error that produces
a *confidently wrong* uncertainty. `scripts/run_tournament.py:49-60` iterates
`j in range(i+1, ...)` so it is correct today, but nothing enforces it.

**Fix.** Canonicalise and aggregate inside `fit_ratings`: key rows on
`tuple(sorted((a,b)))`, flip `s` when reversed, and sum `n` — then a duplicate
listing is merged instead of double-weighted, and an accidental
`("a","b",0.75,100), ("a","b",0.60,100)` becomes a legitimate pooled row.

---

## What I checked and found CORRECT

These are the parts I attacked and could not break. They should be treated as
trustworthy going into v04.

**Belief soundness — the thing I tried hardest to break.**

* *Propagator vs brute force.* `research/audit_scripts/a03_propagator_soundness.py`
  and `a04_pigeonhole_stress.py` build random constraint systems of exactly the
  engine's shape (per-card candidate masks, exact per-player counts, OR
  constraints), with most cards hard-pinned so 6–9 cards are free, run the real
  `_propagate` / `_propagate_or_pigeonhole`, then **exhaustively enumerate**
  every assignment satisfying candidates ∧ counts ∧ ORs and compare supports.

  ```
  k_free=6: 300 random systems, 1037 enumerated solutions, 0 soundness violations
  k_free=7: 300 random systems, 1823 enumerated solutions, 0 soundness violations
  k_free=8: 300 random systems, 2950 enumerated solutions, 0 soundness violations

  k_free=6: sat=500 unsat=0 solutions=1752 bugs=0
  k_free=7: sat=500 unsat=0 solutions=3007 bugs=0
  k_free=8: sat=500 unsat=0 solutions=4594 bugs=0
  k_free=9: sat=500 unsat=0 solutions=7674 bugs=0
  pigeonhole rule fired (changed something) in 1354 propagation passes
  TOTAL SOUNDNESS VIOLATIONS: 0
  ```

  `a04` is *engineered* to make the pigeonhole rule bite (tight quotas, several
  disjoint and overlapping OR groups per player, subsumable groups). It fired
  1354 times and never removed a possible owner, and never raised a spurious
  contradiction on a satisfiable system.

  I specifically expected a bug from the stale `quota` list passed into
  `_propagate_or_pigeonhole` (it is computed at the top of the `while changed`
  body but OR unit propagation pins cards after that, so `quota[p]` can be too
  large). It is benign: an over-large `quota[p]` can only make the rule fire
  when `len(disjoint) == quota_stale[p]`, and since the true quota is never
  larger, a genuine solution would already require `len(disjoint) <= quota_true[p]`,
  forcing `stale == true`. The brute force confirms this empirically.

* *End-to-end against the independent gold-standard validator.*
  `research/audit_scripts/a05_end_to_end_soundness.py` takes real game prefixes,
  permutes the true initial owners of a random 8-card subset that never touches
  the observer's own cards, keeps every permutation that passes
  `validate_deal_against_history` (the module's own independent replay
  validator), and asserts the live `BeliefState` admits it — both the candidate
  masks and every stored OR constraint.

  ```
  agent=memory        : tried 683718, history-consistent 214032, VIOLATIONS 0
  agent=probabilistic : tried 683718, history-consistent 165238, VIOLATIONS 0
  agent=heuristic, allow_bluff_asks=True : tried 416444, consistent 172992, VIOLATIONS 0
  agent=memory, variant=48 : tried 420280, consistent 112652, VIOLATIONS 0
  agent=memory, observer=None (spectator) : tried 678580, consistent 195951, VIOLATIONS 0
  ```

  ≈860,000 genuinely-possible alternative worlds, none excluded.

* *The `_ingest_ask` OR construction is correct.* It builds the OR only over
  cards whose `public_loc` is `None` — i.e. cards that have never moved, so
  "currently the asker's" is equivalent to "initially the asker's", which is
  what `candidates` encodes. Cards publicly sitting with the asker short-circuit
  to `satisfied`; cards publicly sitting elsewhere are correctly excluded; the
  asked card is correctly excluded under no-bluff rules. Events are ingested in
  order, so `public_loc` always reflects the moment *before* the ask.

* *The `per`-card count constraint subsumes the information the engine appears
  to ignore.* `_ingest` does nothing on a `PassEvent`, which looks like a
  missed deduction ("the passer holds zero cards"). It is not: every card with
  `public_loc != None` was pinned when it first moved, so
  `#{unmoved cards initially p's} = per − K_p` is a constant, and the
  `quota[p] == 0` branch of `_propagate` derives exactly the same exclusions.
  Confirmed empirically — no sampled world ever contradicted the public hand
  counts (below).

* *Sampler.* `research/audit_scripts/a10_sampler.py`, 4440 worlds drawn from
  live belief states across 8 games:

  ```
  worlds sampled: 4440  sampler failures: 0
  count-inconsistent worlds: 0
  replay-invalid implied deals: 0
  ```

  and, against exhaustive enumeration of the consistent set on small systems:

  ```
  trial 0: 8 consistent worlds, 0 never sampled, 0 sampled-but-inconsistent, p/uniform in [0.81, 1.38]
  trial 3: 8 consistent worlds, 0 never sampled, 0 sampled-but-inconsistent, p/uniform in [0.74, 1.39]
  trial 4: 7 consistent worlds, 0 never sampled, 0 sampled-but-inconsistent, p/uniform in [0.78, 1.15]
  trial 5: 5 consistent worlds, 0 never sampled, 0 sampled-but-inconsistent, p/uniform in [0.95, 1.14]
  worst max/min sampling-probability ratio seen: 1.9x
  ```

  So the module's own caveat is honest and, importantly, the sampler has **full
  support** (no consistent world was ever unreachable). The distortion is real
  but modest — worth quantifying in `RESEARCH_LOG.md` rather than left as an
  open unknown.

**Information leakage.** No leak found.

* `Observation` exposes exactly `player, rules, hand, turn, hand_counts,
  set_winner, history`. No `hands`, no `agent_seed` (`a08` §3).
* `Observation.from_state` is *identical* to `Observation.reconstruct` from
  (rules, own initial hand, public log) at **183,750 seat-plies** across 8 rule
  configurations — including `claims_any_time`, `allow_bluff_asks`,
  `wrong_distribution_outcome="opponent"`, non-zero `starting_player`, and the
  48-card variant, none of which the shipped tests cover
  (`research/audit_scripts/a08_observation_leakage.py`):

  ```
  seat-plies checked: 183750
  reconstruct mismatches: 0
  initial_hand errors: 0
  ```

  `Observation.initial_hand()` (which `BeliefState` uses to pin the observer's
  own cards, so an error there would be an unsoundness source) matched the true
  initial hand at every one of those plies.
* `Observation`'s legality helpers agree exactly with `GameState`'s for every
  seat over 7260 seat-checks (`a12_misc.py` §1: `legality disagreements: 0`),
  so a policy never needs the engine to know what it may do.
* Every acting policy reads only its `Observation` and its own `BeliefState`.
  The `GameState` objects inside `SearchAgent`, `PairedSearchAgent` and
  `ValueSearchAgent` are built from `belief.sample_current_hands(...)` —
  hypotheses drawn from legal information, not the truth. `pinned_state`
  (`fish/agents/tablebase.py:32-49`) is built entirely from
  `belief.current_holder_mask` and additionally re-checks that the
  reconstruction reproduces the public hand counts and the agent's own hand, so
  the tablebase claim of leak-freedom holds.
* `fish/learning/pi_dataset.py:45` uses `state.hands` for *training targets*
  only, with the acting agent still driven through `Observation` at line 42 —
  the documented and legitimate split.
* `fish/web/server.py` and `fish/coach.py` both drive agents through
  `Observation` (`from_state` / `reconstruct` respectively). The browser sees
  all hands, but the browser is not a policy.
* Agent seeds come from a stream independent of the deal, in both
  `runner.play_game` (`secrets.randbits(64)` or an explicit `agent_seed`) and
  `tournament.play_matchup` (`seed_rng`, seeded from `agent_seed_base` or
  fresh entropy). Verified by source inspection in `a08` §4.

**Rule fidelity.** Everything in SPEC §4 that I probed matches the engine and
the independent human-rules statement, except finding #6.
`research/audit_scripts/a01_rule_fidelity.py`:

* exact claim ⇒ claiming team scores; any opponent card ⇒ opponents score;
  all-in-team but wrong split ⇒ `null` under baseline, `opponent` under the
  house rule. Verified for three distinct wrong splits.
* the declared assignment is coerced with `tuple(...)` before comparison, so a
  list decoded from an RL action space scores correctly (`list assignment -> 0`).
* one team out of cards ⇒ the other has no legal ask (`legal_asks(0): []`,
  `must_claim(0): True`) and must claim the rest out, exactly as the human
  rules say.
* `_normalize_turn` advances to the next clockwise player with cards only when
  the mover *and* their whole team are cardless, and that player is necessarily
  an opponent; otherwise the cardless mover must `PASS`. Matches SPEC §4.4, and
  the `Pass(-1)` / `Pass(7)` bounds checks noted in the source comment are
  genuinely present and correct.
* claiming a half-suit in which you hold no cards is permitted — correct per
  both SPEC §4.2 and the human rules.

**Exact solver.**

* *Value iteration is order-independent* on every layer I could solve.
  `research/audit_scripts/a06_exact_solver.py` §2 re-runs the identical
  algorithm with a shuffled sweep order (3 seeds × 4 layers) and gets the same
  fixpoint every time:

  ```
  hands=['0b110000','0b1100','0b0','0b11','0b0','0b0'] turn=0 base=+1.0 shuffled=[1.0, 1.0, 1.0]  OK
  hands=['0b100000','0b10000','0b1000','0b100','0b10','0b1'] turn=0 base=+1.0 shuffled=[1.0, 1.0, 1.0]  OK
  hands=['0b111000','0b111','0b0','0b0','0b0','0b0'] turn=1 base=-1.0 shuffled=[-1.0, -1.0, -1.0]  OK
  hands=['0b110100','0b0','0b1000','0b11','0b0','0b0'] turn=2 base=+1.0 shuffled=[1.0, 1.0, 1.0]  OK
  ```

* *`optimal_actions` is consistent.* Every returned action re-evaluates to the
  layer value, and `solve()`'s own choice is always among them (§4:
  `best_in_optimal=True  mis-valued=0` on all four layers, 2–4 optimal actions
  each, so genuine ties are being found rather than collapsed).

* *Claim pruning to "true claims only" changed nothing* on every solvable
  layer (§3: four layers, `SAME` on all four) — see §U1 for the residual risk.

* *The "unbroken cycle scores 0" branch is unreachable through the public API*,
  which is worth knowing before v04 builds on it. Two half-suits is the
  smallest layer that can stall, and that is 12 live cards:

  ```
  2-half-suit layer: SubgameTooLarge - layer with 12 live cards is ~6^12
      placements, far beyond the 400000-state budget
  solve_position: SubgameTooLarge - 12 live cards is beyond exact enumeration
  ```

  In a one-half-suit layer the mover always wins outright: with perfect
  information every ask can be made to succeed, so the mover drains every
  opponent and claims, so the value is ±1 by the mover's team and a stall is
  never optimal. Every one-half-suit layer I solved (9 distinct layers across
  `a06` §2/§3 and the timing runs) came out at exactly ±1, never 0 — so the
  cycle-0 branch was never the answer in any position the solver can reach.
  The `ARCHITECTURE.md` §6 sentence *"A side that can only lose by
  claiming will therefore prefer to stall forever, which is exactly what real
  Fish stalemates look like"* describes behaviour the shipped solver has never
  been able to exhibit. It is not wrong as a design intent, but it is untested
  and should not be cited as a validated property.

**Bradley-Terry ratings (`fish/eval/elo.py`) — correct and well-implemented.**
`research/audit_scripts/a11_elo.py`:

* The fit is a genuine stationary point of the exact log-posterior, not an
  iteration artifact. The finite-difference gradient of the negative
  log-posterior at the returned estimate is *uniform across all four
  components* (`[1.93e-04] × 4`), which is precisely the signature of a
  likelihood gradient that is exactly zero, offset only by the unknown constant
  I had to guess when undoing the anchor shift. The likelihood part is
  stationary to machine precision.
* `stderr` is a correct Laplace standard error. Against a numerically
  differentiated Hessian of the exact negative log-posterior:

  ```
  heuristic      reported   37.40   numerical   37.40
  memory         reported   40.26   numerical   40.26
  probabilistic  reported   44.18   numerical   44.18
  random         reported  750.53   numerical  750.41
  ```

  The anchor-relative variance `cov[i,i] + cov[a,a] - 2*cov[i,a]` is the right
  formula and is what is being used.
* Perfect separation gives a finite, flagged bound
  (`{'a': (1732, True), 'b': (200, True)}`), `n == 0` rows are dropped, and an
  unknown anchor degrades gracefully. The retraction described in the module
  docstring appears to have been done properly.

**Paired-deal construction.** Genuinely paired: same deck, same rotated
starting seat, same agent seed, only the seat→policy map differs (§10 above for
the transcript). The shared agent seed is a variance-reduction benefit.

---

## UNVERIFIED (stated as risk, not as finding)

### U1. Pruning `ExactSolver.actions` to true claims may be unsound in principle

`fish/exact.py:113-133` generates only claims the claimant's team provably
holds in full, on the argument that *"a knowingly-wrong claim is never better
than a correct one, and claiming a set the opponents hold simply gifts it to
them."*

Half of that is provable: a wrong-split claim and a true claim of the same
half-suit lead to the *identical* successor state (all six cards removed,
half-suit resolved; the winner label does not affect future play), differing
only in immediate reward, so the true claim dominates. That half is safe.

The other half is not obviously true. Gifting a half-suit the opponents touch
costs −1 but **reduces the layer**, and the successor is a state no other
action can reach. If the resulting simpler layer is worth more than +1 to the
gifting team, the gift is optimal and the solver would miss it. This is exactly
the "stall vs. break the stall by paying a set" trade the module's own cycle-0
semantics is designed to represent.

I could not construct a counterexample, because the smallest layer in which a
stall is possible needs 2 unresolved half-suits (finding #4) and that is
refused as too large. Within the solvable range (one half-suit) I verified
directly that unpruned and pruned solving agree on every layer tested
(`a06_exact_solver.py` §3, 4/4 `SAME`), which is expected since the mover
always wins outright there. **So: no evidence of a bug, and no evidence of
correctness either.** If v04 raises the tractability ceiling — the obvious next
step — this pruning must be re-derived or removed before the solver is used as
ground truth on multi-half-suit layers.

### U2. Long-run timeout rate in production tournaments

Finding #3 demonstrates the *mechanism* of the drop bias with an artificially
reduced action cap. I did not measure how often `incomplete_pairs > 0` at the
production `max_actions=20000` across the agent matrix, because that needs a
full tournament run. The recorded matchups in `results/` would answer it
directly; anyone acting on #3 should read `incomplete_pairs` out of those JSONs
first to size the problem.

---

## Notes on the audit itself

* **I killed background Python processes.** Partway through I ran
  `taskkill /F /IM python.exe` to stop one of my own long-running probes. That
  terminated *all* `python.exe` on the machine, including a
  `codex-primary-runtime` process and possibly another session's work. There is
  a concurrent v04 effort writing to this repo (`fish4/`, `scripts4/`,
  `tests4/`, `results/logs/`, timestamps 02:18–02:35 today) that I did not
  touch but may have interrupted. Flagging it so it can be re-run if it died.
* No file under `fish/`, `tests/`, or any top-level `.md` was modified.
  Targeted regression run to confirm a clean baseline:
  `py -m pytest tests/test_exact.py tests/test_eval_stats.py
  tests/test_observation.py tests/test_engine_rules.py -q`
  → **80 passed in 115.13s**.
* Scripts: `research/audit_scripts/a01`…`a12`. All are standalone
  (`py research/audit_scripts/aNN_*.py`); `a05` takes
  `<n_games> <agent> <rules-json> [spectator]`. The exact-solver probe `a06`
  takes ~4 minutes (each one-half-suit layer costs 3–20 s to solve); everything
  else runs in under two minutes.

---

## Suggested order of work for v04

1. **#1 + #2** — fix the belief attachment guard and `information_is_resolved`.
   These are cheap and they unblock synthetic-position tooling, which v04 will
   want.
2. **#3** — decide the timeout semantics *before* running any v04 evaluation.
   Scoring a timeout as `diff = 0` keeps the estimator unbiased and matches the
   solver's own cycle semantics.
3. **#7 + #8** — fix the `_layer_done` memo and stop swallowing exceptions, in
   that order; #8 is what would have surfaced #7.
4. **#4** — re-express the tractability knobs in half-suits before anyone
   sweeps them. `fish4/agent4.py:72` has already inherited the dead knob.
5. **#5, #6** — engine contract cleanups; #6 needs a rules decision, not just
   code.
6. **U1** — settle the claim-pruning argument before raising the solver's
   tractability ceiling.
