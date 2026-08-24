"""Head-to-head between two champion candidates.

The league promotion rule requires beating the INCUMBENT convincingly, not
merely beating a common baseline by a larger margin. Two candidates measured
against the same baseline can have overlapping intervals, which says nothing
about how they fare against each other, so this runs them directly.

Usage: py scripts/head2head.py [n_deals] [n_jobs]
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.eval.tournament import play_matchup
from fish.registry import Experiment, record

V1 = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
V2 = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2, "n_samples": 96})


def main(n_deals: int = 400, n_jobs: int = 4):
    t = time.time()
    s = play_matchup(V1, V2, n_deals=n_deals, n_jobs=n_jobs,
                     base_seed=1234567, agent_seed_base=31337)
    m, lo, hi = s.diff_mean_ci()
    wl, wh = s.wilson_ci()
    gain, glo, ghi = -m, -hi, -lo          # V1 is X, so negate for V2's gain
    verdict = ("v2 stronger" if glo > 0 else
               "v1 stronger" if ghi < 0 else "no difference")
    res = {"v2_gain": gain, "v2_gain_ci": [glo, ghi],
           "v2_pair_score": 1 - s.pair_score(), "v2_ci": [1 - wh, 1 - wl],
           "n_pairs": s.n_pairs, "verdict": verdict,
           "seconds": time.time() - t}
    print(f"[{res['seconds']:.0f}s] v2 gain over v1: {gain:+.3f} "
          f"[{glo:+.3f},{ghi:+.3f}]  v2 pair-score "
          f"{res['v2_pair_score']:.3f} -> {verdict}", flush=True)
    record(Experiment(
        name="head2head:tuned-v1 vs tuned-v2", kind="ablation",
        config={"v1": V1, "v2": V2, "n_deals": n_deals,
                "base_seed": 1234567, "agent_seed_base": 31337},
        result=res,
        evidence_tier="DEMONSTRATED" if s.n_pairs >= 400 else "PROMISING",
        notes=verdict))
    out = ROOT / "results" / "head2head_v1_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 400,
         int(sys.argv[2]) if len(sys.argv) > 2 else 4)
