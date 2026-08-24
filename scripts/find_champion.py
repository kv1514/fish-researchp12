"""Search for a new champion policy from the terms that individually won.

Two ask-scoring terms beat the baseline on their own at 600 duplicate
deal-pairs each: turn-risk (penalize handing the turn to a card-rich
opponent when the ask fails) and scarcity (prefer contested half-suits our
team is already winning). This script asks the two questions that matter
next:

  1. Where does each term peak? Both improved as the weight grew, so the
     tested range may simply have been too narrow.
  2. Do they COMBINE? Two individually good terms can easily be redundant,
     both pushing toward the same asks, in which case the pair is worth no
     more than the better one alone.

Every candidate is measured against the SAME baseline over duplicate deals,
so the numbers are directly comparable.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.eval.tournament import play_matchup
from fish.registry import Experiment, record

BASE = ("probabilistic", {})

CANDIDATES = [
    ("turn 0.6",              {"w_turn": 0.6}),
    ("turn 1.0",              {"w_turn": 1.0}),
    ("turn 1.6",              {"w_turn": 1.6}),
    ("scarce 0.2",            {"w_scarce": 0.2}),
    ("scarce 0.4",            {"w_scarce": 0.4}),
    ("scarce 0.8",            {"w_scarce": 0.8}),
    ("turn 0.6 + scarce 0.2", {"w_turn": 0.6, "w_scarce": 0.2}),
    ("turn 1.0 + scarce 0.4", {"w_turn": 1.0, "w_scarce": 0.4}),
    ("turn 1.6 + scarce 0.4", {"w_turn": 1.6, "w_scarce": 0.4}),
    ("turn 1.0 + scarce 0.4 + reveal 0.15",
     {"w_turn": 1.0, "w_scarce": 0.4, "w_reveal": 0.15}),
    # Belief precision was itself a strong lever and had NOT saturated at
    # 32 samples (96 still beat 32 by +0.54 sets/pair), so the best policy
    # is probably "better terms AND sharper beliefs" rather than either.
    ("samples 96", {"n_samples": 96}),
    ("turn 1.0 + scarce 0.4 + samples 96",
     {"w_turn": 1.0, "w_scarce": 0.4, "n_samples": 96}),
]


def main(n_deals: int = 600, n_jobs: int = 8):
    rows = []
    t0 = time.time()
    for i, (label, kw) in enumerate(CANDIDATES):
        t = time.time()
        stats = play_matchup(BASE, ("tuned", kw), n_deals=n_deals,
                             n_jobs=n_jobs, base_seed=770_000 + 7_000 * i,
                             agent_seed_base=8080 + i)
        m, lo, hi = stats.diff_mean_ci()
        # baseline is X, so a NEGATIVE differential means the candidate won
        gain, glo, ghi = -m, -hi, -lo
        verdict = ("candidate stronger" if glo > 0 else
                   "baseline stronger" if ghi < 0 else "no difference")
        rows.append({"label": label, "kwargs": kw, "n_pairs": stats.n_pairs,
                     "gain": gain, "gain_ci": [glo, ghi], "verdict": verdict,
                     "pair_score": 1 - stats.pair_score()})
        print(f"[{time.time()-t:6.0f}s] {label:38s} gain {gain:+.3f} "
              f"[{glo:+.3f},{ghi:+.3f}]  {verdict}", flush=True)
        record(Experiment(
            name=f"champion:{label}", kind="ablation",
            config={"baseline": BASE, "candidate": ["tuned", kw],
                    "n_deals": n_deals, "base_seed": 770_000 + 7_000 * i,
                    "agent_seed_base": 8080 + i},
            result={"gain_sets_per_pair": gain, "gain_ci": [glo, ghi],
                    "n_pairs": stats.n_pairs},
            evidence_tier="DEMONSTRATED" if stats.n_pairs >= 400 else "PROMISING",
            notes=verdict))
    rows.sort(key=lambda r: -r["gain"])
    print("\n=== ranked ===")
    for r in rows:
        print(f"  {r['label']:38s} {r['gain']:+.3f} "
              f"[{r['gain_ci'][0]:+.3f},{r['gain_ci'][1]:+.3f}]")
    path = ROOT / "results" / "champion_search.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))
    print(f"\nSaved {path}  ({time.time()-t0:.0f}s total)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 600)
