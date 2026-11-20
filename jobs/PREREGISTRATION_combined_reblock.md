# Pre-registration: re-run COMBINED so both blocks share an engine

Written **before either replay has been played**.

## The problem

`COMBINED` is the paper's directly measured value for the configuration
`api/_engine.py` serves — **+0.357** over the champion, pooled from two blocks
of 1000 pairs. `scripts4/check_engine_provenance.py` found that the two blocks
did not play the same program:

```
block 0   08-24 03:06Z   +0.477   claim4.py 0b1bf3c747bf, never committed
af2ac1f   08-24 03:13Z            forced_claim: independence product -> exact joint
block 1   08-24 03:22Z   +0.235   claim4.py ded5993a368e (= af2ac1f)
```

`claim4.py` is the **only** file that differs between them; the other ten
fingerprinted files are identical. So the pool averages one block played before
a claim-logic bug fix with one played after it, and reports the result as a
single configuration measured directly.

The fix was not cosmetic. `_best_split` returned the joint probability for "this
split is right" alongside the **independence product** for "ours at all", and
`forced_claim` subtracted one from the other — a difference between two
different distributions. The project measured the two disagreeing on 27,902 of
29,406 queries, the product overstating on 86%.

The blocks differ by **0.242 ± 0.170**, which is 1.4 SE. That is *not* evidence
the pooled number is wrong. It is that the interval is quoted as one thing and
is an average over two.

## What is being run

Both blocks replayed **at their own original seeds**, under the current engine.

| cell | seeds | n |
| :--- | :--- | ---: |
| `REPLAY COMBINED 480+lookahead vs champion block 0` | base 27 000 000, agent 9920 | 1000 |
| `REPLAY COMBINED 480+lookahead vs champion block 1` | base 27 200 000, agent 9921 | 1000 |

Same seeds, deliberately. Fresh seeds would confound the engine change with
deal variation; identical seeds mean the old-versus-new difference has **no
deal variance at all** and is attributable entirely to `claim4.py`. That is a
far sharper measurement than the between-block comparison, which carries the
full per-pair sd.

`scripts4/check_seeds.py` gained a narrow exemption for this: a cell labelled
`REPLAY <original>` sharing exactly that original's seed range is a declared
replication rather than a collision. The exemption applies only to that one
pair and only on an exact range match; a `REPLAY` cell overlapping anything
else is still reported.

### Block 1 is the gate

Block 1 already ran under `claim4.py` at `af2ac1f`, which is the current
version. Its replay must therefore reproduce **+0.235 exactly**.

Three files do differ between block 1's engine and today's — `agent4.py`,
`hsvalue.py`, `registry4.py` — all touched by this session's `value_keep` work.
The claim that they are inert **for this arm** is checkable rather than
asserted: the spec is `objective` default `"linear"` with no `w_value`, so
`score_asks_by_value` is never called; the `value_keep` guard cannot fire with
the parameter unset; and duel jobs pass specs in full, so registry constants
are bypassed. If the block 1 replay does not reproduce +0.235 exactly, that
reasoning is wrong somewhere and the whole re-run is invalid — in which case
both blocks need fresh seeds under one engine instead, and this design is
abandoned rather than patched.

## The replacement rule, fixed now

**The re-run pool replaces +0.357 wherever the paper quotes a directly measured
value for the shipped configuration, whatever it says.** Not an average with
the old pool, not the old pool if the new one is less convenient. The old
blocks stay in `results/v04_duels.jsonl` as history.

## Predictions

1. **Block 1 replay reproduces +0.235 exactly.** If it does not, stop.
2. **Block 0 replay moves.** Its old value, +0.477, was played with the buggy
   claim EV. The paired difference (new − old, identical deals) is the pure
   effect of the fix on this matchup.
3. **Direction: I do not know, and say so.** The fix makes the engine's estimate
   of "ours at all" strictly more accurate, and *both* sides of the duel use the
   same claim code, so the net effect on a differential could go either way. A
   guess that block 0 falls toward block 1 would be the tidy answer — it would
   make the two blocks agree and the original spread look like a bug rather
   than noise — and tidiness is exactly the wrong reason to expect something.
4. **The new pool: most likely between +0.235 and +0.357.** If block 0 barely
   moves, the pool stays near +0.357 and the mixed-engine finding turns out to
   be a provenance defect with no numerical consequence, which is still worth
   knowing and still worth fixing.

## What this does not decide

Nothing about `CLAIM THRESHOLD` or `RETAKE BONUS`, which are mixed the same way
but are nulls whose conclusions do not turn on it. Nothing about the five pools
that predate the fingerprint entirely and cannot be checked at all. And nothing
about the public table, which keeps `V04_COMBINED` either way — this run
re-measures that configuration, it does not change it.
