"""How many games does an arm actually change?

WHY THIS EXISTS. P51's D1 and `gamma_team = 1.4` returned the same margin to
four decimals in both populations, and the only way to tell "two arms that agree"
from "one arm measured twice" is to compare the deals. They are the same arm:
594 of 600 pairings identical. Without that count the frontier would still say
D1 halved 1.4's self-play loss, which was a seed-block effect I had credited to
the shape correction.

A verdict table cannot show this. Two arms can differ in every game and land on
the same mean, or agree in every game and look like independent evidence. The
overlap is a separate fact about an arm and it belongs in a results file, not in
a paragraph I typed from a one-off comparison -- which is exactly the provenance
this project's guards exist to require.

    py scripts4/arm_overlap.py results/p51_depth_profile.json \\
        [results/p51_control_gamma_team_14.json]

Compares every pair of arms across the files given, on the deals they share.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.resultfile import write                              # noqa: E402

#: the per-population margins a pairing records; an arm that changed neither is
#: indistinguishable from the other arm ON THAT DEAL, which is the claim
FIELDS = ("sestina_cand", "self")


def load(paths: list[str]) -> dict:
    arms: dict = {}
    for p in paths:
        d = json.loads(Path(p).read_text())
        for name, rows in d.get("per_pair", {}).items():
            if name in arms:
                raise SystemExit(f"arm {name!r} appears in two files")
            arms[name] = {(r["deal"], r["kv_even"]): r for r in rows}
    return arms


def compare(a: dict, b: dict) -> dict:
    shared = sorted(set(a) & set(b))
    same = 0
    for k in shared:
        if all(a[k][f]["margin"] == b[k][f]["margin"] for f in FIELDS):
            same += 1
    return {"shared": len(shared), "identical": same,
            "differ": len(shared) - same,
            "identical_share": (same / len(shared)) if shared else float("nan")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "results" / "arm_overlap.json"))
    a = ap.parse_args(argv)

    arms = load(a.files)
    if len(arms) < 2:
        print("need at least two arms to compare", file=sys.stderr)
        return 2
    out = {"script": "scripts4/arm_overlap.py", "descriptive": True,
           "sources": a.files, "arms": sorted(arms),
           "fields_compared": FIELDS, "pairs": {}}
    print(f"  {len(arms)} arms: {', '.join(sorted(arms))}")
    print("=" * 72)
    print(f"  {'pair':<44}{'shared':>7}{'identical':>10}{'differ':>8}")
    for x, y in combinations(sorted(arms), 2):
        r = compare(arms[x], arms[y])
        out["pairs"][f"{x} vs {y}"] = r
        print(f"  {x + '  vs  ' + y:<44}{r['shared']:>7,}"
              f"{r['identical']:>10,}{r['differ']:>8,}")
    print("=" * 72)
    print("  Two arms identical on nearly every deal are ONE arm, and their")
    print("  agreement is not independent evidence about anything.")
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\n  wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
