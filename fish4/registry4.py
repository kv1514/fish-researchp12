"""Agent registry spanning v0.3 and v0.4 policies.

Evaluation harnesses cross process boundaries, so agents are addressed by
``(name, kwargs)`` specs rather than by object. Importing this module registers
the v0.4 policies alongside the v0.3 ones; any worker process that imports it
can therefore construct either generation, which is what makes head-to-head
duplicate-deal matches between the two possible at all.
"""

from __future__ import annotations

from fish.agents import AGENT_REGISTRY as _V03

from .agent4 import FishBot4

#: The v0.3 champion, as established by 600-pair duplicate-deal experiments.
V03_CHAMPION = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
#: The v0.3 baseline the champion was measured against.
V03_BASELINE = ("probabilistic", {})

#: The v0.4 champion: every "vs champion" cell in the paper is against this
#: exact spec, so it is a fixed reference and its defaults must not drift.
V04_CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})

#: The champion plus the belief-space lookahead, which a pre-registered run over
#: 6000 duplicate deal-pairs put at +0.104 sets per deal-pair, 95% CI
#: [+0.020, +0.189] (jobs/PREREGISTRATION_lookahead.md, and the settling blocks
#: of the paper's lookahead table). It is the strongest configuration measured.
#:
#: It is a SEPARATE NAME rather than a change to FishBot4's defaults, and that is
#: not timidity. Every duel in results/v04_duels.jsonl labelled "vs champion"
#: names its opponent as fishbot4 with an explicit opponent_gamma and nothing
#: else; moving the defaults would silently redefine what those runs measured,
#: including the ones still in flight. The reference stays put and the stronger
#: policy gets its own name.
#:
#: The gain is not free: Section "Cost" of the paper measures the search at about
#: 6.7 ms per decision, roughly a quarter again on top of a v0.4 turn, so a
#: caller under a latency budget should choose deliberately rather than inherit.
V04_STRONGEST = ("fishbot4", {"opponent_gamma": 0.35, "w_lookahead": 0.25,
                              "lookahead_depth": 3, "lookahead_beam": 4})

#: The champion with a tripled sampling budget. A pre-registered run over 6000
#: duplicate deal-pairs puts it at +0.340 sets per deal-pair, 95% CI
#: [+0.243, +0.436], with all six blocks positive and Cochran's Q at p = 0.71
#: (jobs/PREREGISTRATION_precision.md). That is the largest effect measured in
#: this project, more than three times the lookahead's, and it costs
#: +1.7 ms per decision -- 1.35x, not 3x, because at 160 draws the sampler is
#: only a fifth of a decision (results/precision_cost.json).
V04_PRECISE = ("fishbot4", {"opponent_gamma": 0.35, "n_draws": 480})

#: Both changes at once. This was deliberately NOT defined until the stacking
#: run reported, because each had been measured against the champion ALONE and
#: naming their combination would have asserted an additivity nobody had tested
#: -- the lookahead's whole mechanism is to search a belief the sampler draws,
#: which is exactly the sort of coupling that need not add.
#:
#: The stacking run (jobs/PREREGISTRATION_stack.md, 6000 pairs) has now reported
#: the lookahead ON TOP OF 480 draws at +0.072, 95% CI [-0.010, +0.154]. Chained
#: with the precision run's +0.340 -- disjoint deal seeds, so independent and the
#: errors add in quadrature -- the combination is worth
#:
#:     +0.411 sets per deal-pair, 95% CI [+0.285, +0.538]
#:
#: against the champion (results/combined_estimate.json). That excludes zero
#: comfortably and is the largest effect in this project.
#:
#: It has SINCE been played directly, which is what makes the number usable
#: rather than merely large. A chained estimate inherits both links'
#: assumptions -- in particular that each change's effect does not depend on
#: the deal population the other was measured over -- and that was plausible
#: and unmeasured. jobs/PREREGISTRATION_combined.md fixed the design and all
#: three possible outcomes before any pair; over 2000 fresh pairs the direct
#: estimate is
#:
#:     +0.357 sets per deal-pair, 95% CI [+0.191, +0.524]
#:
#: (results/combined_verdict.json). Direct minus chained is -0.054 +/- 0.107,
#: half a standard error, so the chain holds. The direct interval is WIDER --
#: 2000 pairs against 12000 -- and the pre-registration says so in advance:
#: this run could not make the estimate more precise, only honest.
#:
#: What stays unresolved is whether it beats V04_PRECISE. That IS the stacking
#: run's own estimate, and its interval contains zero at 68% power -- a failure
#: to resolve, not a null. So the honest ordering is
#: V04_COMBINED >= V04_PRECISE > V04_CHAMPION, with the first inequality
#: undemonstrated.
#:
#: This is also what the public table actually plays: api/_engine.py sets
#: WEB_DRAWS = 480 and WEB_SPEC's lookahead. The site was running an
#: unnamed configuration while this module declined to name it.
#: THE ENDGAME ASK CORRECTION, added after the above was written.
#:
#: The exact imperfect-information solver made a claim about this objective
#: that no duel could have: on 51% of unpinned m = 1 positions and 61% at
#: m = 2 the champion's ask is provably beaten by another ask, the better move
#: is an ASK rather than a claim (131/154 and 128/138), and it is RISKIER --
#: p = 0.218 against 0.799 at m = 1, paired t = -18.88, with the champion's ask
#: a CERTAIN hit on 73 of 122 and still wrong.
#:
#: Simply de-weighting the success probability does not fix it: the
#: one-parameter scale family, which spans every positive weight on p, picks
#: k = 1. What helps is the information term, fitted against exact one-ply
#: values on 388 endgame positions and held out by game.
#:
#: Then measured three times rather than once, because an effect measured
#: against a weak base does not transfer by assumption:
#:
#:     vs champion, registered      +0.0835  [+0.0338, +0.1332]   2000 pairs
#:     vs champion, replication     +0.0980  [+0.0480, +0.1480]   2000 pairs
#:     vs champion, pooled          +0.0907  [+0.0555, +0.1260]   4000 pairs
#:     ON TOP OF THIS SPEC          +0.1220  [+0.0711, +0.1729]   2000 pairs
#:     raising m from 2 to 3        +0.3025  [+0.2271, +0.3779]   2000 pairs
#:     raising m from 3 to 4        +0.6995  [+0.6033, +0.7957]   2000 pairs
#:     raising m from 4 to 5        +1.0125  [+0.8961, +1.1289]   2000 pairs
#:
#: The third is what licensed the default moving and is what the site gained;
#: it is slightly LARGER on the stronger base, so the depth-3 lookahead was not
#: already finding these asks.
#:
#: The fourth extends the SAME weight to three live half-suits without
#: refitting it, which takes the correction from 9.7% of decisions to 17.5%.
#: That step is worth two and a half times the one before it, and it was only
#: reachable because a SAMPLED one-ply target stands in for the exact one where
#: exact solving cannot go -- validated first, at a cost of +0.0033 in the exact
#: target's own units, and cross-fitted against the selection bias that
#: maximising a noisy target introduces (49% of the naive figure).
#:
#: FishBot4's own defaults are untouched. The champion is the reference point
#: for every measurement in the paper, and moving it would silently reprice all
#: of them; tests4/test_endgame_weights.py requires whole games to be
#: bit-identical when the knob is off.
V04_COMBINED = ("fishbot4", {"opponent_gamma": 0.35, "n_draws": 480,
                             "w_lookahead": 0.25, "lookahead_depth": 3,
                             "lookahead_beam": 4,
                             "endgame_m": 5, "endgame_d_info": 2.0})

#: NOT DEFINED, and the omission is still the point: at-ask-time depth at
#: gamma = 1.0 is DEMONSTRATED (+0.102 over 6000 pre-registered pairs) and is
#: deliberately not shipped, because jobs/PREREGISTRATION_at_ask.md fixed 0.15
#: in advance as the smallest effect worth adopting and 0.102 is under it. A
#: real effect below a threshold chosen before the data is not a reason to
#: change a default; that is what fixing the threshold in advance was for.
#: depth_mode therefore stays "initial" everywhere.

REGISTRY = dict(_V03)
REGISTRY["fishbot4"] = FishBot4

# Register into the v0.3 registry too, so tools that only know about that one
# keep working. Mutating the dict is deliberate: it avoids forking v0.3 code.
_V03.setdefault("fishbot4", FishBot4)


def make_agent(spec):
    name, kwargs = spec
    return REGISTRY[name](**kwargs)
