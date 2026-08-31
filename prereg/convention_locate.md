# Pre-registration: should a code book carry a location instead of a count?

> **AMENDED 2026-08-29, before this book was run: THE PREMISE BELOW IS
> RETRACTED.** This document argues from "aiming should have won and did not".
> That reading came from a 70-decision probe using the mixture at `q = 0.6`,
> interval +-0.0652. At 40 games with the flat weight, aiming is the largest
> result in this direction: NLL **-0.0712** [-0.0803, -0.0621] and top-1
> **+0.0351** [+0.0258, +0.0444] at `beta = 0.8`. It did win.
>
> So the "a count constrains, only a location pins" argument is **not supported
> by the evidence it was built on**. It is left standing below, unedited, as the
> record of a hypothesis formed from an underpowered null.
>
> The locating book is still worth measuring --- it locates a mean of 2.76 cards
> per decoded message where the depth books locate none, which is a fact about
> the code book and not about the retracted comparison --- but it is now a
> question in its own right rather than a fix for a failure that did not happen.
> Its gates below are unchanged, except that condition 2 now compares against
> the **aimed** depth book, which is the incumbent it would have to beat.

**Registered 2026-08-29, before the locating book was measured on any
posterior.** What had been read: the mechanical checks below, and the
flat/mixture arms of the 40-game instrument at sender gate 0.02. No NLL or
top-1 number for this book existed.

## The claim

Three code books have now been built on the same channel --- the free choice of
which card to name, worth 1.72 bits an ask. Two carry a **count**:

* `depth` --- the asker's depth in the half-suit they asked in;
* `aimed` --- the asker's depth in the most-unlocated half-suit, chosen for
  having **4.03x the entropy** (0.8556 nats against 0.2124, and the receiver is
  already certain of the first 72.2% of the time against 9.7% of the second).

Aiming should therefore have won, and it did not. The round trip rules out the
obvious explanation: sender and receiver agree just as well aimed as unaimed
(74.7% decode-under-truth against 74.9%), and the aimed book discriminates
strictly more worlds (V2 48.8% against 30%). It simply did not move the belief.

**The asymmetry entropy does not see.** `is_encoded` under the `depth` book is a
function of the asker's **exact holding**: two holdings of the same depth have
different free sets and so name different cards. The `aimed` book's payload is
`depth in G`, a **pure count**: two worlds that give the asker the same number
of G's cards are not separated at all, however differently they place them. So
aiming did not add a signal --- it **traded a locating one for a counting one**.

Cards are scored one at a time. A count constrains the joint; only a location
pins a card. And what this engine's residual errors need is exactly a pin: 95.3%
of them are allocation errors, our team holding all six of a half-suit and
naming the wrong split.

## The locating book

Both sides take `U`, the unlocated cards of the target half-suit in index
order --- public, and snapshotted at the ask like every other target --- truncated
to the `k` cards the ask has to choose between. The message is

    j = the index in U of the FIRST card the asker holds, or k - 1 if none

sent by naming the `j`-th legal card. A partner who reads it learns that the
asker does **not** hold `U[0..j-1]` and **does** hold `U[j]`: `j` negatives and
a positive, `j + 1` cards located, from an ask that was happening anyway.

## Mechanical checks, run before this registration

Not outcomes. Each has a yes/no answer and each is a way the build could be
silently broken.

| check | result |
|---|---|
| bit-identical at zero weight | 12/12 positions |
| moves a real posterior | 8/12 |
| is a different book from `depth`, not a rename | 5/12 |
| receiver decodes a match under the TRUE deal | 513/797 = **64.4%** |
| **cards located by a decoded message** | **mean 2.76, median 3, max 5** |

The last row is the design's whole point, and the depth books' value for it is
**zero**: a count locates nothing.

The decode rate is lower than the `depth` book's 74.9%, which is expected and
is the price of a wider payload: `j` ranges over `k` values where a depth
effectively ranges over fewer, so more of the message survives the modulus and
less of it agrees with the objective's own preference by luck.

## Design

Identical to `prereg/convention.md` --- same instrument, same transcripts-per-
sender, same pools, same pairing by decision, decoder book always matching the
sender's. Sender gate 0.05, the middle of the three, plus 0.02 as a replication.

**Arms.** `convention_beta` in {0.25, 0.5, 0.8, 1.2, 2.0} with
`convention_book = "locate"`, against a shared inert baseline.

The mixture is **not** carried. It was refuted on its own withdrawal condition
in `prereg/convention_mixture.md` --- worse NLL at every `q` --- and re-running a
refuted parameterisation on a new code book would be fishing.

## Decision rule, fixed in advance

The locating book **supersedes the depth book** only if, on the teammate pool:

1. its best arm satisfies both gates of `prereg/convention.md` --- paired NLL
   interval entirely below zero, paired top-1 interval not entirely below zero
   --- **and**
2. its best arm's paired **top-1** point estimate is **at least as good** as the
   best passing depth arm's --- which, per the amendment above, means the
   **aimed** depth book at `beta = 0.8`: **+0.0351**. That is a far higher bar
   than the one this condition was written against, and deliberately so: the
   incumbent is no longer a book that fails.

Condition 2 is on top-1, not NLL, and that is deliberate. The argument for this
book is that it pins cards rather than counting them, and the quantity that
reads a pin is the argmax. If it wins on NLL while losing on top-1 it has not
done the thing it was built to do, whatever the proper score says.

## Withdrawal conditions

* If the best arm is at a grid boundary, the grid is widened before anything is
  read into where the optimum sits.
* If the book's decode-under-truth rate falls below 40% in the scored
  transcripts, the message is not arriving often enough for a null to mean
  anything about the design, and the run is void rather than negative.
* If it fails to differ from the `depth` book on more than a third of scored
  decisions, the two books are not distinguishable on this instrument and the
  comparison is reported as underpowered rather than as a result.

## What a null would mean

That 1.72 bits an ask is not enough to carry a location worth having, even
though it demonstrably carries ~2.76 located cards per decoded message. That
would put the ceiling on this whole direction at the channel's width rather
than at the code book's design, and the next question would stop being "what
should an ask say" and become "how many asks can be made to say it" --- i.e.
back to the turn-spending signalling channel, which is measured at
+0.122 [+0.029, +0.215] sets/game and was declined only against a +0.15 bar.

## What this ships

Nothing. Scored off-policy with the decoder off during play, so it measures
whether the message decodes into a better belief, not whether a team running
both sides plays better. A pass licenses a duel, registered separately.

---

# OUTCOME, recorded 2026-08-29

**The locating book clears its gate**, at both sender settings, with the
strongest top-1 of any book measured.

| gate | arm | teammate NLL | teammate top-1 |
|---|---|---|---|
| 0.02 | flat 0.25 | -0.0258 [-0.0313, -0.0204] | +0.0232 [+0.0150, +0.0314] |
| 0.02 | flat 0.5 | **-0.0302** [-0.0396, -0.0208] | +0.0254 [+0.0155, +0.0353] |
| 0.05 | flat 0.25 | -0.0282 [-0.0365, -0.0198] | +0.0289 [+0.0199, +0.0378] |
| 0.05 | flat 0.5 | **-0.0315** [-0.0469, -0.0162] | **+0.0408** [+0.0303, +0.0512] |

Against the amended condition 2 --- top-1 at least as good as the **aimed** depth
book's +0.0351 --- the best passing arm gives **+0.0408**, which clears it. Both
gates pass. Validity: V1 62.4%/69.6%, V2' 29.5%/26.5%, V3 91.9%/94.5%.

It is worth being precise about what did and did not happen, given this
document's history. The *reason* it was built --- that aiming had failed and a
location was needed to rescue it --- **was wrong**, and is retracted at the top.
The book itself works anyway, on its own registered criteria.

Its NLL (-0.0315) is smaller than the aimed depth book's (-0.0535); its top-1
(+0.0408) is larger (+0.0392). Its arms also degrade faster: at `beta = 1.2` its
NLL is already significantly *positive* (+0.0339) where the aimed depth book is
still negative, which is what a wider, more aliased payload should look like.

## The pattern across all four books, which is the finding

| book | teammate NLL | teammate top-1 |
|---|---|---|
| depth, unaimed, gate 0.10 | -0.0317 | **-0.0049** |
| depth, aimed | **-0.0535** | +0.0392 |
| locate (aimed by construction), 0.02 | -0.0302 | +0.0254 |
| locate (aimed by construction), 0.05 | -0.0315 | +0.0408 |

**Every book that aims at the most-unlocated half-suit improves top-1; the one
that does not, does not.** Whether the payload is a depth or a location barely
matters beside that. The variable that buys the argmax is *where the message
points*, not *what it says* --- which is the opposite of the hypothesis this
document was written to test, and is only visible because the book was built
and measured anyway.

---

# REPRODUCTION, recorded 2026-08-31: condition 2 no longer passes

**The outcome above is reversed on the current engine, by the rule this
document fixed in advance.**

## The run above committed no results file

`f8abe6d` recorded this OUTCOME and touched this document,
`prereg/convention_aimed.md` and a duels JSONL --- no results file. Its figures
existed in this repository only as prose. `results/convention_replication.json`
is the re-run that closes that; see the matching section in
`prereg/convention_aimed.md` for why the magnitudes moved.

## Re-run, seed base 880,000, 40 games, stride 4

| gate | arm | teammate NLL | teammate top-1 |
|---|---|---|---|
| 0.02 | flat 0.25 | -0.0161 [-0.0206, -0.0116] | +0.0104 [+0.0034, +0.0174] |
| 0.02 | flat 0.5 | **-0.0184** [-0.0266, -0.0103] | +0.0196 [+0.0100, +0.0293] |
| 0.05 | flat 0.25 | -0.0224 [-0.0271, -0.0178] | +0.0196 [+0.0121, +0.0270] |
| 0.05 | flat 0.5 | **-0.0284** [-0.0366, -0.0202] | **+0.0227** [+0.0141, +0.0312] |
| 0.05 | flat 0.8 | -0.0192 [-0.0315, -0.0069] | +0.0158 [+0.0061, +0.0255] |

Validity: V1 48.9%/58.1% (floor 25%), V2 amended 26.4%/23.0% (floor 20%),
V3 92.5%/93.7% (floor 50%). Nothing voids.

**Both gates of `prereg/convention.md` still pass**, at both sender settings.
The book is not refuted as a channel: it still decodes into a better belief and
it still improves the argmax.

## Condition 2 fails

The decision rule above says the locating book supersedes the depth book only
if its best passing arm's top-1 point estimate is **at least as good as** the
aimed depth book's. On the same engine, the same seed base and the same run:

| | top-1 |
|---|---|
| aimed depth book, `beta = 0.8` | **+0.0260** [+0.0164, +0.0356] |
| locating book, best passing arm (gate 0.05, `flat 0.5`) | **+0.0227** [+0.0141, +0.0312] |

+0.0227 is not at least +0.0260, so **condition 2 fails and the locating book
does not supersede**. Against the literal bar the amendment wrote down
(+0.0351, the exploratory aimed figure) it fails by more. Both readings agree,
which is the useful part: the outcome does not depend on which of the two bars
is meant.

Two things must be said against this, and neither rescues it:

* **The comparison is unpaired.** Each sender setting plays its own games, so
  the two books are not scored on shared positions; this document's design
  section flagged that from the start. The gap (0.0033) is far inside the
  overlap of the two intervals.
* **The rule is on point estimates, deliberately.** It was written that way
  because "at least as good as" needs an orderable quantity, and it was fixed
  before either number existed. A rule that only bites when it is comfortable
  is not a rule.

So the honest reading is not "the locating book lost". It is that **it never
beat the aimed depth book by more than noise in either direction**, its
apparent win came from a run that no longer reproduces, and by its own
pre-registered criterion it does not earn the supersession it was written to
claim.

## What this leaves standing

The finding recorded above --- that what buys the argmax is *aiming*, not the
payload --- is not weakened by this; it is sharpened. Two books that aim, one
carrying a count and one carrying a location, are indistinguishable from each
other and both beat the book that does not aim. The variable that mattered was
never the one this document was written to test.
