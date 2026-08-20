"""Ablation duels: one variable changed, paired deals, everything else fixed.

Each suite answers a specific strategy question from STRATEGY_BOOK.md.

Usage: py scripts/run_ablations.py [suite] [n_deals]
Suites: claim_threshold, ev_claim, samples, suit_bonus, all
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.eval.tournament import play_matchup

SUITES = {
    # "At what probability does risking a distributed claim become +EV?"
    # Baseline 0.97 was picked by intuition; the EV model derives ~0.70.
    "claim_threshold": [
        (("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.60})),
        (("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.70})),
        (("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.85})),
        (("probabilistic", {"claim_threshold": 0.97}),
         ("probabilistic", {"claim_threshold": 0.999})),
    ],
    # Decision-theoretic claiming vs a fixed threshold, everything else equal.
    "ev_claim": [
        (("probabilistic", {}), ("ev_claim", {})),
        (("probabilistic", {"claim_threshold": 0.70}), ("ev_claim", {})),
    ],
    # How much does belief precision buy?
    "samples": [
        (("probabilistic", {"n_samples": 32}),
         ("probabilistic", {"n_samples": 8})),
        (("probabilistic", {"n_samples": 32}),
         ("probabilistic", {"n_samples": 96})),
    ],
    # Greedy P(success) vs weighting suit progress.
    "suit_bonus": [
        (("probabilistic", {"suit_bonus": 0.06}),
         ("probabilistic", {"suit_bonus": 0.0})),
        (("probabilistic", {"suit_bonus": 0.06}),
         ("probabilistic", {"suit_bonus": 0.25})),
    ],
}


def main(suite: str = "all", n_deals: int = 120):
    suites = SUITES if suite == "all" else {suite: SUITES[suite]}
    out = {}
    for name, duels in suites.items():
        out[name] = []
        for i, (sx, sy) in enumerate(duels):
            t0 = time.time()
            stats = play_matchup(sx, sy, n_deals=n_deals, n_jobs=8,
                                 base_seed=90_000 + 1000 * i,
                                 agent_seed_base=31 + i)
            rec = stats.to_dict()
            rec["label_x"] = f"{sx[0]}{sx[1]}"
            rec["label_y"] = f"{sy[0]}{sy[1]}"
            lo, hi = stats.wilson_ci()
            m, mlo, mhi = stats.diff_mean_ci()
            verdict = ("X better" if lo > 0.5 else
                       "Y better" if hi < 0.5 else "no difference")
            rec["verdict"] = verdict
            out[name].append(rec)
            print(f"[{time.time()-t0:6.1f}s] {rec['label_x']} vs "
                  f"{rec['label_y']}: {stats.pair_score():.3f} "
                  f"[{lo:.3f},{hi:.3f}] diff {m:+.2f} [{mlo:+.2f},{mhi:+.2f}]"
                  f"  -> {verdict}", flush=True)
    path = ROOT / "results" / f"ablations_{suite}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"Saved {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all",
         int(sys.argv[2]) if len(sys.argv) > 2 else 120)
