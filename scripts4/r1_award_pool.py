"""Pool the R1-award blocks (prereg/rules_award_baseline.md, design R1).

Reads every ``R1-award-*`` cell from results/v04_duels.jsonl, dedupes by
label keeping the last, refuses to pool across engine fingerprints or rule
sets, and writes results/award_headline.json with the fixed-effect estimate.

    py scripts4/r1_award_pool.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Exactly the numbered blocks; the smoke cell (R1-award-smoke) is archive,
#: not evidence.
BLOCK = re.compile(r"^R1-award-\d{2}$")


def main() -> int:
    cells = {}
    for line in (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        label = r.get("label") or ""
        if BLOCK.match(label):
            if label in cells:
                print(f"  note: {label} rerun; keeping the last")
            cells[label] = r
    if not cells:
        print("no R1-award blocks found")
        return 1
    engines = {(c.get("engine") or {}).get("digest")
               if isinstance(c.get("engine"), dict) else c.get("engine")
               for c in cells.values()}
    rulesets = {json.dumps(c.get("rules"), sort_keys=True)
                for c in cells.values()}
    if len(engines) > 1:
        print(f"REFUSING to pool: {len(engines)} engine fingerprints "
              f"{sorted(engines)}")
        return 1
    if len(rulesets) > 1:
        print(f"REFUSING to pool: {len(rulesets)} rule sets")
        return 1
    rules = json.loads(next(iter(rulesets)))
    if rules.get("wrong_distribution_outcome") != "opponent":
        print("REFUSING: blocks were not played under opponent-award")
        return 1
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
    lo, hi = m - 1.96 * se, m + 1.96 * se
    print(f"{len(cells)} blocks, {n} pairs, engine {next(iter(engines))}")
    print(f"  deployed config vs v0.3 champion, opponent-award: "
          f"{m:+.4f} [{lo:+.4f}, {hi:+.4f}] sets/pair")
    print(f"  misdeclared (awarded) sets: deployed {mis_x}, v0.3 {mis_y}")
    out = {"n_pairs": n, "n_blocks": len(cells), "estimate": m,
           "ci": [lo, hi], "se": se, "rules": rules,
           "engine": next(iter(engines)),
           "x_misdeclares": mis_x, "y_misdeclares": mis_y,
           "labels": sorted(cells)}
    (ROOT / "results" / "award_headline.json").write_text(
        json.dumps(out, indent=1))
    print("wrote results/award_headline.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
