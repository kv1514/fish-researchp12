# Pre-registration: is "the effect grows with draws" the channel, or the instrument?

**Registered 2026-08-31, immediately after `prereg/channel_vs_precision.md`
returned REFUTED, and before any run of a second intervention across `n_draws`.**
What has been read: `results/channel_precision.json` in full, and
`results/unlocated_belief.json`'s w = -4.0 row (+0.0422 [+0.0339, +0.0505] NLL
at `n_draws = 480`, clustered by game).

## The claim this is checking is my own, and it is an hour old

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
