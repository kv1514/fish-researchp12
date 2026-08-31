# Pre-registration: is "the effect grows with draws" the channel, or the instrument?

**Registered 2026-08-31, immediately after `prereg/channel_vs_precision.md`
returned REFUTED, and before any run of a second intervention across `n_draws`.**
What has been read: `results/channel_precision.json` in full, and
`results/unlocated_belief.json`'s w = -4.0 row (+0.0422 [+0.0339, +0.0505] NLL
at `n_draws = 480`, clustered by game).

## The claim this is checking is my own, and it is an hour old

> **NOTE added 2026-08-31.** The gap that started this whole sequence was
> later bisected to a gate re-pricing, not a change in the engine's belief
> (`results/convention_drift_bisect.json`). This registration's own result is
> unaffected --- it compares two arms on one set of transcripts --- and it is
> the one that establishes the scaling is an instrument property rather than
> a fact about code books.

The channel-precision sweep found the aimed book's paired NLL gain growing with
sampler draws --- a null at 180, -0.0436 at 1440 --- while the baseline belief
stopped improving after 720. I wrote, in three files, that this means the gain

> tracks **how many sampled worlds the decoder has to reweight**.

There is a duller explanation that sweep cannot distinguish: **any paired
difference between two beliefs may grow with draws**, because at low precision
both marginals are coarse and there is simply less room for the arms to differ.
If that is so, the sentence above is over-read: it would be a property of the
instrument, true of every intervention, and not a fact about code books at all.

The two are distinguishable by running the same sweep on an intervention that
has nothing to do with a code book.

## The intervention

`w_unlocated = -4.0` against the incumbent `0.0`, on the champion's own
transcripts with no convention anywhere. Chosen for three reasons:

* it is **structurally unrelated** to the channel --- it reweights the opponent
  model's slots by how many cards of a half-suit the public record cannot
  place, and no message is involved;
* its sign is **opposite**. It is a *harm* (+0.0422 NLL at 480 draws), so
  "grows with draws" here means the harm gets worse, and a shared mechanism has
  to explain both signs;
* it was **refuted today** on its own pre-registered rule, so nothing rides on
  the answer and there is no arm to protect.

## Design

`scripts4/precision_generality.py`, importing `Pool`, `paired_by_game` and
`true_holder_map` from `scripts4/unlocated_belief.py` and mirroring its
transcript loop exactly: play is always the incumbent, seed base **720,000**,
40 games, stride 4, truth used only to score, the same two disjoint pools,
one RNG seed per decision shared by every arm and every cell.

* **Cells.** `n_draws` in **{180, 360, 480, 720, 1440}**.
* **Arms.** `w_unlocated` in {0.0, -4.0}, the second paired against the first
  within each cell.
* **Clustering.** By game, `fish4.clustered.cluster_ci`, floor 8 clusters.
* **Anchor.** The **480** cell must reproduce `results/unlocated_belief.json`'s
  **+0.0422** to within **0.010**. That is the precision that file was written
  at, so this is a real reproduction and not a courtesy.

## The statistic, identical in form to the sweep it is checking

    d_c(i) = NLL_arm(i) - NLL_base(i)      within cell c; POSITIVE is harm here
    D(i)   = d_1440(i) - d_180(i)          clustered on the game

The convention's gain was negative and grew more negative, giving D < 0. This
arm's effect is positive, so a **shared instrument property predicts D > 0**:
the same "more draws, bigger effect" in the direction this arm points.

## Decision rule, fixed in advance

* **INSTRUMENT PROPERTY** if D's interval lies entirely **above** zero. The
  magnitude of an unrelated, opposite-signed effect also grows with draws, so
  "more worlds to reweight" is not a fact about the channel and the sentence in
  three files is over-read.
* **SPECIFIC TO THE CHANNEL** if D's interval lies entirely **below** zero, or
  covers zero. An unrelated intervention that does not grow with draws leaves
  the channel's growth as something about the channel.
* **VOID** if the 480 anchor misses by more than 0.010, or if fewer than 8 game
  clusters contribute.

Note the asymmetry, which is deliberate: covering zero counts **for** the
channel-specific reading. That is the harder assignment for my own claim to
survive, because a null here is weak evidence and it is being allowed to
support me. If even that fails, the over-reading is not arguable.

## Sample size

**40 games, stride 4, no extension.** Matching both runs this is comparing, so
all three are on the same footing, and k = 40 clusters against a floor of 8.

## What this licenses

Nothing ships; `w_unlocated` stays at its inert default either way and the
convention direction is already closed by its duels.

* **INSTRUMENT PROPERTY** and the "worlds to reweight" sentence is weakened
  wherever it appears --- `RESEARCH_FRONTIER.md`,
  `prereg/channel_vs_precision.md`, `fish4/convention.py` --- and replaced with
  the instrument reading. The REFUTED verdict of the sweep is untouched by
  this: that was about whether the gain shrinks, and it does not, whatever the
  reason.
* **SPECIFIC TO THE CHANNEL** and the sentence stands, with this run cited as
  the reason it is not merely an artefact.

---

# OUTCOME, recorded 2026-08-31: INSTRUMENT PROPERTY

**An unrelated, opposite-signed intervention also grows with draws.** 40 games,
1,027 scored decisions, `results/precision_generality.json`.

| `n_draws` | baseline team NLL | paired team NLL (+ is harm) | paired opp NLL |
|---|---|---|---|
| 180 | 1.2972 | +0.0371 [+0.0293, +0.0448] | +0.0293 [+0.0233, +0.0353] |
| 360 | 1.2777 | +0.0400 [+0.0324, +0.0476] | +0.0336 [+0.0277, +0.0394] |
| 480 | 1.2728 | **+0.0422** [+0.0339, +0.0505] | +0.0349 [+0.0291, +0.0407] |
| 720 | 1.2689 | +0.0435 [+0.0355, +0.0515] | +0.0381 [+0.0318, +0.0444] |
| 1440 | 1.2658 | +0.0465 [+0.0376, +0.0553] | +0.0402 [+0.0333, +0.0471] |

    D = d_1440 - d_180 = +0.0094 [+0.0016, +0.0172]    k = 40 games

Entirely above zero. By the rule fixed in advance this is **INSTRUMENT
PROPERTY**: *"more worlds to reweight" is not a fact about the channel and the
sentence in three files is over-read.*

## The anchor reproduced exactly

The 480 cell measures **+0.042197** against `results/unlocated_belief.json`'s
**+0.0422** --- off by **0.0000**. Different instrument, same seeds, same seed
expression, same number.

Both sweeps run today have now landed on their anchor to four decimal places.
That is worth stating once: the reason these contrasts can be believed is that
each was made to reproduce a published figure before it was allowed to report a
new one.

## The magnitudes are not the same, and that does not rescue the claim

| | at 180 draws | at 1440 | growth | as % of its own end effect |
|---|---|---|---|---|
| aimed code book | -0.0064 (a null) | -0.0436 | **0.0372** | **85%** |
| `w_unlocated = -4.0` | +0.0371 | +0.0465 | **0.0094** | **20%** |

The channel's growth is **4x** the unrelated arm's in absolute nats, and four
times larger again as a fraction of the effect it ends at. So the two are not
the same phenomenon in size, and something beyond the shared instrument effect
is happening to the channel.

**That observation does not reinstate the sentence, and is not allowed to.**
The registration asked one question --- does an unrelated intervention also grow
with draws --- and the answer is yes, with an interval excluding zero. A
size difference noticed afterwards is exactly the kind of post-hoc rescue the
pre-registration exists to refuse. What can be said is: growth-with-draws is
**not** specific to the channel; the channel grows several times more than the
shared effect accounts for; and **this run does not explain why**. That is a
lead, not a finding, and by the standing rule recorded under #49 it does not get
quoted as one.

## What is untouched

The REFUTED verdict of `prereg/channel_vs_precision.md` stands entirely. That
run asked whether the gain *shrinks* as the belief improves, and it does not ---
whatever the reason it grows. Nothing here bears on it.

So does the practical caveat: the engine ships at `n_draws = 480` and the
convention's belief figures were all scored at 720. This run adds that the same
is true in the other direction --- `results/unlocated_belief.json` was written
at 480 while the convention files were written at 720, so those two directions
were never scored at the same precision and their magnitudes were never directly
comparable.

Per the licensing clause above, the "worlds to reweight" sentence is weakened
in `RESEARCH_FRONTIER.md`, `prereg/channel_vs_precision.md` and
`fish4/convention.py`.
