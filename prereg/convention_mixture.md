# Pre-registration: is the flat decode weight mis-specified, and does the fix show?

**Registered 2026-08-29, before the mixture decoder was run at any size.** What
had been read when this was written: the flat-weight arms of
`results/convention_posterior.json` at sender gates 0.02 and 0.05 (the 0.10 gate
was still running), and the mechanical diagnostics recorded in
`prereg/convention.md`. No mixture number of any kind existed.

## The observation this is built on

The flat decoder adds `beta` to a world's log-weight when the card the teammate
named is the card the convention would have named from that world's holding, and
nothing otherwise. Measured over 40 games at two sender gates, it does something
very specific:

| beta | dNLL (team) | dtop-1 (team) |
|---|---|---|
| 0.25 | **-0.0069** [-0.0085, -0.0052] | +0.0002 [-0.0045, +0.0050] |
| 0.50 | **-0.0098** [-0.0129, -0.0066] | -0.0047 [-0.0108, +0.0014] |
| 0.80 | -0.0085 [-0.0134, -0.0036] | **-0.0127** [-0.0197, -0.0058] |
| 1.20 | +0.0002 [-0.0072, +0.0076] | **-0.0200** [-0.0277, -0.0124] |
| 2.00 | +0.0372 [+0.0238, +0.0507] | **-0.0302** [-0.0385, -0.0219] |

(sender gate 0.05; the 0.02 gate replicates it.) **Top-1 decays monotonically in
`beta`**, and is significantly negative from 0.8 up, while NLL turns around at
0.5. The belief is being made better-calibrated and worse at naming the holder,
which is the exact signature that refuted the split gamma --- and for an engine
whose dominant error is *naming a split*, the argmax is the quantity that pays.

## The claim: this is a specification error, not a property of the channel

Write the likelihood of the observed card `c` given the half-suit and a
candidate world `w`, and let `k(w) = 6 - held(w)` be the number of cards the
asker could legally have named under that world:

    P(c | w) = q * 1[c == enc(w)] + (1 - q) * u(c | w)

with `q` the sender's carry rate --- **measured, not fitted**: 0.529 at gate
0.02, 0.629 at 0.05 --- and `u` the unencoded card choice, modelled as uniform
over the `k(w)` legal cards. Then

    log-odds of a match against a non-match  =  log(1 + q*k/(1-q))

**which grows with `k`.** A match is weak evidence when the asker holds five of
the six and had one legal card to name; it is strong evidence when they held one
and had five. The flat weight scores every match at `beta` regardless, so it
systematically over-credits matches in **low-k worlds --- the worlds where the
teammate is deep**. Raising `beta` raises that bias proportionally. That is a
mechanism which predicts precisely the observed top-1 decay, and it predicts it
in the right variable.

The mixture also uses the non-matches, which the flat weight discards entirely:
`log((1-q)/k)` still varies with `k`.

## Design

Identical to `prereg/convention.md` --- same transcripts, same pools, same
pairing by decision, same instrument --- with the receiver arm swept over `q`
instead of `beta`. Both decoders are scored on the **same** positions in the
same run, so the comparison between them is paired too.

**Arms.** `convention_q` in {0.4, 0.5, 0.6, 0.7, 0.8}, alongside the existing
`convention_beta` arms, against a shared `beta = q = 0` baseline.

`q = 0` means **no agreement exists** and the term is skipped. That is
deliberately not the `q -> 0` limit of the formula: with no agreement the card
choice is the objective's, not uniform, so neither branch of the mixture
describes it.

## Decision rule, fixed in advance

The mixture **supersedes the flat weight** only if, on the teammate pool:

1. its best arm satisfies both gates of `prereg/convention.md` --- paired NLL
   interval entirely below zero, paired top-1 interval not entirely below zero
   --- **and**
2. its best arm's paired NLL point estimate is **at least as negative** as the
   best flat arm's.

**The mechanistic test, which is the one this document exists for.** The
argument above says the top-1 damage is the missing `1/k`, and the mixture has
**no strength parameter to grow**: `q` is a probability, bounded, and measured.
So the prediction is

> **the mixture's top-1 curve is flat in `q`, where the flat weight's is
> monotonically decreasing in `beta`.**

Registered as a falsifiable prediction with a criterion: over the five `q` arms,
the spread of `dtop-1` must be **less than half** the spread over the four flat
arms at `beta <= 1.2` (which is 0.0202). If the mixture's top-1 also decays
monotonically, **the `1/k` explanation is wrong** and the damage is coming from
somewhere else --- most plausibly that `u` is not uniform, because the unencoded
choice is made by an expected-value objective that prefers particular cards.
That would be a more interesting result than the fix working, and it would point
at modelling `u` with the objective rather than with a constant.

## Withdrawal conditions

* If the mixture's NLL is worse than the flat weight's at every `q`, the extra
  structure is not earning its inner-loop cost and the flat weight stands.
* If the best `q` is at a boundary of the grid, the grid is widened and the run
  repeated before anything is read into the location of the optimum.
* If the best `q` is far from the measured carry rate (outside 0.4-0.8, i.e. the
  grid), then `q` is behaving as a free strength parameter rather than as the
  probability it is defined to be, and the mixture is reported as a
  reparameterised heuristic rather than as a likelihood.

## What this ships

Nothing. Both decoders are scored off-policy, with the decoder off during play,
so this measures whether the message decodes and not whether a team running both
sides plays better. A pass licenses a duel, registered separately.
