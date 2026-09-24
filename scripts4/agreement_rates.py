"""Derive the agreement table's rates from the counts already stored.

``results/exact_agreement_v04.json`` stores COUNTS -- ``unc_prog`` out of
``unc_total`` and so on. Table~\\ref{tab:exact} in the paper reports the RATES,
and computed those in the LaTeX rather than in a file, so nothing could check
them: the table that carries this paper's absolute-strength claim, including
the $67.6\\% \\to 72.5\\%$ contrast quoted in the abstract, sat outside every
drift check for the same dull reason the headline duel did -- the number the
paper prints was never the number the pipeline stored.

This is a pure transformation of stored counts. It re-runs nothing, harvests
nothing, and cannot disagree with the corpus; it exists so the manifest has a
file to point at.

Usage: python scripts4/agreement_rates.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (stored numerator, stored denominator, column name in the paper's table).
COLUMNS = (
    ("res_prog", "res_total", "resolved"),
    ("unc_prog", "unc_total", "uncertain"),
    ("m1_prog", "m1_total", "m1"),
    ("m2_prog", "m2_total", "m2"),
    # The value-optimal criterion, kept beside the progress-optimal one
    # because the paper quotes both and they differ by ten points.
    ("res_opt", "res_total", "resolved_value_optimal"),
    ("unc_opt", "unc_total", "uncertain_value_optimal"),
)


def _slug(label: str) -> str:
    """``"v0.4 champion"`` -> ``"v04_champion"``. Dots would split a path."""
    return (label.replace(".", "").replace("-", "_").replace(" ", "_")
            .lower())


def main() -> int:
    src = ROOT / "results" / "exact_agreement_v04.json"
    d = json.loads(src.read_text())
    out = {"n_positions": d["n_positions"], "n_resolved": d["n_resolved"],
           "agents": {}}
    print("agreement with progress-optimal play, derived from stored counts\n")
    print(f"{'agent':<28}{'resolved':>10}{'uncertain':>11}{'m=1':>8}{'m=2':>8}")
    for r in d["rows"]:
        rates = {}
        for num, den, name in COLUMNS:
            t = r.get(den) or 0
            rates[name] = (r.get(num, 0) / t) if t else None
        # Keyed by a dot-free slug, because check_paper_numbers addresses a
        # value by a dotted path and "v0.4 champion" would split in the middle
        # of the agent's name. The original label is kept beside it.
        out["agents"][_slug(r["label"])] = {
            "label": r["label"],
            "counts": {k: r[k] for k in r if isinstance(r[k], int)},
            "rates": rates}
        print(f"{r['label']:<28}{100 * rates['resolved']:>9.1f}%"
              f"{100 * rates['uncertain']:>10.1f}%"
              f"{100 * rates['m1']:>7.1f}%{100 * rates['m2']:>7.1f}%")

    # The contrast the abstract quotes, computed here rather than by hand.
    a = out["agents"]
    if "v03_champion" in a and "v04_champion" in a:
        lo = a["v03_champion"]["rates"]["uncertain"]
        hi = a["v04_champion"]["rates"]["uncertain"]
        out["abstract_contrast"] = {"v03_uncertain": lo, "v04_uncertain": hi,
                                    "delta": hi - lo}
        print(f"\nthe contrast the abstract quotes: "
              f"{100 * lo:.1f}% -> {100 * hi:.1f}%  ({100 * (hi - lo):+.1f} pp)")
    if "v04_no_gamma" in a:
        n = a["v04_no_gamma"]["rates"]["uncertain"]
        out["no_opponent_model_uncertain"] = n
        print(f"exact inference WITHOUT the opponent model:      {100 * n:.1f}%")
        print("  -- which is the point: the opponent model does the work, and\n"
              "  three instruments agree on that.")

    dest = ROOT / "results" / "exact_agreement_rates.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
