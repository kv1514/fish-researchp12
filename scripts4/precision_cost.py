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

The positions come from ``ask_regret.harvest`` with ``min_resolved=0``, drawn
from many games so the sample is not one deal's endgame. Each configuration
sees the SAME positions in the same order: the comparison is paired, like
everything else here.

FIXED AND MARGINAL
------------------
Four budgets are timed, not two, because the useful engineering fact is not the
ratio at one operating point. A decision costs a fixed amount plus a per-draw
amount, and the two behave differently: the fixed part is what makes tripling
the sampler cost far less than three times, and it is also what would make a
tenfold increase cost nearly ten. The fit is printed with its residuals so the
linear model can be checked rather than assumed.

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

#: The two the pre-registered duel compared, plus a low and a high anchor so the
#: fixed and marginal parts of a decision can be separated.
DRAWS = (40, 160, 480, 1920)
#: The two the duel actually compared; the ratio the engine would feel.
BASE, BOUGHT = 160, 480


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
    print(f"{n_pos} positions | best of {reps}\n")
    # Many games, so the sample is not one deal's opening. harvest() returns as
    # soon as it has enough, so the game budget has to exceed the position count
    # for the positions to come from more than a handful of deals.
    positions = harvest(max(60, n_pos * 3), 0, n_pos)
    hl = [len(h) for (_, _, _, _, h, _) in positions]
    print(f"harvested {len(positions)} positions   "
          f"history length {min(hl)}-{max(hl)}, median "
          f"{int(np.median(hl))}\n")

    per = {}
    for d in DRAWS:
        t0 = time.time()
        per[d] = time_config(positions, d, reps)
        print(f"  n_draws {d:>4}   mean {np.mean(per[d]):7.1f} ms   "
              f"median {np.median(per[d]):7.1f} ms   "
              f"p90 {np.percentile(per[d], 90):7.1f} ms   "
              f"[{time.time() - t0:.0f}s]")

    a, b = np.array(per[BASE]), np.array(per[BOUGHT])
    ratio = b / a
    print(f"\nthe comparison the duel ran, {BASE} -> {BOUGHT} draws")
    print(f"  per-decision ratio  mean {ratio.mean():.2f}x   "
          f"median {np.median(ratio):.2f}x")
    print(f"  paired difference   {(b - a).mean():+.2f} ms "
          f"+/- {(b - a).std(ddof=1) / np.sqrt(a.size):.2f}")

    # fixed + marginal, by least squares on the four budgets
    xs = np.array(DRAWS, dtype=float)
    ys = np.array([np.mean(per[d]) for d in DRAWS])
    A = np.column_stack([np.ones(xs.size), xs])
    (fixed, marg), *_ = np.linalg.lstsq(A, ys, rcond=None)
    pred = A @ np.array([fixed, marg])
    print(f"\ncost of a decision = {fixed:.2f} ms + {marg * 1000:.2f} us "
          f"per draw")
    for d, y, q in zip(DRAWS, ys, pred):
        print(f"  n_draws {d:>5}   measured {y:6.2f}   fitted {q:6.2f}   "
              f"residual {y - q:+.2f}")
    share = marg * BASE / ys[list(DRAWS).index(BASE)]
    print(f"\nAt the shipped {BASE} draws the sampler is {100 * share:.0f}% of "
          f"a decision, so\ntripling it costs "
          f"{ratio.mean():.2f}x rather than "
          f"{BOUGHT / BASE:.0f}x. That headroom is finite: the\nfixed "
          f"{fixed:.1f} ms stops mattering once the sampler is large enough, "
          f"and by\n{DRAWS[-1]} draws the decision is already "
          f"{np.mean(per[DRAWS[-1]]) / ys[list(DRAWS).index(BASE)]:.1f}x the "
          f"shipped one.")

    out = {
        "host": f"{platform.system()} {platform.machine()}",
        "n_decisions": len(positions), "reps": reps,
        "per_decision_ms": {str(d): float(np.mean(per[d])) for d in DRAWS},
        "fixed_ms": float(fixed), "marginal_us_per_draw": float(marg * 1000),
        "base_draws": BASE, "bought_draws": BOUGHT,
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
