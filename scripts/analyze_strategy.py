"""Run strategy analytics over homogeneous tables of a given agent.

Usage: py scripts/analyze_strategy.py [agent] [n_games]
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.analysis import collect_games, run_all
from fish.rules import RuleConfig


def main(agent: str = "memory", n_games: int = 300):
    specs = [(agent, {})] * 6
    rules = RuleConfig()
    t0 = time.time()
    records = collect_games(specs, rules, n_games, base_seed=50_000, n_jobs=8)
    stats = run_all(records)
    stats["agent"] = agent
    stats["wall_seconds"] = time.time() - t0
    out = ROOT / "results" / f"strategy_{agent}_{n_games}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "memory",
         int(sys.argv[2]) if len(sys.argv) > 2 else 300)
