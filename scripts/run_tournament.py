"""Round-robin tournament with paired-deal evaluation and BT ratings.

Usage:
  py scripts/run_tournament.py quick
  py scripts/run_tournament.py baseline
  py scripts/run_tournament.py search
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.eval.elo import fit_ratings, format_table
from fish.eval.tournament import play_matchup
from fish.rules import RuleConfig

MODEL = str(ROOT / "checkpoints" / "pi_value_v1.pt")

PRESETS = {
    "quick": {
        "specs": [("random", {}), ("heuristic", {}), ("memory", {})],
        "deals": {"default": 30}, "jobs": 8,
    },
    "baseline": {
        "specs": [("random", {}), ("heuristic", {}), ("memory", {}),
                  ("probabilistic", {})],
        "deals": {"default": 400, "probabilistic": 120}, "jobs": 8,
    },
    "search": {
        "specs": [("probabilistic", {}),
                  ("paired_search", {"n_worlds": 12, "n_candidates": 5}),
                  ("value_search", {"model_path": MODEL, "n_worlds": 16,
                                    "n_candidates": 6})],
        "deals": {"default": 40}, "jobs": 8,
    },
}


def main(preset_name: str, out_name: str | None = None):
    preset = PRESETS[preset_name]
    specs = preset["specs"]
    rules = RuleConfig()
    all_stats, bt_rows = [], []
    t_start = time.time()
    for i in range(len(specs)):
        for j in range(i + 1, len(specs)):
            sx, sy = specs[i], specs[j]
            n = min(preset["deals"].get(sx[0], preset["deals"]["default"]),
                    preset["deals"].get(sy[0], preset["deals"]["default"]))
            t0 = time.time()
            stats = play_matchup(sx, sy, n_deals=n, rules=rules,
                                 base_seed=1000 * i + j, n_jobs=preset["jobs"],
                                 agent_seed_base=77 + i * 10 + j)
            print(f"[{time.time()-t0:7.1f}s] {stats.summary()}", flush=True)
            all_stats.append(stats)
            bt_rows.append((sx[0], sy[0], stats.pair_score(), stats.n_pairs))
    anchor = "random" if any(s[0] == "random" for s in specs) else specs[0][0]
    ratings = fit_ratings(bt_rows, anchor=anchor)
    print("\nRatings (Bradley-Terry MAP, anchor=200):")
    print(format_table(ratings))
    out = {
        "preset": preset_name, "rules": rules.to_dict(),
        "matchups": [s.to_dict() for s in all_stats],
        "ratings": ratings, "wall_seconds": time.time() - t_start,
    }
    path = ROOT / "results" / f"tournament_{out_name or preset_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "quick",
         sys.argv[2] if len(sys.argv) > 2 else None)
