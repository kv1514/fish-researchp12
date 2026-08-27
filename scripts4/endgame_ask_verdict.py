"""Pool the eight endgame-ask blocks and read the pre-registered verdict.

prereg/endgame_ask_weights.md fixed the arm, the size, the seeds and what each
outcome means before any block ran. This does the pooling and prints the answer
the document already committed to, rather than deciding what the answer means
after seeing it.

The per-pair differentials are stored, so the pooled interval is computed from
the 2000 pairs directly rather than from eight block means -- pooling means of
equal-sized blocks would give the same point estimate but a slightly different
interval, and there is no reason to take the worse one when the pairs are here.

The engine digest of every block is required to match. Blocks run against
different code are different experiments, and averaging them would hide that
behind one number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"
PREFIX = "endgame-info-b"
EXPECTED = 8


def main() -> int:
    rows = [json.loads(x) for x in DUELS.read_text().splitlines() if x.strip()]
    b = [r for r in rows if r.get("label", "").startswith(PREFIX)]
    if len(b) != EXPECTED:
        print(f"{len(b)} blocks, expected {EXPECTED}. The pre-registration "
              f"says all eight before any are read.")
        return 1
    digs = sorted(set(r["engine"]["digest"] for r in b))
    if len(digs) > 1:
        print(f"blocks ran against {len(digs)} different engines: {digs}. "
              f"Refusing to pool.")
        return 1
    diffs = [d for r in b for d in r["diffs"]]
    n = len(diffs)
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = m - 1.96 * se, m + 1.96 * se
    print(f"engine {digs[0]}; {len(b)} blocks, {n} pairs")
    for r in b:
        print(f"   {r['label']:<20} n={r['n_pairs']:<5} "
              f"diff {r['diff_mean']:+.3f}")
    print(f"\npooled: diff {m:+.4f} sets, 95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  (half-width {1.96*se:.4f}; the pre-registration predicted "
          f"about 0.047)")
    nulls = sum(r["nulls"] for r in b)
    print(f"  nulls {nulls} (X {sum(r['x_nulls'] for r in b)}, "
          f"Y {sum(r['y_nulls'] for r in b)}), "
          f"timeouts {sum(r['timeouts'] for r in b)}, "
          f"dropped {sum(r['dropped_pairs'] for r in b)}")

    if lo > 0:
        verdict = ("pays", "Outcome 1: the correction pays in play.")
    elif hi < 0:
        verdict = ("costs", "Outcome 2: the correction costs in play. The "
                   "offline gain does not survive whole games.")
    else:
        verdict = ("undetected",
                   "Outcome 3: no detectable effect at this resolution. The "
                   "pre-registration\n  called this the most likely outcome "
                   "and said in advance it is NOT evidence\n  of no effect: "
                   "the arm improves exact endgame decisions on held-out\n  "
                   "positions and this test cannot see that in whole-game "
                   "play. It is not\n  shipped on the strength of the offline "
                   "number, and no further pairs are\n  run to chase the "
                   "interval -- that would need a new pre-registration.")
    print(f"\n{verdict[1]}")
    out = ROOT / "results" / "endgame_ask_verdict.json"
    out.write_text(json.dumps({
        "n_pairs": n, "n_blocks": len(b), "engine": digs[0],
        "diff_mean": m, "ci95": [lo, hi], "half_width": 1.96 * se,
        "verdict": verdict[0],
        "blocks": [{"label": r["label"], "n": r["n_pairs"],
                    "diff": r["diff_mean"]} for r in b]}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
