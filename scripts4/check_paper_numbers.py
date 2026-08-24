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
     "The whole\neleven-term fit explains"),
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
        at = text.find(anchor)
        if at < 0:
            print(f"{name:<34}{s:>12}   *** ANCHOR GONE: {anchor[:34]!r}")
            missing.append(f"{name} (anchor text no longer in the paper)")
            continue
        # A signed value may appear with its sign stripped by surrounding
        # LaTeX, so accept the bare digits too -- but only near the anchor.
        near = text[max(0, at - WINDOW):at + WINDOW]
        ok = _present(s, near) or _present(s.lstrip("+"), near)
        print(f"{name:<34}{s:>12}   {'yes' if ok else '*** NOT NEAR ANCHOR'}")
        if not ok:
            missing.append(name)

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
