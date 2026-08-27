# Pre-registration: the misdeclaration rule becomes the baseline

Written before any game of this program is played, and before the default
flip is committed.

## The correction being made

Since v0.1 the engine's default rule for a claim that is wrong ONLY in its
within-team split (the claiming team holds all six cards but misassigns
them among teammates) has been `wrong_distribution_outcome="null"`: the set
is voided and nobody scores it. In the game as actually played -- and in
Dylan's v0.7 engine, the only foreign engine we test against -- a
misdeclared set is AWARDED TO THE OPPOSING TEAM. A claim naming any card
the opponents actually hold has always awarded them the set under both
settings; the void was confined to the within-team-split case, which is
exactly the case a forced endgame declaration hits most.

The fix: `wrong_distribution_outcome` defaults to `"opponent"` everywhere
(engine dataclass, site, harnesses). `"null"` remains a supported option so
every measurement in the paper's void era stays reproducible, and is
relabelled the variant.

What is already known, from the paper's own rule-robustness table
(`results/` behind Table tab:rules): the headline comparison v0.4 vs v0.3
was measured under "wrong split -> opponents" at 200 pairs and held:
+1.690 [+1.191, +2.189]. So the expectation is continuity, not upheaval.
That expectation is written down here so it cannot be adjusted afterwards.

## Designs (all under the new default, pinned explicitly in each runner)

Every runner passes `wrong_distribution_outcome="opponent"` explicitly so
the results files are self-describing rather than default-dependent. Engine
digest recorded per block. No write-access agents run while any block runs.

### R1 -- the headline, restated under the real rule
Deployed configuration (BASE + endgame_m=2, endgame_d_info=2.0) vs the
v0.3 champion. 500 duplicate deal-pairs, fresh seed block 400000+,
statistic the paired diff of set margins. Outcomes, fixed now:
- CI clear of zero, positive: the headline stands under standard scoring;
  the new estimate REPLACES +1.85 as the paper's headline number, and the
  old number is kept, labelled as the void-variant measurement.
- CI straddles zero or reverses: reported exactly as such, headline
  withdrawn pending diagnosis. (Prior evidence makes this unlikely; that
  is why it must be written down.)

### R2 -- the foreign check, rule-matched
Repeat prereg/foreign_opponent_m2.md (on/off arms, 3x each vs Dylan v0.7,
250 deals x both rotations, paired) under the award rule, fresh seed block
332000+. Now the two engines play the SAME misdeclaration rule, removing
the one scoring-rule caveat the first run carried. Outcomes as in the
original prereg (reversal / straddle / transfer), plus the context margin
and decided-set share become the site-facing numbers.

### R3 -- the claim threshold, sanity under the new penalty
0.97 (shipped) vs 0.999 and vs 0.90, 200 pairs each. The mechanism
argument (waiting is nearly free while the team holds the set; an opponent
claim of a set we fully hold awards it to US under both rules) is
rule-independent, so the registered expectation is "no detectable
difference 0.90..0.999". A detectable difference means the mechanism
argument was void-conditioned and the claiming section of the paper gets
rewritten, not footnoted.

### R4 -- the endgame correction under the new rule
The m<=2 ask-correction stack (correction on vs off within the deployed
config), 500 pairs. Registered expectation: the sign holds; the size is
allowed to move (the correction's decisions live exactly where forced
declarations happen, which is where the rule bites).

## What is NOT re-run, and why that is honest

Settled 6000-pair instrument studies (lookahead, precision, at-ask-time
depth, learned weights) measured design choices whose comparisons were
internal to the void rule era; the paper will label their rule explicitly
rather than silently implying the new baseline. Posterior-quality tables
(NLL/Brier vs ground truth) do not score claims at all and are
rule-invariant. Re-running everything at full n is months of compute; the
pre-registered claim is that R1-R4 are sufficient to restate every number
the abstract, strategy section, and site actually assert.

## Void-frequency accounting

Each R1/R2 block also records how many sets per game the flip actually
touches: the count of within-team-split misdeclarations (previously
voided, now awarded). This is the effect-size denominator for the whole
correction and goes in the paper beside the rule change.
