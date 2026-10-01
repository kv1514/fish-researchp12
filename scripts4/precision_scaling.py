"""How fast does the posterior's error fall with the sampling budget?

Two of this project's decisions hang on the answer and neither has been measured
at v0.4. v0.3 found belief precision unsaturated -- 32 to 96 samples was worth
+0.54 sets per deal-pair -- but that was a *biased* sampler with a different
estimator, so it does not transfer. And any work on the sampler (a better
proposal, resampling, a smarter target) is only worth doing if the error it
reduces is an error the policy can feel.

So: L1 error per card against a high-precision reference, as a function of
``n_draws``. If the curve is already flat at the operating point of 160, the
whole inference axis is closed and effort belongs elsewhere. If it is still
falling as 1/sqrt(n), the size of the available prize can be read straight off
it.

Usage: python scripts4/precision_scaling.py [n_positions] [ref_draws] [n...]
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
REPS = 6


def _marginals(rules, hands, sw, turn, hist, seat, n_draws, seed):
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(seed), n_draws=n_draws,
                     obs=obs, gamma=GAMMA)
    return np.asarray(post.marginals(), dtype=np.float64)


def main(argv):
    n_pos = int(argv[0]) if argv else 10
    ref_draws = int(argv[1]) if len(argv) > 1 else 16000
    budgets = [int(x) for x in argv[2:]] or [40, 80, 160, 320, 640, 1280]

    positions = collect_positions(6, 3, n_pos)
    print(f"{len(positions)} positions | reference {ref_draws} draws | "
          f"gamma={GAMMA}\n")

    err = {n: [] for n in budgets}
    for pi, pos in enumerate(positions):
        ref = _marginals(*pos, ref_draws, 900000 + pi)
        for n in budgets:
            for rep in range(REPS):
                M = _marginals(*pos, n, 5000 + 137 * rep + 7919 * pi)
                err[n].append(float(np.abs(M - ref).sum() / M.shape[0]))

    out = []
    prev = None
    for n in budgets:
        e = np.asarray(err[n])
        rec = {"n_draws": n, "mean_l1": float(e.mean()),
               "se": float(e.std(ddof=1) / np.sqrt(e.size)),
               "samples": int(e.size)}
        # what a 1/sqrt(n) law predicts from the previous row, as a check that
        # the estimator is behaving like Monte Carlo error and not like bias
        pred = "" if prev is None else \
            f"  (1/sqrt(n) predicts {prev[1] * (prev[0] / n) ** 0.5:.5f})"
        out.append(rec)
        print(f"n={n:<6} mean L1/card = {rec['mean_l1']:.5f} "
              f"+/- {rec['se']:.5f}{pred}")
        prev = (n, rec["mean_l1"])

    # A floor that does not fall is bias, not noise. Fit the exponent.
    ns = np.array([r["n_draws"] for r in out], dtype=float)
    ls = np.array([r["mean_l1"] for r in out], dtype=float)
    slope, intercept = np.polyfit(np.log(ns), np.log(ls), 1)
    print(f"\nfitted L1 ~ n^{slope:.3f}   (pure Monte Carlo error is -0.5)")
    dest = ROOT / "results" / "precision_scaling.json"
    dest.write_text(json.dumps(
        {"gamma": GAMMA, "ref_draws": ref_draws, "positions": len(positions),
         "rows": out, "log_slope": float(slope)}, indent=1))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
