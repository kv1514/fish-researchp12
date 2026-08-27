"""Pool the R3 (declaration threshold) and R4 (endgame stack) award-rule
blocks of prereg/rules_award_baseline.md.

Same discipline as r1_award_pool.py: dedupe by label keeping the last,
refuse to pool across engine digests or rule sets, require opponent-award.

    py scripts4/r34_award_pool.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GROUPS = {
    "r4_award_check.json": re.compile(r"^R4-award-\d{2}$"),
    "r3_hi_check.json": re.compile(r"^R3-hi-\d{2}$"),
    "r3_lo_check.json": re.compile(r"^R3-lo-\d{2}$"),
}


def pool(pat):
    cells = {}
    for line in (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if pat.match(r.get("label") or ""):
            cells[r["label"]] = r
    if not cells:
        return None
    digs = {(c.get("engine") or {}).get("digest") for c in cells.values()}
    rules = {json.dumps(c.get("rules"), sort_keys=True) for c in cells.values()}
    assert len(digs) == 1, f"engine digests differ: {digs}"
    rd = json.loads(next(iter(rules)))
    assert len(rules) == 1 and rd.get(
        "wrong_distribution_outcome") == "opponent", "rules differ or not award"
    diffs = []
    mis_x = mis_y = 0
    for c in cells.values():
        diffs.extend(c["diffs"])
        mis_x += c.get("x_misdeclares", 0)
        mis_y += c.get("y_misdeclares", 0)
    n = len(diffs)
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    se = (var / n) ** 0.5
    return {"n_pairs": n, "n_blocks": len(cells), "estimate": m,
            "ci": [m - 1.96 * se, m + 1.96 * se], "se": se,
            "engine": next(iter(digs)), "rules": rd,
            "x_misdeclares": mis_x, "y_misdeclares": mis_y}


def main() -> int:
    for fname, pat in GROUPS.items():
        out = pool(pat)
        if out is None:
            print(f"{fname}: no blocks yet")
            continue
        (ROOT / "results" / fname).write_text(json.dumps(out, indent=1))
        lo, hi = out["ci"]
        print(f"{fname}: {out['n_blocks']} blocks, {out['n_pairs']} pairs, "
              f"{out['estimate']:+.4f} [{lo:+.4f}, {hi:+.4f}]  "
              f"misdeclares X {out['x_misdeclares']} / Y {out['y_misdeclares']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
