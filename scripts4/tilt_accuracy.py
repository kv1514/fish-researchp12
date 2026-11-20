"""Does the twisted proposal estimate the same posterior, only better?

A rise in Kish ESS is not on its own evidence of a better estimator. Effective
sample size measures how *flat* the importance weights are, and a proposal that
covers the target badly can have perfectly flat weights over the part it does
cover. So the twist has to be checked against the quantity it claims to
estimate.

Method. On real harvested positions, build a high-precision reference by drawing
a very large untilted batch -- the incumbent sampler is already validated
against exhaustive enumeration, so at large n it is the ground truth. Then draw
small batches at each tilt strength and measure L1 error per card against the
reference. A twist that is merely flattening weights will show a *worse* L1 at
matched budget despite the better ESS; a twist that is genuinely reducing
variance will show a better one.

The reference is untilted deliberately. Using a tilted reference would compare
each setting against itself.

Usage: python scripts4/tilt_accuracy.py [n_positions] [n_draws] [ref_draws] [tilts...]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.observation import Observation
from fish4.posterior import Posterior

from tests4.test_leakage4 import collect_positions

GAMMA = 0.35


def _marginals(rules, hands, sw, turn, hist, seat, n_draws, tilt, seed):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(seed), n_draws=n_draws,
                     obs=obs, gamma=GAMMA, sis_tilt=tilt)
    return np.asarray(post.marginals(), dtype=np.float64)


def main(argv):
    n_pos = int(argv[0]) if argv else 12
    n_draws = int(argv[1]) if len(argv) > 1 else 160
    ref_draws = int(argv[2]) if len(argv) > 2 else 20000
    tilts = [float(t) for t in argv[3:]] or [0.0, 1.0]

    positions = collect_positions(6, 3, n_pos)
    print(f"{len(positions)} positions | n_draws={n_draws} "
          f"ref={ref_draws} untilted\n")

    err = {t: [] for t in tilts}
    for pi, pos in enumerate(positions):
        ref = _marginals(*pos, ref_draws, 0.0, 900000 + pi)
        for t in tilts:
            # several independent small batches per position, so the error is
            # averaged over sampler noise rather than over one lucky seed
            for rep in range(5):
                M = _marginals(*pos, n_draws, t, 5000 + 137 * rep + pi)
                err[t].append(float(np.abs(M - ref).sum() / M.shape[0]))

    out = []
    for t in tilts:
        e = np.asarray(err[t])
        rec = {"tilt": t, "n_draws": n_draws, "ref_draws": ref_draws,
               "positions": len(positions), "samples": int(e.size),
               "mean_l1": float(e.mean()),
               "se": float(e.std(ddof=1) / np.sqrt(e.size)),
               "median_l1": float(np.median(e)),
               "p90_l1": float(np.percentile(e, 90))}
        out.append(rec)
        print(f"tilt={t:<5} mean L1/card = {rec['mean_l1']:.5f} "
              f"+/- {rec['se']:.5f}   median {rec['median_l1']:.5f}   "
              f"p90 {rec['p90_l1']:.5f}")

    if len(out) >= 2:
        a, b = out[0], out[-1]
        d = a["mean_l1"] - b["mean_l1"]
        se = (a["se"] ** 2 + b["se"] ** 2) ** 0.5
        print(f"\ntilt {b['tilt']} vs {a['tilt']}: "
              f"L1 lower by {d:+.5f} +/- {se:.5f} "
              f"({100 * d / a['mean_l1']:+.1f}%)")

    dest = ROOT / "results" / "tilt_accuracy.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
