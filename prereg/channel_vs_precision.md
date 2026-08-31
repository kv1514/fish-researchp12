# Pre-registration: does the channel's value shrink as the belief improves?

**Registered 2026-08-31, before any run at any `n_draws` other than 720, and
before the instrument below exists.** What has been read: the five sender
settings of `results/convention_replication.json`, all at `n_draws = 720`, and
the two-point engine-drift comparison recorded the same day in
`prereg/convention_aimed.md`.

## Why this exists: I asserted a mechanism from two confounded points

Re-running the aimed code book today produced a smaller effect than the one
recorded two days earlier on identical seeds --- paired NLL at `beta = 0.8`
went from -0.0712 to -0.0403 --- while the *baseline* teammate NLL improved
from 1.3995 to 1.3567. I wrote, in `RESEARCH_FRONTIER.md`, in
`prereg/convention_aimed.md` and in `fish4/convention.py`:

> The decode did not get worse. The belief it decodes into got better, and a
> message is worth only what the receiver could not already work out.

That is a mechanism, stated from **two points, on two engines, differing by
eleven commits**. It is the most quotable sentence I wrote today and the least
supported. It is exactly the shape of the claim this project has had to retract
before --- the aimed book's own "neutral" reading was a theory built on one
underpowered comparison --- so it gets a test before it gets repeated again.

## What this tests, and what it does not

The manipulation here is the **scoring posterior's sample count**, `n_draws`.
More draws means a lower-variance belief on the same positions, so the baseline
gets better without the model changing.

That is a **different axis** from the one the drift was on. The engine drift
was a model improvement --- calibration work, a different action model --- not
more draws. So a result here does not directly confirm or refute the drift
explanation. What it does is ask whether the *general* form of the claim holds
on the one axis that can be swept cleanly and cheaply: **when the receiver's
belief gets better, is the message worth less?**

Stating that limit now, before the numbers exist, because the temptation
afterwards will be to quote whichever reading is tidier.

It is also not obvious which way this should go. More draws gives the
convention's reweighting more worlds to act on, which could make the decode
*more* effective rather than less. A null is a real possibility and so is the
opposite sign.

## Design

`scripts4/channel_precision.py`, a sibling of `scripts4/convention_posterior.py`.

* **Transcripts.** Generated once, exactly as in that instrument: sender gate
  0.05 aimed, encoder on at every seat, decoder OFF during play, seed base
  **880,000**, 40 games, stride 4. Identical to
  `results/convention_replication.json`, so the positions are the same ones
  already measured.
* **Cells.** Scoring `n_draws` in **{180, 360, 720, 1440}**. 720 is today's
  value and serves as the anchor.
* **Arm.** `convention_beta = 0.8` --- the pre-registered optimum --- against
  the shared inert baseline *within each cell*.
* **Clustering.** By **game**, through `fish4.clustered.cluster_ci`, which does
  the grouping and the t at k-1 df together. k = 40, floor 8. The existing
  convention instrument clusters by decision and understates its intervals;
  that is #83 one level in and is not inherited here.
* **Storage.** Every per-decision row is written out **with its game id**, so
  the cross-cell contrast below can be re-derived from the file without a
  re-run. `results/gamma_split.json` cannot be, and that is the reason.

## The statistic the decision rule is on

The four cells score the **same decisions**, so the comparison across cells is
paired per decision and does not have to go through two independent intervals.

For each decision `i` and cell `c`, let

    d_c(i) = NLL_arm(i) - NLL_base(i)      (negative when the decode helps)

The primary quantity is the **contrast**

    D(i) = d_1440(i) - d_180(i)

clustered by game. Gains are negative, so **D > 0 means the gain has shrunk
toward zero at higher precision** --- the direction the mechanism predicts.

## Decision rule, fixed in advance

**SUPPORTED** only if BOTH:

1. the baseline teammate NLL falls monotonically across 180 -> 360 -> 720 ->
   1440, so the manipulation did what it is for; **and**
2. the clustered 95% interval on **D** lies entirely **above** zero.

**REFUTED** if the interval on D lies entirely **below** zero: the message is
worth *more* against a better belief, which is the opposite of the claim.

**UNRESOLVED** if the interval on D covers zero, or if condition 1 fails. An
unresolved result is reported as unresolved and does not get described as
"consistent with" the mechanism.

## Withdrawal conditions

* If the `n_draws = 720` cell does not reproduce
  `results/convention_replication.json`'s -0.0382 to within +-0.010, this
  instrument is not measuring the same thing as the one that produced that
  number, and the run is **void** rather than negative.
* If fewer than 8 game clusters contribute, no interval is reported.
* If the baseline NLL is non-monotone in a way that is not a single adjacent
  near-tie, condition 1 fails and the run is unresolved rather than negative.

## Sample size, fixed here and not later

**40 games, stride 4, and no extension.** This matches the run whose numbers
motivated the question, so the two are comparable in power, and it gives k = 40
clusters against a floor of 8. If 40 games cannot resolve the contrast, that is
a finding about power and not a licence to run 80 against the same hypothesis.

## What this licenses

Nothing ships; this is scored off-policy with the decoder off during play.

* **SUPPORTED** upgrades the frontier's sentence from an assertion to a
  measurement, and it must then be stated on the axis actually swept ---
  *sampler precision* --- rather than as a general claim about belief quality.
* **REFUTED or UNRESOLVED** and the sentence gets **weakened wherever it
  appears** --- `RESEARCH_FRONTIER.md`, `prereg/convention_aimed.md`,
  `fish4/convention.py` --- to say it was asserted from two confounded points
  and that the one controlled test run on it did not support it.

That last clause is the point of registering this. The claim is mine, it is
already written into three files, and the cheapest thing to do would be to
leave it there.

---

# OUTCOME, recorded 2026-08-31: REFUTED

**The gain grows as the belief improves. It does not shrink.** 40 games, 1,068
scored decisions, `results/channel_precision.json`.

| `n_draws` | baseline team NLL | paired team NLL | paired team top-1 |
|---|---|---|---|
| 180 | 1.3155 | -0.0064 [-0.0217, +0.0090] | +0.0139 [-0.0002, +0.0281] |
| 360 | 1.3004 | -0.0300 [-0.0444, -0.0156] | +0.0154 [+0.0011, +0.0296] |
| 720 | 1.2919 | **-0.0382** [-0.0538, -0.0227] | +0.0260 [+0.0121, +0.0399] |
| 1440 | 1.2930 | **-0.0436** [-0.0593, -0.0279] | +0.0273 [+0.0136, +0.0409] |

    D = d_1440 - d_180 = -0.0372 [-0.0481, -0.0263]    k = 40 games, 1,046 decisions

D's interval lies **entirely below zero**, which the decision rule above calls
**REFUTED**: the message is worth *more* against a better-sampled belief, not
less.

## The anchor held exactly

The 720 cell measures **-0.038245** against
`results/convention_replication.json`'s **-0.0382**, off by **0.0000** on a
tolerance of 0.010. Different instrument, different clustering, same number:
this is not measuring something else.

## Condition 1, and the tie-break that was written for it

The baseline is monotone over the first three cells and then ticks the wrong
way: steps of **-0.0151, -0.0085, +0.0011** against a grid span of **-0.0224**.
That last step is a single adjacent pair differing by 5% of the span, which is
the case the withdrawal condition names --- *"non-monotone in a way that is not
a single adjacent near-tie"* --- so condition 1 does not fail and the verdict is
REFUTED rather than UNRESOLVED.

Writing that tie-break in advance is the only reason this is not a judgement
call made after seeing which reading was tidier. The rule as stated was
genuinely ambiguous between REFUTED and UNRESOLVED for this exact pattern, and
the withdrawal condition is what resolves it.

## The finding is sharper than the refutation

**The baseline saturates and the gain does not.** From 720 to 1440 the baseline
belief gets no better at all (+0.0011, noise), while the gain still grows from
-0.0382 to -0.0436. So the gain is not tracking how much the receiver already
knows.

> **AMENDED 2026-08-31, an hour later.** This paragraph originally continued:
> *"It is tracking how many sampled worlds the decoder has to reweight."* That
> second explanation was registered in `prereg/precision_generality.md` and
> **refuted**: an unrelated, opposite-signed arm (`w_unlocated = -4.0`, no
> message involved) also grows with draws, +0.0371 -> +0.0465, contrast
> +0.0094 [+0.0016, +0.0172]. Growth-with-draws is a property of the
> **instrument**, not of code books.
>
> What that run leaves unexplained is a size difference --- the channel grows
> 0.0372 nats against the unrelated arm's 0.0094, and 85% of its own end effect
> against 20% --- which is a lead and is deliberately not written up as a third
> mechanism.

At 180 draws there is **no measurable channel**: -0.0064 [-0.0217, +0.0090],
an interval covering zero, on the same transcripts where 1440 draws gives
-0.0436. The message is identical in all four cells. Only the number of worlds
it can act on differs.

The registration named this possibility before the run --- *"more draws gives
the convention's reweighting more worlds to act on, which could make the decode
more effective rather than less"* --- and it is what happened.

## The opponent pool, secondary and worth more than most secondaries

| `n_draws` | paired **opponent** NLL |
|---|---|
| 180 | **+0.0435** [+0.0287, +0.0582] |
| 360 | +0.0173 [+0.0083, +0.0262] |
| 720 | +0.0025 [-0.0033, +0.0082] |
| 1440 | **-0.0086** [-0.0135, -0.0037] |

At low precision the decode makes the **opponent-side belief significantly
worse**, and it crosses to significantly better between 720 and 1440. Same
message, same transcripts, opposite sign. Reweighting a small set of worlds by
a fact about a teammate distorts the rest of the joint; with enough worlds it
stops having to.

## A caveat this hands to every convention number in the project

The shipped engine samples at **`n_draws = 480`**. Every belief figure in this
direction --- the depth book, the aimed book, the locating book, all of
`results/convention_posterior.json` and `results/convention_replication.json`
--- was scored at **720**, because that is what `gamma_split.py` fixed and the
convention instrument imported.

Interpolating this grid put the aimed book's -0.0382 at roughly **-0.033** at
the shipped 480.

> **MEASURED 2026-08-31, replacing that interpolation.** A descriptive run on
> the same transcripts with 480 added to the grid gives **-0.0368**
> [-0.0523, -0.0213] --- `results/channel_precision_shipped.json`. That is a
> **4%** difference from the 720 figure, not the 15% a straight line between
> the 360 and 720 cells predicted: the curve flattens well before 720 and the
> interpolation could not see it.
>
> The run is marked non-registered everywhere it can be --- on stdout, in the
> payload's `registered: false`, and in a verdict prefixed DESCRIPTIVE ---
> because a run on a different grid is not this registration's test however
> similar it looks. The four cells it shares with the registered run came back
> **bit-identical** (delta 0.00e+00 on all four), which is what the
> per-decision RNG seeding is for: inserting a cell perturbs no other cell.
>
> So the caveat survives but shrinks. "These numbers are quoted at 1.5x the
> sampler precision the engine uses" is still true and still worth knowing; it
> is worth about 4% on the aimed book, not 15%.

## What this does and does not say about the engine drift

**It does not rehabilitate or refute the drift explanation**, and the
registration said so before the numbers existed: that was a *model* change over
eleven commits, and this sweeps *sampler precision*. The two are different axes
and this run cannot speak to the other one.

What it does is remove the support the claim was resting on. "A message is
worth what the receiver could not already work out" was asserted from two
confounded points; the one controlled test available to it went the other way
on the nearest axis. It also supplies a competing explanation for the drift
that cannot be ruled out from here: eleven commits could have changed how many
*effective* worlds the sampler produces as easily as they changed the belief's
quality, and the old engine is not available to check.

Per this document's own licensing clause, the sentence is weakened wherever it
appears: `RESEARCH_FRONTIER.md`, `prereg/convention_aimed.md` and
`fish4/convention.py`.
