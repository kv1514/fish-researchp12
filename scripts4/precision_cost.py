"""What does posterior precision cost, in milliseconds per decision?

``jobs/PREREGISTRATION_precision.md`` commits in advance to separating two
questions: whether more sampling makes the engine stronger, and whether the
engine should therefore pay for it. The first is settled by the duel blocks.
This script answers the second half of the second, by timing the thing that
actually gets slower.

WHAT IS TIMED
-------------
One full ``FishBot4.act`` on a real position: posterior construction, the SIS
batch, the feature matrix and the score. Not the sampler in isolation -- the
sampler is only part of a decision, and a 3x sampler on a decision that is half
sampler is a 2x decision. The ratio this prints is the ratio the web table and
the match harness would actually feel.

The positions come from ``ask_regret.harvest`` with ``min_resolved=0``, so they
are spread across the whole deal rather than concentrated in the cheap endgame.
Each configuration sees the SAME positions in the same order: the comparison is
paired, like everything else here.

Usage: python scripts4/precision_cost.py [n_positions] [reps]
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.observation import Observation                       # noqa: E402
from fish4.registry4 import make_agent                         # noqa: E402

from ask_regret import GAMMA, harvest                          # noqa: E402

DRAWS = (160, 480)


def time_config(positions, n_draws: int, reps: int) -> list[float]:
    """Milliseconds for one ``act`` at each position, best of ``reps``."""
    out = []
    for i, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        best = float("inf")
        for _ in range(reps):
            agent = make_agent(("fishbot4", {"opponent_gamma": GAMMA,
                                             "n_draws": n_draws}))
            agent.begin_game(seat, rules, 4242 + i)
            t0 = time.perf_counter()
            agent.act(obs)
            best = min(best, (time.perf_counter() - t0) * 1000.0)
        out.append(best)
    return out


def main(argv):
    n_pos = int(argv[0]) if argv else 60
    reps = int(argv[1]) if len(argv) > 1 else 3

    print("what does posterior precision cost per decision?")
    print(f"{n_pos} positions across the whole deal | best of {reps}\n")
    positions = harvest(60, 0, n_pos)
    print(f"harvested {len(positions)} positions\n")

    per = {}
    for d in DRAWS:
        t0 = time.time()
        per[d] = time_config(positions, d, reps)
        print(f"  n_draws {d:>4}   mean {np.mean(per[d]):7.1f} ms   "
              f"median {np.median(per[d]):7.1f} ms   "
              f"p90 {np.percentile(per[d], 90):7.1f} ms   "
              f"[{time.time() - t0:.0f}s]")

    a, b = np.array(per[DRAWS[0]]), np.array(per[DRAWS[1]])
    ratio = b / a
    print(f"\nper-decision ratio  mean {ratio.mean():.2f}x   "
          f"median {np.median(ratio):.2f}x")
    print(f"paired difference   {(b - a).mean():+.1f} ms "
          f"+/- {(b - a).std(ddof=1) / np.sqrt(a.size):.1f}")
    print(f"\nthe sampling budget itself is {DRAWS[1] / DRAWS[0]:.1f}x; a "
          f"decision is not all sampler,\nso the decision ratio is the smaller "
          f"number and it is the one that matters.")

    out = {
        "host": f"{platform.system()} {platform.machine()}",
        "n_decisions": len(positions), "reps": reps,
        "per_decision_ms": {str(d): float(np.mean(per[d])) for d in DRAWS},
        "median_ms": {str(d): float(np.median(per[d])) for d in DRAWS},
        "p90_ms": {str(d): float(np.percentile(per[d], 90)) for d in DRAWS},
        "ratio_mean": float(ratio.mean()),
        "ratio_median": float(np.median(ratio)),
        "samples": {str(d): per[d] for d in DRAWS},
    }
    dest = ROOT / "results" / "precision_cost.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
