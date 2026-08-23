# Pre-registration: do learned ask weights beat hand-tuned ones, now that the target carries signal?

Written **before the fit has been run on the v2 data**, and before any learned
weight vector has been looked at. That is the only moment at which writing this
means anything.

## What changed since the line failed

v0.4 learned the ask objective by common-random-numbers paired rollout
regression, and the learned weights lost badly: $-2.183$ sets per deal-pair over
120 pairs for the best of three variants. The paper diagnosed the cause as the
rollout continuation, and then closed the line on a claim that the strong policy
*could not* be used as one.

That claim was false. With the full engine finishing every rollout, on identical
positions, identical worlds and identical root asks, the target's slope on
$P(\text{success})$ rises from $+0.040 \pm 0.045$ to $+0.681 \pm 0.142$ — a
paired difference of $+0.641 \pm 0.145$ (`results/continuation_compare.json`).
The mechanism is measured too: the heuristic needs 181 plies to finish a position
the engine finishes in 26.

So the regression is being re-run against a target that is no longer flat. What
that does to the *weights* is unknown, and what the weights do in *play* is what
this document is about.

## The fit is not chosen

**The fit uses every position the v2 rollout pass has completed at the moment
the duel queue drains, and no other.** Fixed here, in advance, because the
alternative is poisonous: fitting at 300 positions, looking at the weights,
deciding they look wrong and waiting for 600 more is selection on the training
set, and it would make the validation duel below a test of a vector that was
chosen for looking promising.

The fit itself is estimation, not inference. It has no p-value to protect. The
**validation duel is the test**, and it is the only thing here that decides
anything.

## Hypothesis

`fishbot4(opponent_gamma=0.35, **learned_weights)` scores a positive set
differential against `fishbot4(opponent_gamma=0.35)` — the v0.4 champion, which
is the identical policy with the hand-tuned weights.

The baseline is the champion, not `fishbot4()`. v0.4's own validation played
against the defaults, which carry `opponent_gamma = 0.0`; that is a weaker
opponent than anything this project ships, and it is not the comparison that
decides whether learned weights are worth adopting.

## Effect size assumed for sizing

**+0.15 sets per deal-pair**, the same minimum interesting effect used for the
belief-space search, the sampling budget and the at-ask run, and for the same
reason: it is roughly what the already-shipped search delivers.

The previous attempt's $-2.183$ sizes nothing. It is not an estimate of this
effect — it was measured on a different target, a different baseline and a
different fit — and using it would be borrowing a number from an experiment that
no longer applies.

## Design, and its stated limit

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds throughout.
- Per-pair standard deviation **3.8**: an ask-weight change alters decisions
  constantly, so this is the high-divergence regime where the A/A figure is the
  right one. (`results/pair_sd_model.json` — and unlike the claim-threshold run,
  this contrast sits inside the range that model was measured over.)
- **MDE at 80% power is 0.238**, which is *above* the +0.15 threshold, and this
  is stated here rather than discovered afterwards.

  2000 pairs resolves the outcome that matters most: a repeat of the previous
  catastrophe. A $-2.18$ would be visible at nine standard errors. What it
  cannot do is separate a small positive from zero. **An interval containing
  zero will therefore be reported as unresolved at this size, never as a null**,
  and a larger run would need its own pre-registration rather than an extension
  of this one.

  The reason for stopping at 2000 is cost and a poor prior, not evidence: the
  line has failed once, and buying 6000 pairs before knowing whether it fails
  the same way again is not how this study's compute is best spent.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 2 blocks. The learned weights are
**demonstrated better** if and only if the 95% interval lies entirely above
zero, and **demonstrated worse** if it lies entirely below.

**Homogeneity.** Cochran's $Q$ across the 2 blocks, diagnostic only.

**Reported alongside, not decisive.** v0.4's $-2.183$, labelled as the different
experiment it was; and the fitted weight vector next to the incumbent, so a
reader can see which terms moved.

## Committed in advance

- No block excluded for its result; no block added to chase significance.
- Only the **pinned-$p$** weight vector is played. v0.4 validated three variants
  and reported the best, which is a maximum over three noisy arms; taking one
  fixed in advance removes that. The other variants may be computed and
  reported, and may not be substituted into this test.
- A demonstrated improvement does **not** move a default by itself. It earns a
  replication on fresh seeds first, for the reason the whole study keeps
  restating: this line has already produced one confidently-argued result that
  did not survive contact with a control.
