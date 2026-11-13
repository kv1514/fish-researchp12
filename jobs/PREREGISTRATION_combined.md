# Pre-registration: is the shipped configuration worth what the chain says?

Written **before any pair of this run has been played**, with the estimate it
tests already fixed and recorded in `results/combined_estimate.json`.

## What is being tested, and why a chain is not enough

`V04_COMBINED` — 480 posterior draws plus the depth-3 belief-space search — is
what `api/_engine.py` serves to every visitor. Its value against the champion is
currently known only **indirectly**, by chaining two pre-registered runs that
share no deals:

| link | estimate | pairs |
|---|---|---|
| 480 draws vs champion | +0.340 ± 0.049 | 6000 |
| search on top of 480 draws | +0.072 ± 0.042 | 6000 |
| **chained** | **+0.411 ± 0.064** | 12000 |

A chain inherits both links' assumptions. The one that matters here is that each
change's effect does not depend on the deal population the other was measured
over — plausible, since both pools were drawn the same way, and *unmeasured*.
This project's recurring failure is exactly that: a plausible unmeasured step
carrying a published number.

There is also a cheaper reason. **Nobody has ever played the shipped
configuration against the reference in a single duel.** Every "vs champion"
number in this paper is for a spec that is not the one on the website.

## The prediction, stated before the data

The chained estimate is **+0.411, 95% CI [+0.285, +0.538]**. This run is a
prediction test, not a fishing expedition, and there are three outcomes fixed in
advance:

- **agrees** — the direct interval overlaps [+0.285, +0.538]. The chain is
  vindicated and the indirect caveat can be dropped from the paper.
- **lower** — the direct estimate sits below +0.285. Then the two changes
  interact negatively and the chain over-states the combination; the paper keeps
  the direct number and reports the chain as refuted.
- **higher** — above +0.538. Then they interact positively, which would be the
  more surprising result and earns a replication rather than a paragraph.

## Sizing

Per-pair sd is taken as the **A/A 3.796** here rather than from the divergence
model. That is deliberate and conservative: the divergence model is calibrated
on arms that differ by one knob, and this arm differs by two, so its divergence
share is not one the model has ever been fitted for. Using the A/A figure asks
for more pairs than needed rather than fewer.

- **2 blocks × 1000 pairs = 2000 duplicate deal-pairs**, fresh seeds
  (base 27 000 000 and 27 200 000), checked by `scripts4/check_seeds.py` against
  every recorded and queued cell.
- **MDE at 80% power ≈ 0.238**, against a predicted +0.411. Comfortable.
- A 95% half-width of ≈ 0.166, so the direct interval will be wider than the
  chained one. **This run cannot make the estimate more precise; it can only
  make it honest.** That is the whole point and it is stated here so a wider
  interval is not read afterwards as a disappointment.

## Analysis, fixed in advance

**Primary.** Fixed-effect pool of the 2 blocks; the estimate and its 95%
interval, against the chained prediction above.

**Homogeneity.** Cochran's *Q* across the 2 blocks, diagnostic only.

**The contrast that matters.** Direct minus chained, with the two standard
errors combined in quadrature. The chain is refuted if that difference excludes
zero.

## Committed in advance

- No block excluded for its result; no block added to chase anything.
- Whatever this says, `V04_COMBINED` and the website's spec do **not** change on
  it. This measures what ships; it does not choose what ships.
- If the direct and chained estimates disagree, the **direct** one is reported
  as the headline and the chain is reported as refuted — not averaged with it,
  and not quietly dropped.
