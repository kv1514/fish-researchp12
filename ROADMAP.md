# Roadmap

Ordered by expected information gain toward "what does near-optimal Fish
look like", not by how impressive the technique sounds.

The governing question each cycle: **what is currently preventing this
engine from making closer-to-optimal decisions, and what experiment removes
that bottleneck?**

---

## Where strength is currently lost (measured)

Agreement with exact optimal play, 327 solvable endgame positions:

| agent | information already resolved | genuine uncertainty | value loss |
|---|---|---|---|
| probabilistic | **100%** | 75.6% | 0.104 |
| memory | **100%** | 69.0% | 0.138 |
| paired_search | 100% | 73.6% | 0.122 |
| value_search | **97.7%** | 68.0% | 0.177 |
| heuristic | 66.2% | 47.7% | 0.275 |
| random | 48.5% | 28.9% | 0.465 |

Two load-bearing consequences:

1. **In positions we can verify, the belief agents are already optimal.**
   The remaining gap is not in the endgame, so endgame search has almost no
   headroom and work aimed there will not pay.
2. **`value_search` has a locatable defect**, not just a tuning problem: it
   is the only agent that misses information-resolved positions, where the
   correct move is unambiguous and its own prior already had it. Fixing
   that is a hard prerequisite, and it now has a precise pass condition
   (130/130) instead of a vague one.

The gap lives in midgame positions that are too large to solve exactly, and
in the two decisions that are still made by formula rather than by
reasoning: which ask to make, and when to claim.

---

## Next, in order

### 0. Make value_search stop breaking unambiguous positions
It fails 3 of 130 information-resolved endgames, where there is nothing to
guess. Concrete diagnosis path: dump those three positions, check whether
the learned value or the paired significance test is responsible, and gate
the network so it cannot override a prior choice that is provably forced
(e.g. skip search entirely when the belief state pins every relevant card).
Pass condition: 130/130. This is the cheapest well-defined bug in the
project and it blocks trusting the evaluator anywhere else.

### 1. Beat the prior at least once (open problem)
No search variant has yet been significantly BETTER than the belief policy;
common random numbers only removed the deficit, and on the exact benchmark
search is still slightly *behind* its prior under uncertainty (73.6% vs
75.6%). Until search adds value, every downstream plan (teacher/student,
league, massive self-play) is building on a teacher no stronger than its
student.

Concrete next attempts:
- Search only in positions where the prior is *uncertain* (small margin
  between top candidates). Where the prior is confident, defer to it. This
  spends compute where discrimination is possible and avoids adding noise
  where it is not.
- Deeper lookahead with a *weaker, more varied* in-tree policy, since the
  quiescence failure suggests over-strong uniform continuations destroy
  discrimination.
- Opponent-response search: evaluate after the opponent's best reply, not
  after our own move.

### 2. Learn the ask objective instead of hand-coding it
Ask value is currently `P(success) + 0.06 * suit_progress`. The coefficient
is arbitrary. Learn the full value of an ask including turn retention,
information gained on success and on failure, information leaked to
opponents, and which opponent receives the turn on failure. `TunedAgent`-style
weights make each term individually ablatable so the data, not intuition,
sets them.

### 3. Finish the claim study
The EV model derives a claim threshold near 0.70, well below the 0.97 that
was used by intuition. The threshold sweep is the direct test. Then extend
the model with the terms it currently approximates: score dependence, number
of unresolved sets, and the probability an opponent claims first.

### 4. Fix sampler bias
The world sampler satisfies every constraint but is not uniform over the
consistent set (OR seeding and quota weighting skew it). Quantify the bias
against exhaustive enumeration on small positions, then try importance
weighting or MCMC refinement. Every probability the engine reports inherits
this bias.

### 5. Widen exact ground truth
Currently limited to one live half-suit and <= 9 cards. Worth trying:
reduced decks, restricted claim rules, and forced-claim endings. More
solvable structure means more absolute validation, which is the only kind
that cannot fool us.

### 6. Teacher/student, then league (blocked on item 1)
Once search genuinely exceeds the prior, use it to label difficult
information states, train a policy head, and put the student back inside
search. Then population play: champion, historical checkpoints, exploiters,
independently initialized runs. Promotion already requires a paired-deal CI
strictly above 0.5.

### 7. Exploiters
For every champion, deliberately train a best response against it. A policy
that dominates previous bots may still be very exploitable, and we will not
know until we try to break it.

### 8. Emergent conventions, tested honestly
Check whether coordination conventions arise in self-play without any
explicit channel, then test them in **cross-play against independently
trained partners**. An engine that only wins alongside copies of itself
using a private convention has not solved general Fish; that distinction is
the whole test.

---

## Deliberately not doing yet

- **Rewriting the core in Rust/C++.** Profiling says inference dominates,
  not rule application. Revisit when that inverts.
- **Large neural networks.** The current value net already explains 58.7% of
  outcome variance and still does not help search. Capacity is not the
  binding constraint; the search harness is.
- **Millions of self-play games.** Volume is only worth buying once the
  policy generating them is better than what we already have.
