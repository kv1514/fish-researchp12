"""Store the ceiling interaction instead of computing it in the LaTeX.

``declaration_timing.py`` measures three ceilings over the same 600 games: the
truth given only when the seat DECLARES (D), only when it ASKS (K), and in both
channels (T). The quantity the paper actually argues from is neither of those --
it is what the two channels are worth TOGETHER beyond the sum of their parts:

    interaction        = T - (D + K)
    interaction share  = interaction / T

Both were being computed in the prose. That is precisely the failure mode
``scripts4/unwatched_claims.py`` was written after: Table~\\ref{tab:exact}'s
rates were derived in the LaTeX from counts the pipeline stored, so the printed
number was never a stored number and nothing could check it.

This is pure arithmetic on the arms already in the file, so it does not re-run
the 600 games -- it makes a number the document asserts into a number a file
holds.

    py scripts4/derive_ceiling_interaction.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "results" / "declaration_timing.json"


def main() -> int:
    d = json.loads(DEST.read_text())
    arms = d["arms"]
    D = arms["D_declare"]["ceiling"]
    K = arms["K_ask"]["ceiling"]
    T = arms["T_both"]["ceiling"]
    inter = T - (D + K)
    d["derived"] = {
        "D_plus_K": D + K,
        "T": T,
        "interaction": inter,
        "interaction_share_of_T": inter / T if T else float("nan"),
        "note": "arithmetic on this file's own arms; no games were replayed",
    }
    DEST.write_text(json.dumps(d, indent=1))
    print(f"D {D:+.4f}  K {K:+.4f}  D+K {D+K:+.4f}  T {T:+.4f}")
    print(f"interaction {inter:+.4f}  = {inter/T:.1%} of T")
    print(f"wrote {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
