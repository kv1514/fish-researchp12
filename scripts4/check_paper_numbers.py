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
PAPER = ROOT / "paper" / "fishbot_v04.tex"


def _get(d, path):
    for k in path.split("."):
        if isinstance(d, list):
            k = int(k)
        d = d[k]
    return d


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
     "posterior sampling budget, from 160 draws to 480"),
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
     "corr with deplete", "correlates with"),
    ("target_feature_fit.json", "p_success_abscorr.certain", "{:.3f}",
     "corr with certain", "correlates with"),
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
     "final 6000, is"),
    ("settle_verdict.json", "secondary.pooled.fe", "{:.3f}",
     "lookahead, unselected pool", "secondary --- all ten unselected cells"),
    ("settle_verdict.json", "n_pairs", "{:d}", "pairs in the settling run",
     "final 6000, is"),
    # The programme total. It was quoted as 15,600 in the abstract and again in
    # the results, and matched nothing: not the table (9,700), not the record
    # with the stacking run added (15,700). Nobody could recompute it, so it
    # drifted unchallenged. It is now computed from the duel record.
    ("settle_verdict.json", "programme_pairs", "{:,d}",
     "the lookahead programme's cost", "duplicate\ndeal-pairs across four"),
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
    ("perpetual_study.json", "normal.half_suits", "{:d}",
     "half-suits measured", "Over the $1800$ half-suits of"),
    ("perpetual_study.json", "normal.stuck_half_suits", "{:d}",
     "half-suits that get stuck", "Over the $1800$ half-suits of"),
    ("perpetual_study.json", "normal.share_of_half_suits_stuck", "{:.1%}",
     "share of half-suits stuck", "Over the $1800$ half-suits of"),
    ("perpetual_study.json", "normal.null_rate_when_stuck", "{:.1%}",
     "null rate when stuck", "and they are nulled"),
    ("perpetual_study.json", "normal.null_rate_when_not_stuck", "{:.2%}",
     "null rate when not stuck", "half-suits that never get stuck"),
    ("perpetual_study.json", "normal.null_rate_ratio", "{:.0f}",
     "ratio between the two", "half-suits that never get stuck"),
    ("perpetual_study.json", "normal.stuck_share_of_all_nulls", "{:.0%}",
     "stuck share of all nulls", "so they account for"),
    # The signalling contrast is the one place a null rate is quoted as a
    # BEFORE and an AFTER, so the two have to move together or the 20%
    # reduction stops being one.
    ("perpetual_study.json", "normal.nulls_per_game", "{:.3f}",
     "nulls per game", "cuts nulls from"),
    ("perpetual_study.json", "signalling.nulls_per_game", "{:.3f}",
     "nulls per game, signalling on", "cuts nulls from"),
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
     "declare-beats-wait bar", "would beat\nwaiting wherever the MAP is right"),
    ("stuck_claim_value.json", "null_rate", "{:.1%}",
     "null rate the bar comes from", "accepting the measured"),
    # The seventh cell of the adaptive family, and the first in the TRADING
    # direction. Quoted in the advice section and in the results table, so a
    # stale figure here is advice to a human.
    ("retake_bonus_verdict.json", "estimate", "{:.3f}",
     "rewarding the re-take", "(\\texttt{jobs/PREREGISTRATION\\_retake\\_bonus.md}), and it returns"),
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
        f = ROOT / "results" / fname
        if not f.exists():
            print(f"{name:<34}{'-':>12}   results file absent")
            missing.append(f"{name} (results file absent)")
            continue
        try:
            val = _get(json.loads(f.read_text()), path)
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
