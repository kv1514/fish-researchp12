"""Large-scale Monte Carlo study: the paper's experimental backbone.

Every cell is a paired-deal duel (same cards, same agent randomness, teams
swapped) at a sample size chosen so the confidence interval can actually
separate the effects we care about. With a per-pair set-differential
standard deviation around 3, n=1000 pairs gives a standard error near 0.1
sets, enough to resolve effects of about a quarter of a set.

Usage:
  py scripts/run_large_study.py ladder 1000
  py scripts/run_large_study.py strategy 1000
  py scripts/run_large_study.py all 1000
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.eval.tournament import play_matchup
from fish.registry import Experiment, record
from fish.rules import RuleConfig

MODEL = str(ROOT / "checkpoints" / "pi_value_v1.pt")

STUDIES = {
    # The strength ladder, at a sample size that pins the measured gaps.
    "ladder": [
        ("random vs heuristic", ("random", {}), ("heuristic", {})),
        ("heuristic vs memory", ("heuristic", {}), ("memory", {})),
        ("memory vs probabilistic", ("memory", {}), ("probabilistic", {})),
    ],
    # Strategy questions, each isolating ONE mechanism.
    "strategy": [
        ("turn-risk w=0.15", ("probabilistic", {}), ("tuned", {"w_turn": 0.15})),
        ("turn-risk w=0.30", ("probabilistic", {}), ("tuned", {"w_turn": 0.30})),
        ("turn-risk w=0.60", ("probabilistic", {}), ("tuned", {"w_turn": 0.60})),
        ("reveal-cost w=0.05", ("probabilistic", {}), ("tuned", {"w_reveal": 0.05})),
        ("reveal-cost w=0.15", ("probabilistic", {}), ("tuned", {"w_reveal": 0.15})),
        ("deplete w=0.15", ("probabilistic", {}), ("tuned", {"w_deplete": 0.15})),
        ("scarcity w=0.20", ("probabilistic", {}), ("tuned", {"w_scarce": 0.20})),
        ("claim 0.97 vs 0.70", ("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.70})),
        ("claim 0.97 vs 0.90", ("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.90})),
        ("belief samples 32 vs 8", ("probabilistic", {"n_samples": 32}),
         ("probabilistic", {"n_samples": 8})),
        ("belief samples 32 vs 96", ("probabilistic", {"n_samples": 32}),
         ("probabilistic", {"n_samples": 96})),
        ("tablebase on vs off", ("probabilistic", {"use_tablebase": True}),
         ("probabilistic", {"use_tablebase": False})),
    ],
    # Does any search variant beat its own prior?
    "search": [
        ("prior vs paired-search", ("probabilistic", {}),
         ("paired_search", {"n_worlds": 12, "t_threshold": 1.5})),
        ("prior vs paired-search strict", ("probabilistic", {}),
         ("paired_search", {"n_worlds": 12, "t_threshold": 4.0})),
        ("prior vs value-search", ("probabilistic", {}),
         ("value_search", {"model_path": MODEL, "n_worlds": 16})),
    ],
}

# Search agents are far slower per decision, so they get fewer pairs.
SLOW = {"paired_search", "value_search", "search", "ismcts"}


def main(study: str = "all", n_deals: int = 1000, n_jobs: int = 8):
    names = list(STUDIES) if study == "all" else [study]
    out = {}
    grand_t0 = time.time()
    for name in names:
        out[name] = []
        for i, (label, sx, sy) in enumerate(STUDIES[name]):
            n = n_deals
            if sx[0] in SLOW or sy[0] in SLOW:
                n = max(60, n_deals // 12)
            t0 = time.time()
            stats = play_matchup(sx, sy, n_deals=n, rules=RuleConfig(),
                                 base_seed=500_000 + 10_000 * i,
                                 n_jobs=n_jobs,
                                 agent_seed_base=4242 + i)
            lo, hi = stats.wilson_ci()
            m, mlo, mhi = stats.diff_mean_ci()
            verdict = ("X stronger" if mlo > 0 else
                       "Y stronger" if mhi < 0 else "no difference")
            rec = stats.to_dict()
            rec.update({"label": label, "study": name, "verdict": verdict,
                        "x": f"{sx[0]}{sx[1]}", "y": f"{sy[0]}{sy[1]}"})
            out[name].append(rec)
            print(f"[{time.time()-t0:6.0f}s] {label:28s} n={n:5d}  "
                  f"score {stats.pair_score():.3f} [{lo:.3f},{hi:.3f}]  "
                  f"diff {m:+.3f} [{mlo:+.3f},{mhi:+.3f}]  -> {verdict}",
                  flush=True)
            record(Experiment(
                name=f"{name}:{label}", kind="ablation",
                config={"x": sx, "y": sy, "n_deals": n,
                        "base_seed": 500_000 + 10_000 * i,
                        "agent_seed_base": 4242 + i},
                result={"pair_score": stats.pair_score(),
                        "wilson_ci": [lo, hi], "set_diff": m,
                        "set_diff_ci": [mlo, mhi], "n_pairs": stats.n_pairs},
                evidence_tier="DEMONSTRATED" if stats.n_pairs >= 400
                else "PROMISING",
                notes=verdict))
    path = ROOT / "results" / f"large_study_{study}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    total_games = sum(r["n_pairs"] * 2 for v in out.values() for r in v)
    print(f"\n{total_games} games in {time.time()-grand_t0:.0f}s")
    print(f"Saved {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all",
         int(sys.argv[2]) if len(sys.argv) > 2 else 1000)
