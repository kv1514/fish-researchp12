"""Does every number the paper quotes still match the results file it came from?

Several already did not. The divergence model's cell count was written as 28,
then 31, then 34, while runs kept landing and appending to
``results/v04_duels.jsonl``; the paper said $3.88$ where the file said $3.911$;
and a standard-error correction moved a per-pair sd that four documents quote.
None of those were caught by reading, because a stale number reads exactly like
a fresh one.

This is a manifest of the figures most exposed to that -- the ones derived from
a results file that keeps growing -- with the value the file holds now and the
string the paper must contain. It does not try to parse the paper's claims. It
formats the current value the way the paper formats it and checks that string is
present, which is crude, catches drift, and cannot silently pass.

A miss is not automatically an error: a paper legitimately quotes a snapshot.
What it must not do is quote a snapshot while implying it is current, so a miss
is a prompt to either refresh the figure or say when it was taken.

Usage: python scripts4/check_paper_numbers.py
Exit status is 1 if any watched figure no longer appears in the paper.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "kraken.tex"


def _get(d, path):
    for k in path.split("."):
        if isinstance(d, list):
            k = int(k)
        d = d[k]
    return d


def _load(fname: str):
    """Load a results source. ``duel:<label>`` addresses one cell of the pool.

    The pool is JSONL, so until this existed the manifest could not watch
    anything in it -- and the single most-quoted figure in the paper, the
    abstract's headline margin over the previous champion, lives there. That is
    the same shape as the settle_verdict.py failure this module was extended
    for: the most load-bearing number was the one number no drift check could
    see, and for a reason as dull as a file format.
    """
    if fname.startswith("duel:"):
        label = fname[len("duel:"):]
        hits = [json.loads(l) for l in
                (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines()
                if l.strip()]
        hits = [r for r in hits if (r.get("label") or "") == label]
        if not hits:
            raise FileNotFoundError(f"no duel cell labelled {label!r}")
        if len(hits) > 1:
            # Same rule as pool_cells.cells: silently preferring one is how a
            # figure comes to be checked against a run nobody meant.
            raise ValueError(f"{len(hits)} cells share the label {label!r}")
        return hits[0]
    return json.loads((ROOT / "results" / fname).read_text())


#: (results file, key path, format spec, short name, anchor).
#:
#: The anchor is the point. Checking only that a formatted number appears
#: SOMEWHERE in a 3700-line paper is close to useless: "0.340" occurs for
#: unrelated reasons, so a stale figure passes because a different figure
#: happens to share its digits. Each row therefore names a phrase that must
#: appear within WINDOW characters of the number, which ties the check to the
#: sentence that makes the claim.
WINDOW = 700

WATCH = [
    ("pair_sd_model.json", "n_cells", "{:d}", "divergence-model cell count",
     "cells of this study that store"),
    ("pair_sd_model.json", "cond_sd_mean", "{:.2f}", "conditional sd",
     "it moves little in absolute terms"),
    ("pair_sd_model.json", "corr_share_sd", "{:+.3f}", "corr(share, sd)",
     "The correlation between $s$ and the raw standard deviation"),
    # The out-of-sample test of the drift correction. Its whole force is that
    # the two errors point opposite ways, so both have to stay true.
    ("pair_sd_model.json", "low_share_check.flat_rel_err", "{:+.1%}",
     "flat model error at low share", "mean relative error"),
    ("pair_sd_model.json", "low_share_check.drift_rel_err", "{:+.1%}",
     "drift-corrected error at low share", "mean relative error"),
    ("pair_sd_model.json", "cond_drift.intercept", "{:.2f}",
     "drift fit intercept", "it drifts\nwith share"),
    ("pair_sd_model.json", "cond_drift.slope", "{:.2f}", "drift fit slope",
     "it drifts\nwith share"),
    # The position-statistics table, quoted in the abstract and the intro. Every
    # row of it disagreed with the file it summarises, including the maximum
    # that the complexity argument was stated as a bound on.
    ("infer_position_stats.json", "free_cards.n", "{:d}",
     "positions in the corpus", "decision points of the stored corpus"),
    ("infer_position_stats.json", "free_cards.mean", "{:.1f}",
     "mean free cards", "free cards $|F|$"),
    ("infer_position_stats.json", "mask_groups.mean", "{:.1f}",
     "mean distinct candidate sets",
     "\\textbf{distinct candidate sets}"),
    ("infer_position_stats.json", "mask_groups.max", "{:d}",
     "max distinct candidate sets",
     "$G$ is small: at most"),
    ("infer_position_stats.json", "active_ors.mean", "{:.1f}",
     "mean active OR-constraints", "active OR-constraints"),
    ("infer_position_stats.json", "or_size.mean", "{:.2f}",
     "mean cards per OR-constraint", "cards per OR-constraint"),
    # The tablebase cross-check. It was quoted as "131 further positions at
    # 4,205x"; the file holds one corpus of 300 and no ratio near 4,205.
    ("exact2_cross_check.json", "cross_check_m1.n_positions", "{:d}",
     "tablebase cross-check corpus", "one cross-check rather than two"),
    ("exact2_cross_check.json", "cross_check_m1.v1_cpu_seconds", "{:,.0f}",
     "old solver CPU seconds", "CPU-seconds against"),
    # Proposition 1's empirical shadow. It was quoted as "53,273 of 53,273"
    # with no file behind it; these come from instrumenting the real search.
    ("greedy_shadow.json", "uncoupled.nodes", "{:,d}", "multi-branch nodes",
     "Instrumenting the\nsearch itself over"),
    ("greedy_shadow.json", "coupled.non_greedy", "{:d}",
     "coupled departures", "the coupled arm departs from the"),
    ("greedy_shadow.json", "uncoupled.non_greedy", "{:d}",
     "uncoupled departures", "the uncoupled arm\ndeparts at"),
    # Precision rung 2 and the log-linearity contrast. Rung 2 alone is not
    # demonstrated and the CONTRAST is, so the two must never drift apart --
    # quoting one without the other inverts what the run showed.
    ("precision2_verdict.json", "pooled.fe", "{:.3f}", "precision rung 2",
     "$480 \\to 1440$ draws, 6000 pairs"),
    ("precision2_verdict.json", "log_linearity.delta", "{:+.3f}",
     "log-linearity contrast",
     "the difference between the rungs"),
    ("precision2_verdict.json", "log_linearity.se", "{:.3f}",
     "contrast standard error",
     "the difference between the rungs"),
    ("precision2_verdict.json", "min_interesting", "{:.3f}",
     "minimum interesting effect", "fixed before any pair was played"),
    # The half-suit value model's calibration. The paper called it "reliable
    # across every decile" while half its deciles miss at 95%; the mean bias is
    # small only because the errors cancel, so both have to be quoted together.
    ("hsvalue_fit.json", "results.model.mean_bias", "{:+.3f}",
     "hsvalue mean calibration bias", "mean calibration\nbias of"),
    ("hsvalue_fit.json", "results.model.log_loss", "{:.3f}",
     "hsvalue held-out log-loss",
     "half-suit value model is good --- held-out log-loss"),
    ("precision_verdict.json", "pooled.fe", "{:.3f}", "precision pooled",
     "Six blocks of $1000$ duplicate deal-pairs"),
    ("at_ask_verdict.json", "pooled.fe", "{:.4f}", "at-ask pooled",
     "sized against a minimum interesting effect"),
    ("continuation_compare.json", "v04.slope", "{:.3f}", "v04 slope",
     "position-centred\nrollout value rises by"),
    ("continuation_compare.json", "public.slope", "{:.3f}", "public slope",
     "Running the public-information heuristic on"),
    ("continuation_compare.json", "paired.delta", "{:.3f}", "paired difference",
     "That paired contrast is"),
    ("continuation_compare.json", "paired.median_per_position", "{:.3f}",
     "median per-position difference", "The robust summaries agree"),
    ("continuation_compare.json", "paired.unweighted_mean", "{:.3f}",
     "unweighted per-position mean", "Averaging the\nper-position slope"),
    ("precision_cost.json", "fixed_ms", "{:.2f}", "fixed cost per decision",
     "Measured on $90$\npositions, a decision costs"),
    ("precision_cost.json", "marginal_us_per_draw", "{:.2f}", "cost per draw",
     "Measured on $90$\npositions, a decision costs"),
    # The residuals. The paper quoted a tolerance the fit does not achieve and
    # nothing stored could contradict it, because the residuals were printed
    # and never saved.
    ("precision_cost.json", "max_abs_residual_ms", "{:.2f}",
     "worst residual of the cost fit", "a fit whose residuals reach"),
    ("decision_cost_profile.json", "fixed_ms", "{:.2f}",
     "sampler-alone fixed cost", "per draw --- about"),
    # The ESS figures. The paper quoted a p90 of the champion arm as if it were
    # the mean of a model-disabled arm that was never run, and gave two
    # different efficiencies 400 lines apart. All four are now watched.
    ("ess_probe.json", "0.mean_ess", "{:.1f}", "champion mean ESS",
     "160 draws are worth"),
    ("ess_probe.json", "0.efficiency", "{:.0%}", "champion ESS efficiency",
     "160 draws are worth"),
    ("ess_probe.json", "0.p90_ess", "{:.1f}", "champion ESS p90",
     "a median of $87.0$ and a p90 of"),
    ("ess_probe.json", "0.exact_decisions", "{:d}", "exact-DP decisions",
     "The exact DP is almost never"),
    ("mde_recheck.json", "verdicts_changed_project_bar", "{:d}",
     "cells whose verdict changes", "Under the definition the rest of the paper"),
    ("continuation_length.json", "public.mean", "{:.0f}", "heuristic plies",
     "the\nheuristic needs"),
    ("continuation_length.json", "v04.mean", "{:.0f}", "engine plies",
     "the\nheuristic needs"),
    # Quoted in the playing-advice section, where a stale number would be
    # advice to a human rather than a figure in a table.
    ("duel_depth_base_rate.json", "max_recoverable", "{:.3f}",
     "most the retake gate can recover",
     "The situation is not rare"),
    # The collinearity diagnostic. Its whole force is that the VIF is large
    # enough to void the coefficient beside it; a stale VIF would leave the
    # paper voiding a fit on a number the file no longer holds.
    ("target_feature_fit.json", "p_success_vif", "{:.1f}",
     "P(success) variance inflation", "variance inflation\nfactor of"),
    ("target_feature_fit.json", "multivariate.p_success.coef", "{:+.3f}",
     "P(success) multivariate coefficient", "turns \\emph{negative}, at"),
    ("target_feature_fit.json", "p_success_abscorr.deplete", "{:.3f}",
     #: NOT the bare phrase "correlates with". That is common enough English
     #: that a later section using it made both of these ambiguous, which the
     #: guard caught as "(anchor x2)" before the value could be checked
     #: against the wrong sentence.
     "corr with deplete", "\\texttt{deplete} at"),
    ("target_feature_fit.json", "p_success_abscorr.certain", "{:.3f}",
     "corr with certain", "\\texttt{certain} at"),
    ("target_feature_fit.json", "within_r2", "{:.1%}", "within R^2 of the fit",
     "The whole eleven-term fit explains"),
    # `turn` is the control on the collinearity story: the paragraph's point is
    # that this term is NOT entangled and still disagrees with play, so all
    # three of its figures have to stay true or the paragraph inverts.
    ("target_feature_fit.json", "multivariate.turn.vif", "{:.1f}", "turn VIF",
     "variance inflation factor is"),
    ("target_feature_fit.json", "multivariate.turn.coef", "{:+.3f}",
     "turn coefficient", "It comes back at"),
    ("target_feature_fit.json", "positions_with_variation.turn", "{:d}",
     "positions where turn varies", "it varies between\ncandidate asks at"),
    ("target_feature_fit.json", "n_positions_kept", "{:d}",
     "positions in the within fit", "it varies between\ncandidate asks at"),
    # The decomposition. Its force is that the two terms ADD to the combined
    # contrast, so all three have to stay in step or the identity stops being
    # one.
    ("continuation_compare.json", "public_seeded.slope", "{:.3f}",
     "public arm with the log seeded", "with the public log seeded. It scores"),
    ("continuation_compare.json", "decomposition.policy_only.delta", "{:.3f}",
     "policy alone", "policy alone"),
    ("continuation_compare.json", "decomposition.log_only.delta", "{:.3f}",
     "the log alone", "the log alone"),
    ("stall_asymmetry.json", "arms.v04.acts", "{:,d}",
     "engine-continuation decisions counted", "the rule fired \\emph{zero}"),
    ("stall_asymmetry.json", "prefix_bite.mean", "{:.1f}",
     "actions the seeded prefix eats", "the seeded prefix eats a mean"),
    # The sixth cell of the adaptive family, quoted in two places: the results
    # table and the playing advice. A stale figure here is advice to a human.
    ("retake_verdict.json", "pooled.fe", "{:.3f}", "gated retake, pooled",
     "The gated penalty\nscores"),
    ("retake_verdict.json", "contrast_vs_ungated.delta", "{:.3f}",
     "gated vs ungated", "Against the ungated"),
    ("retake_verdict.json", "n_pairs", "{:d}", "pairs in the retake run",
     "It has now been run at"),
    # The stacking run. Its whole point is that an interval containing zero is
    # NOT a null here, so the estimate and the power it was sized against have
    # to travel together or the paragraph inverts.
    ("stack_verdict.json", "pooled.fe", "{:.3f}", "lookahead on top of 480",
     "lookahead on top of $480$ draws"),
    ("stack_verdict.json", "n_pairs", "{:d}", "pairs in the stacking run",
     "At $6000$ pairs this run has"),
    ("stack_verdict.json", "power_vs_alternative", "{:.0%}",
     "power against the stated alternative", "power against the"),
    # The HEADLINE. settle_verdict.py printed this and stored nothing for its
    # whole life, so the single most load-bearing number in the paper was the
    # one figure this manifest could not watch. It is quoted in five places.
    ("settle_verdict.json", "pooled.fe", "{:.3f}", "lookahead, pre-registered",
     "four rounds and $6000$ pre-registered pairs"),
    ("settle_verdict.json", "secondary.pooled.fe", "{:.3f}",
     "lookahead, unselected pool", "secondary --- all ten unselected cells"),
    ("settle_verdict.json", "n_pairs", "{:d}", "pairs in the settling run",
     "four rounds and $6000$ pre-registered pairs"),
    # The programme total. It was quoted as 15,600 in the abstract and again in
    # the results, and matched nothing: not the table (9,700), not the record
    # with the stacking run added (15,700). Nobody could recompute it, so it
    # drifted unchallenged. It is now computed from the duel record.
    ("settle_verdict.json", "programme_pairs", "{:,d}",
     "the lookahead programme's cost", "deal-pairs across four rounds"),
    ("settle_verdict.json", "programme_rounds.settling", "{:d}",
     "pairs in the settling round", "6000 in the pre-registered settling"),
    # The basis comparison. Its point is that the winner's margin CONTAINS
    # ZERO, so the estimate and its standard error have to travel together --
    # quoting the gain alone would invert the paragraph into the conclusion it
    # was written to retract.
    ("basis_search.json", "full_cv_r2", "{:.4f}", "full basis CV R^2",
     "full, eleven terms and"),
    ("basis_search.json", "best_cv_r2", "{:.4f}", "best basis CV R^2",
     "selected \\emph{within} each fold"),
    ("basis_search.json", "gain_over_full", "{:+.4f}", "gain over the full basis",
     "beats the basis in use by"),
    ("basis_search.json", "gain_se", "{:.4f}", "standard error of that gain",
     "beats the basis in use by"),
    # The chained combined estimate. It is the paper's largest number and it is
    # INDIRECT, so the estimate, its error and the pair count all have to stay
    # in step with the two runs behind it.
    ("combined_estimate.json", "chained.est", "{:.3f}", "combined vs champion",
     "chained: search $+$ $480$ draws"),
    ("combined_estimate.json", "chained.se", "{:.3f}",
     "error on the combined estimate", "chained: search $+$ $480$ draws"),
    ("combined_estimate.json", "chained.lo", "{:+.3f}", "combined interval, low",
     "larger than either change alone"),
    ("combined_estimate.json", "chained.hi", "{:+.3f}", "combined interval, high",
     "larger than either change alone"),
    ("at_ask_verdict.json", "pooled.fe", "{:.3f}", "at-ask, not shipped",
     "At-ask-time\ndepth at"),
    # The split-calibration table. Its whole point is the gap between the
    # stated probability and the realised accuracy, so the decision count and
    # the population size both have to stay true or the table stops being one.
    ("stuck_claim_value.json", "n_decisions", "{:d}", "split decisions scored",
     "decisions on"),
    ("stuck_claim_value.json", "n_half_suits", "{:d}", "distinct half-suits",
     "decisions on"),
    ("stuck_claim_value.json", "calibration_under_half", "{:.1%}",
     "accuracy below 0.5", "$[0.000, 0.500)$"),
    ("stuck_claim_value.json", "value.half_suits_within_one_team_per_game",
     "{:.2f}", "half-suits within one team per game",
     "per game out of nine"),
    # The deadlock quartet, and the reason this manifest exists at all. All
    # four figures were quoted in three places across every draft and matched
    # NO results file: perpetual_study.py tracked which TEAMS were stuck and
    # recorded nothing per half-suit, so no check could have caught them and
    # none did. One of them was then consumed downstream as a decision bar in
    # scripts4/stuck_claim_value.py. Re-measured, the ratio is four times what
    # was claimed and the share of nulls is 73% against a quoted 27%.
    ("perpetual_study_void.json", "normal.half_suits", "{:d}",
     "half-suits measured", "Over the $1800$ half-suits of"),
    ("perpetual_study_void.json", "normal.stuck_half_suits", "{:d}",
     "half-suits that get stuck", "Over the $1800$ half-suits of"),
    ("perpetual_study_void.json", "normal.share_of_half_suits_stuck", "{:.1%}",
     "share of half-suits stuck", "Over the $1800$ half-suits of"),
    ("perpetual_study_void.json", "normal.misdeclare_rate_when_stuck", "{:.1%}",
     "null rate when stuck", "and they are nulled"),
    ("perpetual_study_void.json", "normal.misdeclare_rate_when_not_stuck", "{:.2%}",
     "null rate when not stuck", "half-suits that never get stuck"),
    ("perpetual_study_void.json", "normal.misdeclare_rate_ratio", "{:.0f}",
     "ratio between the two", "half-suits that never get stuck"),
    ("perpetual_study_void.json", "normal.stuck_share_of_all_misdeclares", "{:.0%}",
     "stuck share of all nulls", "so they account for"),
    # The signalling contrast is the one place this rate is quoted as a
    # BEFORE and an AFTER, so the two have to move together or the 20%
    # reduction stops being one.
    #
    # The file is now ``perpetual_study_void.json`` and the keys say
    # "misdeclare" rather than "null": the study was pinned to the void rule
    # and counted NULL_TEAM outcomes, which read zero under the opponent-award
    # baseline. It counts the EVENT now -- a team held all six and named the
    # wrong split -- which means the same thing under both rules. The fresh
    # void run reproduces the archived file on every field, so these figures
    # are unchanged; only their label is.
    # v1.1, section sec:v11. Every one of these was bolded in the paper with
    # nothing behind it -- caught by unwatched_claims, not by a reader. The
    # deal-clustered declaration figures now live in results/cluster_audit.json
    # (scripts4/cluster_audit.py persists them) and the ceiling interaction in
    # results/declaration_timing.json (scripts4/derive_ceiling_interaction.py),
    # rather than being computed in the prose.
    ("cluster_audit.json",
     "declare_regret.best_claim_minus_best_ask_when_asked.mean", "{:.4f}",
     "best claim minus best ask, deal-clustered", "best claim minus best ask"),
    ("cluster_audit.json",
     "declare_regret.best_claim_minus_best_ask_when_asked.half_width_by_deal",
     "{:.4f}", "its deal-clustered half-width", "best claim minus best ask"),
    ("cluster_audit.json",
     "declare_regret.best_claim_minus_best_ask_when_asked.n_positions",
     "{:d}", "positions where it asked", "beat the best ask in"),
    ("cluster_audit.json",
     "declare_regret.best_claim_minus_best_ask_when_asked."
     "positions_where_claim_beat_ask", "{:d}",
     "positions where the best claim beat the best ask",
     "beat the best ask in"),
    ("declaration_timing.json", "derived.interaction", "{:.2f}",
     "the ceiling interaction, T - (D+K)", "together are worth"),
    ("declaration_timing.json", "derived.interaction_share_of_T", "{:.0%}",
     "the interaction as a share of the teammate ceiling",
     "of the\nteammate ceiling is in neither channel alone"),
    ("perpetual_study_void.json", "normal.misdeclares_per_game", "{:.3f}",
     "nulls per game", "cuts nulls from"),
    ("perpetual_study_void.json", "signalling.misdeclares_per_game", "{:.3f}",
     "nulls per game, signalling on", "cuts nulls from"),
    # The same three rows under the baseline rule. #50 item (3) asked whether
    # the award flip re-prices this table; measured on the same 200 seeds it
    # does not move at all, so these must equal their void twins above. If
    # they ever diverge, one of the two runs has gone stale.
    ("perpetual_study_award.json", "normal.misdeclares_per_game", "{:.3f}",
     "misdeclarations per game, award rule", "cuts nulls from"),
    ("perpetual_study_award.json", "signalling.misdeclares_per_game", "{:.3f}",
     "misdeclarations per game, award rule, signalling on", "cuts nulls from"),
    ("perpetual_study_award.json", "normal.misdeclare_rate_when_stuck", "{:.1%}",
     "misdeclaration rate when stuck, award rule", "and they are nulled"),
    # The claim-threshold confirmation. Its point is that the SCREEN and the
    # confirmatory run disagree, so both have to be quoted and both have to
    # stay true -- writing one without the other is how the screen got counted
    # among the designed cells in the first place.
    ("claim_threshold_verdict.json", "estimate", "{:.3f}",
     "claim threshold, confirmatory", "two new blocks, 2000 pairs"),
    ("claim_threshold_verdict.json", "n_pairs", "{:d}",
     "pairs in the claim run", "two new blocks, 2000 pairs"),
    ("claim_threshold_verdict.json", "screen.decay", "{:.3f}",
     "decay from screen to confirmation", "the decay of"),
    ("claim_threshold_verdict.json", "screen.decay_se", "{:.3f}",
     "error on that decay", "the decay of"),
    # The realised sizing. The paragraph's whole claim is that the design
    # missed its own power target, so the planned and realised MDEs have to
    # travel together or it reads as a design that met it.
    ("claim_threshold_verdict.json", "realised_sd", "{:.3f}",
     "claim run realised sd", "realised\nstandard deviation is"),
    ("claim_threshold_verdict.json", "mde_80", "{:.3f}",
     "claim run realised MDE", "so the realised MDE is"),
    # The out-of-sample test of the drift correction, at a share a ninth of
    # anything it was fitted on. Both errors have to stay quoted: the force of
    # the paragraph is the RATIO between them.
    ("claim_threshold_verdict.json", "divergence.share", "{:.1%}",
     "claim run divergence share", "the measured share\nis"),
    ("claim_threshold_verdict.json", "divergence.conditional_sd", "{:.2f}",
     "claim run conditional sd", "conditional standard deviation is"),
    ("claim_threshold_verdict.json", "divergence.model_cond_sd_now", "{:.3f}",
     "flat conditional term", "The flat conditional term of"),
    ("claim_threshold_verdict.json", "divergence.drift_pred_cond_sd", "{:.3f}",
     "drift-corrected prediction", "$2.53 + 1.66\\,s$ predicts"),
    ("claim_threshold_verdict.json", "divergence.flat_rel_err", "{:.0%}",
     "flat model error out of sample", "The flat conditional term of"),
    ("claim_threshold_verdict.json", "divergence.drift_rel_err", "{:.0%}",
     "drift model error out of sample", "an overstatement of"),
    # The split-calibration table itself. It was printed and never stored, so
    # nothing could check it -- and two of its rows silently changed counts
    # when a null rate measured in a DIFFERENT script moved the bin edges.
    # Every cell is watched now, and the bins no longer depend on that bar.
    ("stuck_claim_value.json", "calibration.0.n", "{:d}",
     "calibration row 1, n", "posterior says & decisions"),
    ("stuck_claim_value.json", "calibration.1.n", "{:d}",
     "calibration row 2, n", "posterior says & decisions"),
    ("stuck_claim_value.json", "calibration.2.n", "{:d}",
     "calibration row 3, n", "posterior says & decisions"),
    ("stuck_claim_value.json", "calibration.3.n", "{:d}",
     "calibration row 4, n", "posterior says & decisions"),
    ("stuck_claim_value.json", "calibration.4.n", "{:d}",
     "calibration row 5, n", "posterior says & decisions"),
    ("stuck_claim_value.json", "calibration.2.accuracy", "{:.1%}",
     "calibration row 3, accuracy", "posterior says & decisions"),
    # The bar is 1 - the stuck null rate, quoted in the paper as a percentage
    # and consumed here as a threshold. It is the figure that was carried for
    # drafts as 82.5% off a null rate that no file held.
    ("stuck_claim_value.json", "bar", "{:.1%}",
     "declare-beats-wait bar", "beat waiting wherever the MAP is right"),
    ("stuck_claim_value.json", "null_rate", "{:.1%}",
     "null rate the bar comes from", "accepting the measured"),
    # The seventh cell of the adaptive family, and the first in the TRADING
    # direction. Quoted in the advice section and in the results table, so a
    # stale figure here is advice to a human.
    ("retake_bonus_verdict.json", "estimate", "{:.3f}",
     "rewarding the re-take", "(\\path{jobs/PREREGISTRATION_retake_bonus.md}), and it returns"),
    ("retake_bonus_verdict.json", "n_pairs", "{:d}",
     "pairs in the bonus run", "It has now been, at"),
    ("retake_bonus_verdict.json", "contrast_vs_gated_penalty.delta", "{:.3f}",
     "bonus against gated penalty", "the gated penalty's $-0.004$ the difference is"),
    ("retake_bonus_verdict.json", "contrast_vs_gated_penalty.se", "{:.3f}",
     "error on that difference", "the gated penalty's $-0.004$ the difference is"),
    # The claim screen's correctness claim, which was a comment until it was
    # measured. Its safety is a MARGIN, not an agreement, so the largest true
    # joint and the largest gap both have to stay quoted or the paragraph
    # reads as "the shortcut is exact".
    ("claim_screen_check.json", "n_screened", "{:d}",
     "half-suits screened out", "Over $11687$ screened half-suits"),
    ("claim_screen_check.json", "n_claimable_but_screened", "{:d}",
     "claimable half-suits discarded", "the number that turn out to be"),
    ("claim_screen_check.json", "largest_true_joint_among_screened", "{:.3f}",
     "largest true joint among screened", "the largest true joint among them is"),
    ("claim_screen_check.json", "gap_max", "{:+.3f}",
     "largest product-joint gap when screened", "the gap reaches"),
    # The product-vs-joint gap and what it decided. Both halves are needed:
    # the gap alone reads as a large correction, the decision counts alone
    # read as a correction not worth making.
    ("claim_joint_gap.json", "gap.n_queries", "{:d}",
     "half-suit queries compared", "half-suit queries in"),
    ("claim_joint_gap.json", "gap.n_differ", "{:d}",
     "queries where they disagree", "the two\ndisagree on"),
    ("claim_joint_gap.json", "gap.share_overstates_where_they_differ", "{:.0%}",
     "share where the product overstates", "the two\ndisagree on"),
    ("claim_joint_gap.json", "gap.median_abs_where_differ", "{:.3f}",
     "median gap where they differ", "by a median of"),
    ("claim_joint_gap.json", "gap.max_abs", "{:.3f}",
     "largest gap", "and by as much as"),
    ("claim_joint_gap.json", "decision.n_positions", "{:d}",
     "forced-claim positions", "positions in the same games where a forced"),
    ("claim_joint_gap.json", "decision.n_negative_wrongly_split", "{:d}",
     "negative wrongly-split cases", "produced a negative"),
    ("claim_joint_gap.json", "decision.n_declaration_changed", "{:d}",
     "declarations changed", "which half-suit is declared at"),
    # The shipped configuration, measured directly at last. The chained and
    # direct estimates must BOTH stay quoted: the paragraph's whole claim is
    # that they agree, and either one alone reads as the headline.
    ("combined_verdict.json", "estimate", "{:.3f}",
     "shipped config, direct", "\\textbf{direct}, 2000 pairs"),
    ("combined_verdict.json", "ci.0", "{:+.3f}",
     "direct interval, low", "\\textbf{direct}, 2000 pairs"),
    ("combined_verdict.json", "ci.1", "{:+.3f}",
     "direct interval, high", "\\textbf{direct}, 2000 pairs"),
    ("combined_verdict.json", "contrast_vs_chain.delta", "{:.3f}",
     "direct minus chained", "difference & $-0.054"),
    ("combined_verdict.json", "contrast_vs_chain.se", "{:.3f}",
     "error on that difference", "difference & $-0.054"),
    ("combined_verdict.json", "realised_sd", "{:.3f}",
     "combined run realised sd", "against a realised"),
    # THE HEADLINE. The margin over the previous champion is quoted in the
    # abstract, the introduction and the conclusions, and until the loader
    # learned to read the duel pool it was unwatchable -- the most-quoted
    # figure in the paper, outside every drift check, because it lives in a
    # JSONL and everything else lives in JSON.
    ("duel:FINAL: v04 champion vs v03 champion", "diff_mean", "{:.3f}",
     "margin over the v0.3 champion",
     "champion (\\texttt{tuned})"),
    ("duel:FINAL: v04 champion vs v03 champion", "n_pairs", "{:d}",
     "pairs behind the headline", "champion (\\texttt{tuned})"),
    ("duel:FINAL: v04 champion vs v03 champion", "diff_ci.0", "{:.3f}",
     "headline interval, low",
     "champion (\\texttt{tuned})"),
    ("duel:FINAL: v04 champion vs v03 champion", "diff_ci.1", "{:.3f}",
     "headline interval, high",
     "champion (\\texttt{tuned})"),
    # The absolute-strength table. Its rates were computed in the LaTeX and
    # stored nowhere, so the table carrying this paper's independent
    # confirmation of the opponent model -- including the contrast the
    # abstract quotes -- could not be checked against anything.
    ("exact_agreement_rates.json", "agents.v04_champion.rates.uncertain",
     "{:.1%}", "champion under uncertainty", "\\textbf{72.5%}"),
    ("exact_agreement_rates.json", "agents.v04_champion.rates.m2",
     "{:.1%}", "champion at m=2", "agrees with optimal play"),
    ("exact_agreement_rates.json", "agents.v03_champion.rates.uncertain",
     "{:.1%}", "v0.3 champion under uncertainty", "the v0.3 champion's"),
    ("exact_agreement_rates.json", "no_opponent_model_uncertain", "{:.1%}",
     "no opponent model, uncertain", "scores $67.5%$ under uncertainty"),
    ("exact_agreement_rates.json", "n_positions", "{:d}",
     "positions in the agreement corpus", "988 exactly solved positions"),
    # The stalling fraction. It motivates the progress-optimal criterion that
    # the entire absolute-strength table is scored against, so if it is wrong
    # the table is measuring the wrong thing. Both rows: the m=1 zero is what
    # explains why v0.3 never noticed.
    ("exact2_study.json", "stalling.m=2.fraction", "{:.1%}",
     "value-preserving non-progress at m=2", "of\ndecided two-half-suit states"),
    ("exact2_study.json", "stalling.m=1.fraction", "{:.0%}",
     "value-preserving non-progress at m=1", "At\none half-suit the figure is"),
    # The posterior-accuracy contrast the caption is built on: the EXACTLY
    # CORRECT uniform posterior scoring worse than v0.3's biased sampler at the
    # same budget. Quoting one without the other loses the whole point.
    ("posterior_accuracy.json", "rows.3.nll", "{:.4f}",
     "v0.3 sampler at 512 draws", "the same budget"),
    ("posterior_accuracy.json", "rows.9.nll", "{:.4f}",
     "exact uniform posterior at 512", "the same budget"),
    # The headline duel's pair score, quoted beside its set differential.
    ("duel:FINAL: v04 champion vs v03 champion", "pair_score", "{:.3f}",
     "headline pair score", "\\textbf{v0.3 champion (\\texttt{tuned})}"),
    # Quantiles of the candidate-set count, which bound the exact DP's state
    # space; the mean and max were watched and the middle of the distribution
    # was not.
    ("infer_position_stats.json", "mask_groups.median", "{:d}",
     "median distinct candidate sets", "\\textbf{distinct candidate sets}"),
    ("infer_position_stats.json", "mask_groups.p90", "{:d}",
     "p90 distinct candidate sets", "\\textbf{distinct candidate sets}"),
    ("perpetual_study_void.json", "normal.games", "{:d}",
     "games in the perpetual study", "games in which a position repeated"),
    # The A/A per-pair standard deviation. Every MDE and every power statement
    # in this paper divides by it, so it is the most reused number in the
    # document after the headline -- and it was not watched.
    ("v04_eval_calibration.json", "sd_per_pair", "{:.3f}",
     "A/A per-pair standard deviation", "of the set differential between two"),
    # The champion posterior configuration's own scores, bolded as the best
    # row of Table~\ref{tab:posterior}.
    ("posterior_accuracy.json", "rows.1.nll", "{:.4f}",
     "champion posterior NLL", "512, $\\gamma{=}0.45$} & \\textbf{1.3251}"),
    ("posterior_accuracy.json", "rows.1.brier", "{:.4f}",
     "champion posterior Brier", "512, $\\gamma{=}0.45$} & \\textbf{1.3251}"),
    # The learned-weights validation. The estimate and its interval must travel
    # together with the homogeneity and the realised sd, because the paragraph
    # argues the run resolved what it was built to resolve -- quoting the
    # estimate alone would leave that unsupported.
    ("learned_weights_verdict.json", "estimate", "{:.3f}",
     "learned weights vs champion", "\\textbf{this run}, 2000 pairs"),
    ("learned_weights_verdict.json", "ci.0", "{:.3f}",
     "learned weights interval, low", "\\textbf{this run}, 2000 pairs"),
    ("learned_weights_verdict.json", "ci.1", "{:.3f}",
     "learned weights interval, high", "\\textbf{this run}, 2000 pairs"),
    ("learned_weights_verdict.json", "realised_sd", "{:.3f}",
     "learned weights realised sd", "realised per-pair\nstandard deviation of"),
    ("learned_weights_verdict.json", "divergence_share", "{:.1%}",
     "learned weights divergence", "the arms\ndiverge on"),
    ("learned_weights_verdict.json", "v04_attempt.est", "{:.3f}",
     "v0.4's own attempt", "120 pairs \\emph{(different design)}"),
    # The prefix robustness check the amendment committed to.
    ("fit_prefix_check_v2.json", "largest_move.delta", "{:+.3f}",
     "largest weight move, 743 vs 1023", "a largest single move of"),
    ("fit_prefix_check_v2.json", "l1_movement", "{:.3f}",
     "total L1 movement", "total $L_1$ movement of"),
    ("fit_prefix_check_v2.json", "blocks_full", "{:d}",
     "positions in the fit", "resolving it to the full"),
    # The exact imperfect-information endgame. The control is watched first
    # and deliberately: it is the number that licenses every other figure in
    # that section, and a solver whose control quietly drifted from 344 while
    # the paper still said 344 is exactly the failure this manifest exists for.
    ("ii_endgame.json", "pinned_ok", "{:d}",
     "exact-II control, pinned positions matching the closed form",
     "Over $200$ games it does"),
    ("ii_endgame.json", "n_solved", "{:d}",
     "exact-II hidden positions solved", "genuinely hidden positions solved"),
    ("ii_endgame.json", "mean_gain", "{:+.4f}",
     "exact-II gain from deviating",
     "genuinely hidden positions solved exactly"),
    # The control on the BELIEF rather than the search. It is the only one, and
    # a belief that excluded the truth would invalidate every value in the
    # section without any of the other controls noticing.
    ("ii_endgame.json", "truth_in_support_ok", "{:d}",
     "exact-II control, true deal in the belief's support",
     "The true deal must be one of the deals the belief admits"),
    # m = 2. Watched with its NEGATIVE-GAIN count as well as its gain, because
    # the negatives are what said the solver was broken and a silent return of
    # them is the regression that matters most.
    ("ii_endgame_m2.json", "mean_gain", "{:+.4f}",
     "exact-II m=2 gain from deviating",
     "tree and rollout, same champion strategy"),
    ("ii_endgame_m2.json", "n_solved", "{:d}",
     "exact-II m=2 positions solved", "positions were solved"),
    # The bounds on the layer. Watched because they are what stops the "lower
    # bound" reading from being restored by accident: the control count is the
    # only thing that says the interval is real, and the one-ply means are the
    # only figures in the paper that span the support cap. A drift in either
    # would turn a negative result back into the positive one it replaced.
    ("ii_bound_unsolved.json", "control_ok", "{:d}",
     "bounds control passed", "lie inside its own bounds. It does, on"),
    ("ii_bound_unsolved.json", "n_bounded", "{:d}",
     "positions bounded", "positions in\n$59$ games"),
    ("ii_bound_unsolved.json", "unsolved_lower_mean", "{:+.4f}",
     "unsolved lower bound", "bounded into"),
    ("ii_bound_unsolved.json", "unsolved_upper_mean", "{:+.4f}",
     "unsolved upper bound", "bounded into"),
    ("ii_bound_unsolved.json", "headline_solved_mean_matched", "{:+.4f}",
     "matched solved mean", "solved mean over the same\ngames is"),
    # The m = 1 layer, and the calibration that retracted the exploratory
    # reading. The gap slope is watched hardest: it is the number that turned a
    # negative result about Fish into a negative result about the instrument,
    # and a drift back would silently restore a conclusion that was withdrawn.
    # The correction the solver found, fixed and shipped. Watched at every
    # rung: a drift in the stacking figure would misstate what the site
    # actually gained, and that is the only one of the four that moved a
    # default.
    ("endgame_ask_stack.json", "diff", "{:+.4f}",
     "endgame ask, on top of what ships", "on top of what ships"),
    ("endgame_ask_replication.json", "pooled.diff", "{:+.4f}",
     "endgame ask, pooled vs champion", "vs champion, pooled"),
    ("endgame_ask_replication.json", "primary.diff", "{:+.4f}",
     "endgame ask, primary vs champion", "vs champion, registered"),
    ("endgame_ask_replication.json", "replication.diff", "{:+.4f}",
     "endgame ask, replication vs champion", "vs champion, replication"),
    # The negative result beside the positive one. The best-response line is
    # what says the correction does not reduce exploitability, and it is the
    # figure most likely to be quietly dropped if it ever drifted.
    # The deception sweep. The paired-vs-m0 rows are the withdrawal of the
    # ladder and the bound on what the shipped correction costs against a
    # foreign opponent; the m9 margin is the number that reverted a ship.
    ("xplay_sweep.json", "by_m.2.vs_m0", "{:+.3f}",
     "m<=2 against v0.3, paired vs none", "$m \\le 2$ & $+2.914$"),
    ("xplay_sweep.json", "by_m.3.vs_m0", "{:+.3f}",
     "m<=3 against v0.3, paired vs none", "$m \\le 3$ & $+2.568$"),
    ("xplay_sweep.json", "by_m.9.vs_m0", "{:+.3f}",
     "always-on against v0.3, paired vs none", "always on & $-2.160$"),
    ("endgame_m9_verdict.json", "diff", "{:+.4f}",
     "the sibling rung that was deception", "the amended coarse step to"),
    # The foreign-opponent check of the shipped correction, against an engine
    # from outside the project entirely (dylann4500's v0.7 over the process
    # bridge). Watched because it is the only measurement in the paper whose
    # opponent shares no code with this engine, and because its interval is
    # quoted for what it EXCLUDES (+0.1220): if these drifted, the paper
    # would misstate the one result that answers "against whom".
    ("foreign_m2_check.json", "effect", "{:+.4f}",
     "m<=2 effect vs Dylan v0.7", "at a power sized for\ndeception-scale flips"),
    ("foreign_m2_check.json", "ci95.0", "{:+.4f}",
     "m<=2 vs v0.7, CI low", "at a power sized for\ndeception-scale flips"),
    # The dose law (prereg/signal_dose_law.md). The verdict rests on one
    # interval covering one prediction and excluding the other, so all three
    # numbers are watched.
    ("signal_dose_law.json", "their_wrong_effect.mean", "{:+.4f}",
     "dose law, heuristic observed", "lands at\n$+0.0178$"),
    ("signal_dose_law.json", "their_wrong_effect.ci95.1", "{:+.4f}",
     "dose law, interval high", "$[+0.0048, +0.0308]$"),
    ("signal_dose_law.json", "predictions.multiplicative", "{:+.4f}",
     "dose law, the excluded prediction", "predicts $+0.0426$ against"),
    ("signal_dose_law.json", "dose_off_by", "{:.1%}",
     "dose law, how far the dose missed D", "the dose lands"),
    ("signal_dose_law.json", "their_wrong_effect.half_width", "{:.4f}",
     "dose law, realised half-width", "half-width of $0.0130$"),
    # The dose screen's uncertainties, added after an audit found the paper
    # printing $4.150$ for a quantity whose recorded half-width is 1.238 and
    # quoting two ratio columns that had no interval at all.
    ("signal_dose_arms.json",
     "opponents.dylan_v07.shipped.stuck_turns_half_width", "{:.3f}",
     "dylan_v07 stuck turns, half-width", "$4.150 \\pm 1.238$"),
    ("signal_dose_arms.json",
     "opponents.dylan_v07.stuck_turns_ratio_ci95.1", "{:.2f}",
     "dylan_v07 amplification, interval high", "$[2.32, 4.16]$"),
    ("signal_dose_arms.json",
     "opponents.dylan_v07.fires_per_stuck_turn_ci95.0", "{:.3f}",
     "dylan_v07 second gate, interval low", "$[0.868, 0.916]$"),
    ("signal_dose_arms.json",
     "opponents.ev_claim.fires_per_stuck_turn_ci95.1", "{:.3f}",
     "ev_claim second gate, interval high", "$[0.428, 0.497]$"),
    ("signal_dose_arms.json",
     "opponents.memory.ambiguous_cards_half_width", "{:.2f}",
     "memory ambiguity, half-width", "$26.02 \\pm 0.21$"),
    ("signal_dose_arms.json",
     "opponents.ev_claim.shipped.their_hits_half_width", "{:.2f}",
     "ev_claim ask-hits, half-width", "$27.94 \\pm 0.74$"),
    # Dylan's released ladder (scripts4/dylan_ladder_sweep.py). Six rungs, and
    # the paper's claim is that the ORDERING is his declaration error rate, so
    # each rung's margin and each rung's error rate are watched together --
    # a drift in either half would leave the correlation claim standing on a
    # table that no longer shows it.
    ("dylan_ladder_sweep.json", "opponents.dylan_v02.margin", "{:+.4f}",
     "ladder, v02 margin", "$+1.5283$ $[+1.3735, +1.6832]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v03.margin", "{:+.4f}",
     "ladder, v03 margin", "$+0.6133$ $[+0.4597, +0.7670]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v04.margin", "{:+.4f}",
     "ladder, v04 margin", "$+1.9867$ $[+1.8371, +2.1362]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v05.margin", "{:+.4f}",
     "ladder, v05 margin", "$+2.1233$ $[+1.9663, +2.2803]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v06.margin", "{:+.4f}",
     "ladder, v06 margin", "$+1.8850$ $[+1.7333, +2.0367]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v07.margin", "{:+.4f}",
     "ladder, v07 margin", "$+2.3600$ $[+2.2017, +2.5183]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v03.their_err", "{:.2%}",
     "ladder, v03 error rate", "$+0.6133$ $[+0.4597, +0.7670]$"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v07.their_err", "{:.2%}",
     "ladder, v07 error rate", "$+2.3600$ $[+2.2017, +2.5183]$"),
    # The ladder's headline statistic and the one that does NOT survive, both
    # derived by scripts4/dylan_ladder_sweep.py corr. The r = 0.95 was a shell
    # command until the bolded-claim guard refused it, which is the same
    # failure this manifest exists for, caught one layer up.
    ("dylan_ladder_correlation.json", "corr_margin_their_error", "{:.2f}",
     #: one line only -- the paper wraps between "at" and the maths, and an
     #: anchor spanning that break is absent from the file it is searched in.
     "ladder, margin against their error rate", "$r = 0.95$"),
    ("dylan_ladder_correlation.json", "corr_our_error_our_declares", "{:.2f}",
     "ladder, our error against our volume", "declaration count at $+0.71$"),
    ("dylan_ladder_correlation.json",
     "corr_our_error_our_declares_without_v04", "{:.2f}",
     "ladder, the same with v04 dropped", "collapses that to $+0.10$"),
    ("dylan_ladder_sweep.json", "v04_v06_spread", "{:.3f}",
     "ladder, the instrument check", "across those three is"),
    ("dylan_ladder_sweep.json", "opponents.dylan_v04.our_err", "{:.2%}",
     "ladder, our error rate against v04", "rate is $8.38\\%$ against their"),
    # The dose-linearity run (prereg/signal_dose_linearity.md). The verdict is
    # NEITHER, which rests on ONE interval excluding two predictions, so the
    # interval, both predictions and the power limit it had to clear are all
    # watched -- and so is the realised dose, because the prediction is a
    # formula evaluated at it.
    ("signal_dose_linearity.json", "their_wrong_effect.mean", "{:+.4f}",
     "dose linearity, observed", "their extra wrong declarations & $+0.0088$"),
    ("signal_dose_linearity.json", "their_wrong_effect.ci95.0", "{:+.4f}",
     "dose linearity, interval low", "their extra wrong declarations & $+0.0088$"),
    ("signal_dose_linearity.json", "predictions.linear", "{:+.4f}",
     "dose linearity, the linear prediction", "linear predicts & $+0.0201$"),
    ("signal_dose_linearity.json", "dose", "{:.3f}",
     "dose linearity, realised dose", "realised dose & $1.381$"),
    ("signal_dose_linearity.json", "dose_off_by", "{:.1%}",
     "dose linearity, how far off the replicated arm", "from the arm being"),
    ("signal_dose_linearity.json", "their_wrong_effect.half_width", "{:.4f}",
     "dose linearity, realised half-width", "the half-width of $0.0081$"),
    ("dose_linearity_points.json", "rows.1.shift_per_signal", "{:+.4f}",
     "the low-dose shift per signal", "shift is $+0.0095$ here"),
    ("dose_linearity_points.json", "constant_window_width", "{:.5f}",
     "how wide one constant's window still is", "a window $0.00003$ wide"),
    # The transfer law's supporting table (scripts4/dose_law_table.py). Every
    # figure here was hand arithmetic in the first draft of that paragraph and
    # two of the four were wrong in the last digit, which is the exact failure
    # this module exists for -- so the whole table is watched, including the
    # baseline that both registered predictions were derived from.
    ("heuristic_baseline.json", "both_sides.A_shipped.their_err", "{:.2%}",
     "heuristic's measured baseline", "the rate is $62.01\\%$"),
    ("heuristic_baseline.json", "both_sides.A_shipped.their_declares", "{:,d}",
     "heuristic's declarations, counted", "games and $1{,}166$ declarations"),
    ("heuristic_baseline.json", "n_games", "{:,d}",
     "the baseline bank's games", "bank of $1{,}000$ games"),
    ("dose_law_table.json", "shift_reference_fit", "{:+.4f}",
     "the shift fitted to the reference", "a log-odds shift of $+0.0669$"),
    ("dose_law_table.json", "shift_refit_all", "{:+.4f}",
     "the shift refitted on all three", "moves the shift to"),
    ("dose_law_table.json", "refit_moves_shift_by", "{:.1%}",
     "how far the refit moves it", "a change of $1.4\\%$"),
    ("dose_law_table.json", "rows.0.predicted_reference_fit", "{:+.4f}",
     "law table, ev_claim predicted", "$3.728$ & $+0.0172$"),
    ("dose_law_table.json", "rows.1.predicted_reference_fit", "{:+.4f}",
     "law table, dylan_v07 predicted", "$3.998$ & $+0.0454$"),
    ("dose_law_table.json", "rows.2.predicted_reference_fit", "{:+.4f}",
     "law table, heuristic predicted", "$1.166$ & $+0.0178$"),
    ("dose_law_table.json", "rows.2.baseline", "{:.2%}",
     "law table, heuristic baseline", "$1.166$ & $+0.0178$"),
    ("dose_law_table.json", "rows.0.declares_per_game", "{:.3f}",
     "law table, ev_claim declarations", "$7.96\\%$  & $3.728$"),
    ("dose_law_table.json", "rows.1.declares_per_game", "{:.3f}",
     "law table, dylan_v07 declarations", "$21.08\\%$ & $3.998$"),
    # The matched-dose study (prereg/signal_matched_dose.md). The first
    # positive generality result in this line, so the two intervals that
    # carry it and the doses that make them comparable are all watched.
    # These two anchors carry their intervals. The bare means were ambiguous
    # once the dose-law table quoted the same two observed effects a page
    # later, and widening them to the whole table cell fixes that while also
    # putting the interval bounds -- which nothing else watches, and on which
    # "both clear zero" rests -- under the drift check.
    ("matched_dose_scored.json",
     "opponents.dylan_v07.their_wrong_effect.mean", "{:+.4f}",
     "matched dose, reference channel", "$+0.0454$ $[+0.0326, +0.0582]$"),
    ("matched_dose_scored.json",
     "opponents.ev_claim.their_wrong_effect.mean", "{:+.4f}",
     "matched dose, test channel", "$+0.0172$ $[+0.0048, +0.0296]$"),
    ("matched_dose_scored.json", "opponents.dylan_v07.dose", "{:.3f}",
     "matched dose, reference dose", "dose tolerance at"),
    ("matched_dose_scored.json", "opponents.ev_claim.dose", "{:.3f}",
     "matched dose, test dose", "$2.766$ and"),
    ("matched_dose_calibration.json", "gate.mean", "{:+.4f}",
     "feasibility gate at D", "It cleared, at"),
    ("matched_dose_calibration.json", "common_dose_D", "{:.1f}",
     "the common dose D", "highest dose both reach is $D = "),
    # Why the dose differs (scripts4/signal_dose_screen.py). Watched because
    # the paper's claim is that the dose FACTORS, and a factorisation whose
    # terms drift stops being one.
    ("signal_dose_arms.json", "opponents.dylan_v07.shipped.stuck_turns_per_game",
     "{:.3f}", "dylan_v07 stuck turns, protocol off", "$4.150 \\pm 1.238$"),
    ("signal_dose_arms.json", "opponents.dylan_v07.fires_per_stuck_turn",
     "{:.3f}", "dylan_v07 second-gate pass rate", "$0.896$"),
    ("signal_dose_arms.json", "opponents.ev_claim.fires_per_stuck_turn",
     "{:.3f}", "ev_claim second-gate pass rate", "$0.462$"),
    ("signal_dose_arms.json",
     "opponents.dylan_v07.stuck_turns_ratio_signal_over_shipped",
     "{:.2f}", "dylan_v07 amplification", "$3.02$ $[2.32, 4.16]$"),
    ("signal_dose_arms.json", "opponents.dylan_v07.shipped.episodes_per_game",
     "{:.3f}", "dylan_v07 episodes a game", "$0.517 \\pm 0.065$ episodes a"),
    ("signal_dose_arms.json", "opponents.memory.shipped.episodes_per_game",
     "{:.3f}", "memory episodes a game", "$0.812 \\pm 0.082$"),
    # The generality run (prereg/signal_generality.md). Watched because the
    # conclusion is that the run does NOT answer its question, and the reason
    # is a comparison of doses -- so the doses are the numbers that carry it.
    ("signal_generality_self_12100000.json", "primary.mean", "{:+.4f}",
     "control against self, margin", "against\nitself the arm is"),
    ("signal_generality_ev_claim_12100000.json", "primary.mean", "{:+.4f}",
     "ev_claim, margin", "in the margin at"),
    ("signal_generality_ev_claim_12100000.json",
     "their_wrong_effects.B_signal.mean", "{:+.4f}",
     "ev_claim, opponent channel", "mechanism works through, at"),
    ("signal_generality_ev_claim_12100000.json",
     "signal_turns_per_game.B_signal", "{:.3f}",
     "ev_claim, signals a game", "$2.171$"),
    ("signal_generality_self_12100000.json",
     "signal_turns_per_game.B_signal", "{:.3f}",
     "self, signals a game", "$0.487$"),
    # The signalling budget (prereg/signal_budget.md). Watched because it is
    # a REFUTATION with three passing gates: the numbers that carry it are the
    # primary, the channel split it rests on, and the replication that lets
    # the primary be read at all.
    ("signal_budget_11700000.json", "primary.mean", "{:+.4f}",
     "budget 6 against uncapped, primary", "per-game budget of six is"),
    ("signal_budget_11700000.json", "effects.B_uncapped.mean", "{:+.4f}",
     "uncapped against shipped", "replicates a third time at"),
    ("signal_budget_11700000.json", "replication.z", "{:+.2f}",
     "replication z, both uncertainties", "a two-sample $z$ of"),
    ("signal_budget_11700000.json", "their_wrong_effects.C_budget6.mean",
     "{:+.4f}", "their extra wrong declarations under a budget of 6",
     "extra wrong declarations are"),
    ("signal_budget_11700000.json", "signal_turns_per_game.C_budget6",
     "{:.2f}", "signals a game under a budget of 6",
     "signals a game the opponents"),
    ("foreign_m2_check.json", "ci95.1", "{:+.4f}",
     "m<=2 vs v0.7, CI high", "at a power sized for\ndeception-scale flips"),
    ("foreign_m2_check.json", "n_pairs", "{:d}",
     "foreign-opponent paired games", "games per arm, the statistic being"),
    ("foreign_m2_check.json", "kv_margin_on", "{:+.3f}",
     "margin over v0.7, correction on", "beats v0.7 by"),
    ("foreign_m2_check.json", "kv_margin_off", "{:+.3f}",
     "margin over v0.7, correction off", "beats v0.7 by"),
    ("foreign_m2_check.json", "kv_set_share", "{:.1%}",
     "share of decided sets vs v0.7", "of decided sets across"),
    # The rule-matched rerun (R2) and the standard-scoring headline (R1) of
    # prereg/rules_award_baseline.md. These are the numbers the abstract now
    # asserts, so they are the last figures in the paper that may drift.
    ("award_headline.json", "estimate", "{:+.3f}",
     "standard-scoring headline", "restatement of this ladder's headline"),
    ("award_headline.json", "ci.0", "{:+.3f}",
     "standard-scoring headline CI low", "restatement of this ladder's headline"),
    ("award_headline.json", "ci.1", "{:+.3f}",
     "standard-scoring headline CI high", "restatement of this ladder's headline"),
    # The anchor here used to read "misdeclared-and-awarded sets", and it
    # stopped matching when that caption was rewritten -- the counter these
    # two figures come from holds the ALLOCATION class only, and calling it
    # "misdeclares" is what put the paper's headline decomposition at 9% when
    # the complete count says 57%. The figures did not move; the sentence
    # around them did. The anchor now quotes the clause that says which class
    # is being counted, so a future rewrite that drops the distinction again
    # breaks this check instead of passing it silently.
    ("award_headline.json", "x_misdeclares", "{:d}",
     "deployed allocation misdeclares in R1", "so awarded to the opponents"),
    ("award_headline.json", "y_misdeclares", "{:d}",
     "v0.3 allocation misdeclares in R1", "so awarded to the opponents"),
    # The deal-luck decomposition and the pairing table. Watched because
    # sec:dealluck overturns a premise the evaluation section stated for four
    # versions -- that raw win rates are dominated by the deal -- and a claim
    # that strong should not be allowed to drift away from the file behind it.
    ("deal_luck.json", "deal_component.corr_parities", "{:+.4f}",
     "parity correlation of the margin", "identically $-\\rho$"),
    ("deal_luck.json", "deal_component.pairing_efficiency", "{:.2f}",
     "seat-swap pairing efficiency", "the antisymmetric deal"),
    ("deal_luck.json", "deal_component.var_sum", "{:.3f}",
     "variance of the paired sum", "The sample variances are"),
    ("deal_luck.json", "deal_component.var_diff", "{:.3f}",
     "variance of the paired difference", "The sample variances are"),
    ("deal_luck.json", "overdispersion.our hit rate.corr_across_parities",
     "{:+.3f}", "hit-rate correlation across parities",
     "a symmetric\ntexture is not an advantage"),
    ("pairing_value.json", "runs.0.pairs.B_none.efficiency", "{:.1f}",
     "G1 arm pairing efficiency", "identical games"),
    # The signalling gate and the forced search, both reported in full in
    # sec:res-perpetual and sec:res-pathledger. Watched because each is quoted
    # for what its interval EXCLUDES -- the gate for failing to reach +0.15,
    # the search for clearing zero -- and a drifted bound would invert the
    # verdict rather than merely blur it.
    # Anchored on the table's own first row rather than on the prose that
    # follows it: `+0.1220` also occurs in the foreign-opponent discussion, and
    # a loose anchor let the effect match there while its own CI bound, three
    # characters away in the source, fell outside the window.
    ("signal_gate_confirm.json", "arms.C_measured.effect", "{:+.4f}",
     "signalling gate at 0.50", "A, signalling off"),
    ("signal_gate_confirm.json", "arms.C_measured.ci95.0", "{:+.4f}",
     "signalling gate CI low", "A, signalling off"),
    ("signal_gate_confirm.json", "arms.B_incumbent.effect", "{:+.4f}",
     "signalling gate replication arm", "A, signalling off"),
    ("forced_exhaustive_v07.json", "margin.effect", "{:+.4f}",
     "forced search margin vs v0.7", "guard 2 and which it passed exactly"),
    # What an avoided misdeclaration is worth, and what a deferral costs.
    #
    # Watched because the paper quotes +1.7898 twice and the file backing it was
    # silently replaced: error_value.py wrote results/error_value.json whatever
    # journal it read, so running it on the signalling journal overwrote the
    # stuck-gate fit with a different population's. Everything still built and
    # every other check passed, because this figure was not in the manifest.
    ("error_value.json", "arms.B_defer.value_per_avoided_error.est", "{:+.4f}",
     "value of one avoided error", "value of one avoided error"),
    ("error_value.json", "arms.B_defer.value_per_avoided_error.ci95.0",
     "{:+.4f}", "avoided-error value, CI low", "value of one avoided error"),
    ("error_value.json", "arms.B_defer.value_per_avoided_error.ci95.1",
     "{:+.4f}", "avoided-error value, CI high", "value of one avoided error"),
    ("error_value.json", "arms.B2_mid.value_per_avoided_error.est", "{:+.4f}",
     "avoided-error value, middle rung", "value of one avoided error"),
    # Not cost_per_deferral: the paper states that one rounded, as "about 0.36
    # to 0.43 sets each", and a manifest row that cannot match the prose it
    # guards is worse than no row. These three are quoted exactly, and they are
    # the inputs the paragraph's own arithmetic runs on.
    ("error_value.json", "arms.B_defer.errors_avoided_per_game", "{:.4f}",
     "errors avoided per game, deferral arm", "errors avoided at"),
    ("error_value.json", "arms.B_defer.declarations_deferred_per_game",
     "{:.3f}", "deferrals per game", "less often than average"),
    ("error_value.json",
     "arms.B_defer.deferred_per_game_where_no_error_avoided", "{:.3f}",
     "deferrals per game where nothing was avoided",
     "defer about"),
    # The declaration-risk finding: what a declaration risks is how many of the
    # six have never moved, not how many the declarer holds. Watched because
    # the paper prints the two curves side by side and the whole argument is
    # that the right-hand one is steeper.
    ("declarer_holding_self.json", "n_wholly_held", "{:,d}",
     "wholly-held declarations", "wholly-held\ndeclarations"),
    ("declarer_holding_self.json", "declarations_with_a_derived_card", "{:,d}",
     "declarations with a derived card", "least one derived card"),
    ("declarer_holding_self.json", "err_by_k.5.err", "{:.3f}",
     "error rate at five cards held", "declarer's own cards"),
    ("declarer_holding_self.json", "err_by_unmoved.5.n", "{:,d}",
     "declarations with five never located", "cards never located"),
    # The ceiling split. Watched because the paragraph's whole argument rests
    # on the two partial arms being told nearly the SAME number of cards, so a
    # drift in either pinned-per-game figure would silently dissolve it.
    ("ceiling_split.json", "arms.T_team.ceiling", "{:+.4f}",
     "teammate-knowledge ceiling", "its \\textbf{teammates'} cards"),
    ("ceiling_split.json", "arms.O_opp.ceiling", "{:+.4f}",
     "opponent-knowledge ceiling", "its \\textbf{opponents'} cards"),
    ("ceiling_split.json", "arms.T_team.pinned_by_cheat_per_game", "{:.1f}",
     "teammate arm, cards pinned per game", "cards pinned/game"),
    ("ceiling_split.json", "arms.O_opp.pinned_by_cheat_per_game", "{:.1f}",
     "opponent arm, cards pinned per game", "cards pinned/game"),
    # The concentration retest's verdict. Watched because tab:nulls retains the
    # v1 screen row and the dagger beneath it now carries the v2 outcome; a
    # drift there would leave a retained-as-history row pointing at nothing.
    ("concent_confirm.json", "arms.C_dose.effect", "{:+.4f}",
     "concentration at w=1.50", "worse than shipped"),
    ("concent_confirm.json", "arms.C_dose.ci95.1", "{:+.4f}",
     "concentration at w=1.50, CI high", "worse than shipped"),
    ("concent_confirm.json", "mechanism.C_dose.allocation_per_game", "{:.4f}",
     "allocation errors at w=1.50", "rose\nmonotonically instead"),
    ("foreign_award_check.json", "effect", "{:+.4f}",
     "rule-matched foreign effect", "under the award rule --- no reversal"),
    ("foreign_award_check.json", "ci95.0", "{:+.4f}",
     "rule-matched foreign CI low", "under the award rule --- no reversal"),
    ("foreign_award_check.json", "ci95.1", "{:+.4f}",
     "rule-matched foreign CI high", "under the award rule --- no reversal"),
    ("foreign_award_check.json", "kv_margin_on", "{:+.3f}",
     "margin over v0.7, award rule, on", "sets per game with the correction on"),
    ("foreign_award_check.json", "kv_margin_off", "{:+.3f}",
     "margin over v0.7, award rule, off", "sets per game with the correction on"),
    ("foreign_award_check.json", "misdeclares_kv", "{:d}",
     "misdeclared sets against this engine", "misdeclarations --- wholly-held"),
    ("foreign_award_check.json", "misdeclares_dylan", "{:d}",
     "misdeclared sets against v0.7", "misdeclarations --- wholly-held"),
    # R3/R4: the threshold sanity and the correction's re-pricing. R4 is the
    # number that withdrew a shipped knob, which makes it the figure whose
    # silent drift would be most misleading in either direction.
    # The anchor is "correction scores", not "against the same". The latter
    # is an ordinary three-word English phrase, and a paragraph added
    # elsewhere in the paper wrote it a second time -- which
    # test_no_watched_anchor_is_ambiguous caught, correctly, because a
    # duplicated anchor lets a drifted figure pass off a coincidental match
    # beside the first occurrence. An anchor has to name its own sentence.
    ("r4_award_check.json", "estimate", "{:+.4f}",
     "correction stack under award rule", "correction scores"),
    ("r4_award_check.json", "ci.0", "{:+.4f}",
     "correction stack CI low", "correction scores"),
    ("r4_award_check.json", "ci.1", "{:+.4f}",
     "correction stack CI high", "correction scores"),
    ("r4_award_check.json", "x_misdeclares", "{:d}",
     "correction-arm misdeclares", "misdeclares \\emph{more}"),
    ("r4_award_check.json", "y_misdeclares", "{:d}",
     "no-correction-arm misdeclares", "misdeclares \\emph{more}"),
    ("r3_lo_check.json", "estimate", "{:+.4f}",
     "threshold 0.97 vs 0.90, award rule", "against $0.90$ the difference"),
    ("r3_lo_check.json", "ci.0", "{:+.4f}",
     "threshold sweep CI low", "against $0.90$ the difference"),
    ("r3_lo_check.json", "ci.1", "{:+.4f}",
     "threshold sweep CI high", "against $0.90$ the difference"),
    # R5: the signalling re-measure. Watched because its summary sentence
    # changed from "buys no wins" to "right sign, unproven at this power" --
    # a drift in either direction would misstate a stays-off decision.
    ("r5_signal_check.json", "estimate", "{:+.4f}",
     "signalling under award rule", "the effect moves to"),
    ("r5_signal_check.json", "ci.0", "{:+.4f}",
     "signalling CI low", "the effect moves to"),
    ("r5_signal_check.json", "ci.1", "{:+.4f}",
     "signalling CI high", "the effect moves to"),
    ("r5_signal_check.json", "x_misdeclares", "{:d}",
     "misdeclares with signalling on", "cuts misdeclarations"),
    ("r5_signal_check.json", "y_misdeclares", "{:d}",
     "misdeclares with signalling off", "cuts misdeclarations"),
    # R6: the ported contestation term and the silence prior, both measured
    # against Dylan and both rejected. Watched because a negative result is
    # exactly the kind of number that rots quietly -- and because the
    # baseline margin in the same table is what the rejection is relative to.
    ("r6_screen.json", "arms.c+30.effect", "{:+.4f}",
     "contestation +3.0 vs baseline", "contestation $+3.0$"),
    ("r6_screen.json", "arms.c+10.effect", "{:+.4f}",
     "contestation +1.0 vs baseline", "contestation $+1.0$"),
    ("r6_screen.json", "arms.c-10.effect", "{:+.4f}",
     "contestation -1.0 vs baseline", "contestation $-1.0$"),
    ("r6_screen.json", "arms.d07.effect", "{:+.4f}",
     "silence 0.7 vs baseline", "silence $\\delta = 0.7$"),
    ("r6_screen.json", "arms.d09.effect", "{:+.4f}",
     "silence 0.9 vs baseline", "silence $\\delta = 0.9$"),
    ("r6_screen.json", "arms.c+30.base_margin", "{:+.3f}",
     "R6 baseline margin over v0.7", "baseline (neither knob)"),
    # The bridge defect that had been flattering this engine. Watched harder
    # than most rows, because a retraction is the one kind of number a project
    # has an incentive to let rot: every figure the correction turns on is
    # here, including the two accuracies that form its control.
    # The foreign choice curve: the opponent model measured against a policy
    # that is not a copy of ourselves. Watched in full because the whole point
    # is a sign, and a sign that drifts silently is the worst kind of stale.
    ("choice_curve_foreign.json", "alpha", "{:+.4f}",
     "foreign choice-model exponent", "and a fitted $\\alpha = \\mathbf{-1.0041}$"),
    ("choice_curve_foreign.json", "ci95.0", "{:+.4f}",
     "foreign exponent CI low", "and a fitted $\\alpha = \\mathbf{-1.0041}$"),
    ("choice_curve_foreign.json", "ci95.1", "{:+.4f}",
     "foreign exponent CI high", "and a fitted $\\alpha = \\mathbf{-1.0041}$"),
    ("choice_curve_foreign.json", "n_records", "{:,d}",
     "foreign asks in the corpus", "against v0.7 over"),
    ("choice_curve_foreign.json", "n_games", "{:d}",
     "foreign cross-engine games", "cross-engine games gives"),
    ("choice_curve_foreign.json", "curve.1.relative", "{:.3f}",
     "foreign O/E at depth 1", "observed / expected"),
    ("choice_curve_foreign.json", "curve.2.relative", "{:.3f}",
     "foreign O/E at depth 2", "observed / expected"),
    ("choice_curve_foreign.json", "curve.3.relative", "{:.3f}",
     "foreign O/E at depth 3", "observed / expected"),
    ("choice_curve_foreign.json", "curve.4.relative", "{:.3f}",
     "foreign O/E at depth 4", "observed / expected"),
    ("bridge_bug_price.json", "paired_difference", "{:+.4f}",
     "price of the bridge defect", "sets per game: real, and about"),
    ("bridge_bug_price.json", "ci95.0", "{:+.4f}",
     "bridge defect interval, low", "sets per game: real, and about"),
    ("bridge_bug_price.json", "ci95.1", "{:+.4f}",
     "bridge defect interval, high", "sets per game: real, and about"),
    ("bridge_bug_price.json", "n_paired_games", "{:,d}",
     "deals replayed under both bridges", "deals replayed under both bridge"),
    # The corrected head-to-head itself -- the one figure in this paper taken
    # through bridge revision 2, and the one the abstract now leads with.
    ("mega_match.json", "margin", "{:+.4f}",
     "corrected margin over v0.7", "margin & $\\mathbf{+2.3466}$"),
    ("mega_match.json", "ci95.0", "{:+.4f}",
     "corrected margin CI low", "margin & $\\mathbf{+2.3466}$"),
    ("mega_match.json", "ci95.1", "{:+.4f}",
     "corrected margin CI high", "margin & $\\mathbf{+2.3466}$"),
    ("mega_match.json", "n_games", "{:,d}",
     "games in the corrected head-to-head", "games on the same deals the retracted"),
    ("mega_match.json", "kv_set_share", "{:.2%}",
     "corrected set share", "of decided) \\\\"),
    ("mega_match.json", "declare_right_kv", "{:.2%}",
     "our declaration accuracy, corrected", "declaration accuracy &"),
    ("mega_match.json", "declare_right_dylan", "{:.2%}",
     "their declaration accuracy, corrected", "declaration accuracy &"),
    ("mega_match.json", "ask_hit_kv", "{:.2%}",
     "our ask hit rate, corrected", "ask hit rate &"),
    ("mega_match.json", "ask_hit_dylan", "{:.2%}",
     "their ask hit rate, corrected", "ask hit rate &"),
    ("mega_match.json", "bridge_rev", "{:d}",
     "bridge revision of the head-to-head", "through bridge\nrevision~"),
    ("bridge_bug_price.json", "their_declare_acc_rev1", "{:.2%}",
     "their declaration accuracy, defective bridge",
     "their declaration accuracy rises from"),
    ("bridge_bug_price.json", "their_declare_acc_rev2", "{:.2%}",
     "their declaration accuracy, repaired bridge",
     "their declaration accuracy rises from"),
    ("bridge_bug_price.json", "our_declare_acc_rev1", "{:.2%}",
     "our declaration accuracy, defective bridge",
     "while this engine's moves from"),
    ("bridge_bug_price.json", "our_declare_acc_rev2", "{:.2%}",
     "our declaration accuracy, repaired bridge",
     "while this engine's moves from"),
    ("ii_exploit_after_split_m1.json", "parts.best response.diff", "{:+.4f}",
     "best response after the fix", "what a best response takes"),
    ("ii_exploit_after_split_m1.json", "parts.policy's own value.diff",
     "{:+.4f}", "policy value after the fix", "the policy's own value &"),
    ("ii_exploit_after_split_m1.json", "n", "{:d}",
     "positions paired across policies", "Over $285$"),
    ("ii_one_move_m1.json", "champ_p_mean", "{:.3f}",
     "m=1 champion ask hit rate", "$m = 1$ & $p ="),
    ("ii_one_move_m1.json", "best_p_mean", "{:.3f}",
     "m=1 better ask hit rate", "$m = 1$ & $p = 0.799$ & $p ="),
    ("ii_one_move_m1.json", "champion_certain_and_beaten", "{:d}",
     "m=1 certain asks that were still wrong",
     "the champion asked a card it was"),
    ("ii_bound_m1.json", "control_ok", "{:d}",
     "m=1 bounds control passed", "The control holds on"),
    ("ii_bound_m1.json", "oneply_already_optimal", "{:d}",
     "m=1 positions where one move is the whole exploit",
     "One deviation attains the optimum on"),
    ("ii_bound_analysis.json", "gap_slope_t_m1", "{:+.2f}",
     "m=1 gap-vs-support t", "Slope $+0.0236$ per deal, $t ="),
    ("ii_bound_analysis.json", "oneply_already_optimal", "{:d}",
     "positions where one move is the whole exploit", "of the $100$"),
    ("ii_bound_analysis.json", "mean_gap_exact_minus_oneply", "{:+.4f}",
     "exact minus one-ply gap", "the gap averages"),
    ("ii_bound_analysis.json", "positions_with_trivial_upper", "{:d}",
     "positions with a trivial upper bound", "positions\n\\emph{every} deal"),
    ("ii_bound_analysis.json", "oneply_narrow_mean", "{:+.4f}",
     "one-ply gain at or below the cap", "At or below the cap it averages"),
    ("ii_bound_analysis.json", "oneply_wide_mean", "{:+.4f}",
     "one-ply gain above the cap", "($n = 169$); above it,"),
    # The analysis's own position count is not watched: it is the same 248 the
    # collector reports, from the same journal, and the paper quotes it once.
    # Two entries on one number check the number twice and the paper once.
    # The exploitability lower bound. Watched because it is the only figure in
    # the paper that contradicts a sentence the paper used to make -- "we
    # compute no exploitability bound" -- and a number that overturns a claim
    # is the one worst served by drifting quietly.
    ("ii_first_endgame.json", "mean_gain_per_game", "{:+.4f}",
     "exact deviation gain per game", "exact, \\textbf{one} endgame decision"),
    ("ii_first_endgame.json", "none_pinned", "{:d}",
     "games where the belief pinned every card",
     "the belief has \\emph{pinned every card}"),
    # The replicated endgame-policy gain. Watched with its heterogeneity
    # statistic, because the interval alone is what the +0.490 cell also had.
    ("exact_endgame_team_pooled.json", "pooled_mean", "{:+.4f}",
     "exact endgame policy, pooled gain", "pooled, $1200$ pairs"),
    # Cross-play. Watched because it is the figure that decides whether the
    # gain is better play or an exploit, and those get read differently.
    ("exact_endgame_team_vsv03_pooled.json", "pooled_mean", "{:+.4f}",
     "exact endgame policy, vs the v0.3 champion",
     "which the solver's opponent model is simply"),
    ("exact_endgame_team_pooled.json", "cochran_q", "{:.3f}",
     "exact endgame policy, Cochran Q",
     "degrees of freedom: the three blocks are as"),
    # The arm that came out of it, with its interval, because the section's
    # point is that a real effect can sit under the bar.
    ("claim_feasibility_verdict.json", "estimate", "{:+.3f}",
     "claim feasibility estimate", "over $6000$\npre-registered pairs"),
    ("claim_feasibility_verdict.json", "ci.0", "{:+.3f}",
     "claim feasibility interval, low", "over $6000$\npre-registered pairs"),
    ("claim_feasibility_verdict.json", "ci.1", "{:+.3f}",
     "claim feasibility interval, high", "over $6000$\npre-registered pairs"),
    # G1: what the mis-signed opponent model costs in play. The two arms are
    # watched separately because the section's argument needs BOTH -- that
    # removing the model loses, and that adopting the fitted exponent loses
    # more. Either alone reads as a different result.
    ("g1_gamma_cost.json", "arms.B_none.effect", "{:+.4f}",
     "G1 arm B, no opponent model", "respect but one scalar, played on"),
    ("g1_gamma_cost.json", "arms.C_measured.effect", "{:+.4f}",
     "G1 arm C, his fitted exponent", "respect but one scalar, played on"),
    # thousands separator: the paper writes 1{,}600, which main() normalises
    ("g1_gamma_cost.json", "n_games", "{:,d}",
     "G1 games", "respect but one scalar, played on"),
    # The margin decomposition. This is the one that re-prices the headline, so
    # the residual and the leak are both pinned: quoting the leak without the
    # residual, or the other way round, would let the section drift into a
    # claim the file does not support.
    # On the headline block now, not the 600-game probe. The probe's own
    # figures stay watched below, because the section quotes both and says
    # they agree.
    ("margin_decomposition.json", "headline_block.margin.mean", "{:+.4f}",
     "decomposed margin", "Fifty-seven per cent of the margin"),
    ("margin_decomposition.json", "headline_block.residual.mean", "{:+.4f}",
     "margin residual after declarations", "Fifty-seven per cent of the margin"),
    ("margin_decomposition.json", "headline_block.their_ownership_per_game",
     "{:.4f}", "their ownership-class error rate",
     "Fifty-seven per cent of the margin"),
    ("margin_decomposition.json", "headline_block.their_per_game", "{:.3f}",
     "their wrong declarations per game", "times a game against their"),
    ("margin_decomposition.json", "decomposition.their_errors.total_per_game",
     "{:.3f}", "the probe's error rate, quoted as the agreeing figure",
     "the probe put their error rate at"),
    ("margin_decomposition.json", "decomposition.their_errors.ownership_per_game",
     "{:.3f}", "the probe's ownership-class rate",
     "obvious hypothesis about the ownership-class leak"),
    ("margin_decomposition.json", "mechanism.dark", "{:d}",
     "their misplaced cards that never moved in public",
     "never publicly moved since the deal"),
    ("margin_decomposition.json", "mechanism.publicly_pinned", "{:d}",
     "their misplaced cards that were publicly ours",
     "publicly pinned to us by an ask we had won"),
    # The path ledger, and the gate arm it licensed. The margin and the
    # mechanism are both watched: this section's whole point is that they
    # disagree, so quoting either alone would be a different result.
    ("stuck_gate_confirm.json", "ledger.A_shipped.gate.err", "{:.3f}",
     "the doomed-ask gate's error rate", "the doomed-ask gate &"),
    ("stuck_gate_confirm.json", "ledger.A_shipped.forced.err", "{:.3f}",
     "the forced path's error rate", "forced (no legal ask) &"),
    ("stuck_gate_confirm.json", "arms.B_defer.effect", "{:+.4f}",
     "gate deferral, margin", "so the deferral is"),
    ("stuck_gate_confirm.json", "ledger.B_defer.gate.err", "{:.3f}",
     "gate error rate once deferred", "falls from $0.281$ to"),
]


def _present(s: str, near: str) -> bool:
    """Is ``s`` in ``near`` as a whole number rather than as a substring?

    A bare ``s in near`` is close to no test at all for a short format. In a
    1400-character window, "5" matches every digit that occurs anywhere; "35"
    matched 13 of the values 0--59, INCLUDING the 28 and 32 this module's
    docstring names as the stale values it exists to catch; and the two
    continuation-length rows share an anchor and each passed on the OTHER's
    value, so swapping the two numbers in the paper reported clean. Requiring
    that no digit or decimal point abut the match is what makes the check able
    to fail.
    """
    return re.search(r"(?<![\d.])" + re.escape(s) + r"(?![\d.])",
                     near) is not None


def main() -> int:
    text = PAPER.read_text(encoding="utf-8")
    # LaTeX spells some characters differently from Python's formatter, and a
    # literal search for the formatted string then misses every figure written
    # that way -- a miss that reads exactly like drift. "11.7\%" is the
    # percent sign; "13{,}290" is the thousands separator, braced so TeX keeps
    # the digits kerned as one number. Normalising both here is a search
    # convenience, not an edit to the paper.
    text = text.replace("\\%", "%").replace("{,}", ",")
    print("do the paper's most drift-prone figures still match the files?\n")
    print(f"{'figure':<34}{'file value':>12}   in paper")
    missing = []
    ambiguous = []
    for fname, path, fmt, name, anchor in WATCH:
        if not fname.startswith("duel:") and not (ROOT / "results" / fname).exists():
            print(f"{name:<34}{'-':>12}   results file absent")
            missing.append(f"{name} (results file absent)")
            continue
        try:
            val = _get(_load(fname), path)
        except FileNotFoundError as e:
            print(f"{name:<34}{'-':>12}   *** {e}")
            missing.append(f"{name} ({e})")
            continue
        except (KeyError, IndexError, TypeError):
            print(f"{name:<34}{'-':>12}   *** key {path!r} gone from {fname}")
            missing.append(name)
            continue
        s = fmt.format(val)
        # EVERY occurrence of the anchor, not just the first. This used to be
        # text.find(), which silently checked the wrong sentence whenever a
        # phrase recurred: "a p90 of" appears at line 668 and again at 1409, so
        # a figure correctly written at 1409 was reported missing because the
        # window sat around 668. A check that inspects the wrong place and says
        # "no" is a nuisance; the same bug reporting "yes" off a coincidental
        # match elsewhere is the real hazard.
        # The anchor is normalised the SAME way the text was. Without this the
        # two disagree: an anchor written "72.5\\%" is absent from normalised
        # text, and one written "72.5%" is absent from the paper as authored --
        # so whichever way an anchor is written, one of the two checks that
        # look for it reports it missing.
        anchor = anchor.replace("\\%", "%").replace("{,}", ",")
        spots = []
        at = text.find(anchor)
        while at >= 0:
            spots.append(at)
            at = text.find(anchor, at + 1)
        if not spots:
            print(f"{name:<34}{s:>12}   *** ANCHOR GONE: {anchor[:34]!r}")
            missing.append(f"{name} (anchor text no longer in the paper)")
            continue
        # A signed value may appear with its sign stripped by surrounding
        # LaTeX, so accept the bare digits too -- but only near the anchor.
        ok = False
        for at in spots:
            near = text[max(0, at - WINDOW):at + WINDOW]
            if _present(s, near) or _present(s.lstrip("+"), near):
                ok = True
                break
        note = "" if len(spots) == 1 else f"  (anchor x{len(spots)})"
        print(f"{name:<34}{s:>12}   "
              f"{'yes' if ok else '*** NOT NEAR ANCHOR'}{note}")
        if not ok:
            missing.append(name)
        elif len(spots) > 1:
            ambiguous.append((name, len(spots), anchor))

    print()
    if ambiguous:
        # Not a failure: the value was found beside one of them. But an
        # ambiguous anchor is one edit away from pointing at the wrong sentence
        # and passing there, so it gets named rather than tolerated silently.
        print(f"{len(ambiguous)} anchor(s) occur more than once. The value was "
              f"found beside one of\nthem, which is enough today and is one "
              f"edit from being enough for the wrong\nreason. Tighten these:")
        for name, n, anchor in ambiguous:
            print(f"  - {name}: {anchor[:48]!r} appears {n} times")
        print()
    if missing:
        print(f"{len(missing)} figure(s) in the paper no longer match the "
              f"results files:")
        for m in missing:
            print(f"  - {m}")
        print("\nEither refresh the paper, or say in the text when the figure "
              "was taken.\nA stale number reads exactly like a fresh one, "
              "which is the whole problem.")
        return 1
    print("Every watched figure still appears in the paper as the results "
          "files hold it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
