"""Tune search against EXACT ground truth instead of against other agents.

Why this is the right instrument: agreement-with-optimal is absolute, needs
no opponent, and the expensive part (solving positions) is paid once and
reused across every configuration. A paired matchup costs minutes per cell
and only tells us "better than this other bot"; this tells us "closer to
right".

Hypothesis under test: paired search degrades its own prior (73.6% vs 75.6%
agreement) because its override rule suffers from MULTIPLE COMPARISONS. It
tests every candidate against the baseline at t > 1.5 independently, so with
5-6 candidates the chance that at least one clears the bar by luck is
substantial. If that is the cause, agreement should rise monotonically with
a stricter threshold and approach the prior's from below.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.benchmark_exact import (benchmark_agent, collect_solvable_positions,
                                  solve_positions)

MODEL = str(ROOT / "checkpoints" / "pi_value_v1.pt")


def main(n_games: int = 200, seed: int = 3):
    t0 = time.time()
    pos = collect_solvable_positions(n_games=n_games, seed=seed,
                                     max_live_cards=7)
    solved = solve_positions(pos)
    res = sum(1 for p in solved if p["resolved"])
    print(f"{len(solved)} positions ({res} information-resolved) "
          f"prepared in {time.time()-t0:.0f}s\n", flush=True)

    configs = [
        ("prior (no search)", "probabilistic", {}),
        ("paired t=1.0", "paired_search", {"n_worlds": 12, "t_threshold": 1.0}),
        ("paired t=1.5", "paired_search", {"n_worlds": 12, "t_threshold": 1.5}),
        ("paired t=2.5", "paired_search", {"n_worlds": 12, "t_threshold": 2.5}),
        ("paired t=4.0", "paired_search", {"n_worlds": 12, "t_threshold": 4.0}),
        ("paired t=8.0", "paired_search", {"n_worlds": 12, "t_threshold": 8.0}),
        ("paired w=24 t=2.5", "paired_search",
         {"n_worlds": 24, "t_threshold": 2.5}),
        ("value t=1.0", "value_search",
         {"model_path": MODEL, "n_worlds": 16, "t_threshold": 1.0}),
        ("value t=2.5", "value_search",
         {"model_path": MODEL, "n_worlds": 16, "t_threshold": 2.5}),
        ("value t=4.0", "value_search",
         {"model_path": MODEL, "n_worlds": 16, "t_threshold": 4.0}),
    ]
    rows = []
    for label, agent, kw in configs:
        t = time.time()
        r = benchmark_agent(agent, solved, kw, seed=7)
        d = r.to_dict()
        d["label"] = label
        d["kwargs"] = {k: v for k, v in kw.items() if k != "model_path"}
        rows.append(d)
        print(f"  {label:20s} resolved {r.resolved_rate:6.1%} "
              f"uncertain {r.unresolved_rate:6.1%} "
              f"loss {r.mean_value_loss:.3f}  [{time.time()-t:.0f}s]",
              flush=True)
    out = ROOT / "results" / "search_param_sweep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
