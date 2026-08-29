# Pre-registration: is there a richer teammate choice model worth building?

**Registered 2026-08-29, before the `unlocated_now` fit was read.** The corpus
regeneration was running when these conditions were fixed; nothing from it had
been looked at.

## The claim

Our teammates run our policy, and we possess it. So the ceiling on predicting a
teammate's ask is not "how good is a depth heuristic" but "how close can a cheap
surrogate get to the policy that actually generated the choice".

The shipped model uses one covariate: the asker's depth in the half-suit. The
paper motivates a second one and then never tests it —

> under an objective dominated by P(success), what makes a half-suit attractive
> to ask in is not depth but the number of missing cards it offers: holding five
> of six leaves exactly one card to ask for, holding one of six leaves five.
> Those pull opposite ways.

— because the covariate it appeals to was never recorded.

## What was already established before this registration

Two things, both from `scripts4/choice_basis.py` on the existing corpus:

1. **The fit replicates the paper.** Held out at the game level over 17,005
   choices: the shipped initial-deal covariate is worth **+1,400** nats over
   uniform (paper: 1,403) and at-ask-time depth **+6,055** (paper: 6,057). The
   instrument agrees with the published numbers to within rounding, which is
   what licenses using it to judge anything new.

2. **`missing_now` is not a second covariate.** It counts the cards of the
   half-suit *not in the asker's hand*, which under these rules is exactly
   `6 - held` — verified over **72,091 alternatives with no exception**. So the
   paper's "those pull opposite ways" cannot be tested with it: a model using
   both fits one variable twice, and the +68 nats such a model gains over
   at-ask depth is curvature in the shape of `f(held)`, not information. It is
   retained as a labelled control, and `collinearity_report()` now fails loudly
   on any feature that is a deterministic function of another.

The covariate the argument actually needs is **`unlocated_now`**: how many cards
of the half-suit are still sitting with nobody the public record can name. A
card already pinned to a player is not an opportunity to anyone. It has been
added to the recorder, it varies freely at every value of `held` (four to six
distinct values), and it is common knowledge — which is what would make it
usable inside the sampler rather than only inside a fit.

## Design

**Instrument.** `scripts4/choice_basis.py` on a regenerated 200-game self-play
corpus. Conditional logit over the legal half-suits actually offered, scored by
**held-out** log-likelihood with folds at the **game** level: asks inside one
game share a deal, a policy realisation and a seed, so an ask-level fold leaks.

**Models.** M0 uniform · M1 `depth0^a` (shipped) · M2 `held^a` · M3
`held^a missing^b` (control) · M4 `unlocated^a` · M5 `held^a unlocated^b` ·
M6 `held^a unlocated^b depth0^c`.

**Primary outcome.** Held-out nats of **M5 over M2** — the gain from adding
opportunity to at-ask depth. M2, not M1, is the reference: the question is
whether a *second covariate* is worth carrying, and comparing against the
weaker shipped covariate would let a known result masquerade as a new one.

## Decision rule, fixed in advance

Let `D = cv_loglik(M5) - cv_loglik(M2)`, held out, in nats over ~17,000 choices.

* **D < 200** → **withdraw.** Below roughly 0.012 nats per choice, the second
  covariate is not carrying enough to justify a per-world computation in the
  sampler's inner loop. Nothing is built.
* **200 ≤ D < 1,000** → **build the fit, not the engine.** Record it as a
  measurement of the choice model and stop. It does not earn a place in the
  posterior on this evidence alone.
* **D ≥ 1,000** → **licensed to build** into `oppmodel.py` behind an inert
  default, followed by the posterior-accuracy instrument used for the split
  gamma (`scripts4/gamma_split.py`), under its own pre-registration with **both**
  an NLL and a top-1 criterion. Nothing ships on a fit alone.

The 1,000-nat bar is set at roughly a fifth of what changing the covariate from
initial-deal to at-ask depth was worth (4,654 nats). A second covariate that
cannot reach a fifth of a covariate swap is not the thing standing between this
engine and the teammate ceiling.

## Withdrawal conditions

* If `collinearity_report()` finds `unlocated_now` determined by any other
  recorded feature, the whole comparison is void and the result is a corpus
  defect, not a finding.
* If M4 (`unlocated` alone) beats M5, the fit is unstable and is re-run before
  anything is read into it.
* If M5's fitted coefficient on `unlocated` has an inconsistent **sign** across
  the five folds, it is noise and the direction is withdrawn regardless of D.
* If the regenerated corpus does not reproduce M1 and M2 to within 50 nats of
  the values above, the recorder change perturbed the games and the run is void.

## What a null would mean

That the ask choice really is a function of depth alone, to the accuracy a
one-parameter family can express, and that the "opportunity" story the paper
tells is not a second force but a restatement of the first. That would close the
cheap route to the teammate ceiling and leave only the expensive one: evaluating
the policy itself per candidate world, which costs a nested posterior per world
per ask and is out of reach of the sampler's inner loop by orders of magnitude.

In that case the honest conclusion is that the teammate value measured by the
ceiling split is **not reachable through the choice model at all**, and the
remaining lever is the declaration policy rather than the belief.
