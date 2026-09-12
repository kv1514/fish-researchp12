"""How much of the sampler's nominal precision actually survives reweighting?

The posterior is drawn by sequential importance sampling and self-normalised.
Self-normalisation is consistent, not free: if the proposal is a poor match for
the target, a few draws carry most of the weight and the batch behaves like far
fewer than ``n_draws`` independent worlds. Kish's effective sample size measures
that directly, and the sampler already computes it -- it has simply never been
reported.

This matters more at v0.4 than the numbers suggest. An opponent model changes
the target, so any ``opponent_gamma > 0`` forces the sampling path at *every*
decision; the exact DP is never reached. Since the paper's sharpest finding is
that P(success) is the objective and the rest are tie-breaks, the precision of
the marginal that P(success) is read from is the precision of the whole policy.

Usage:  python scripts4/ess_probe.py [n_deals] [n_draws] [gamma ...]
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

from fish.cards import deck_size
from fish.rules import RuleConfig
from fish4.match import play_capped
from fish4.registry4 import make_agent


def probe(n_deals: int, gamma: float, n_draws: int, seed0: int = 77000,
          tilt: float = 0.0):
    rules = RuleConfig()
    per_decision = []
    spec = {"opponent_gamma": gamma, "n_draws": n_draws,
            "sis_tilt": tilt}
    for d in range(n_deals):
        agents = [make_agent(("fishbot4", spec)) for _ in range(6)]
        deck = list(range(deck_size(rules.variant)))
        random.Random(seed0 + d).shuffle(deck)
        play_capped(agents, rules, deck, agent_seed=4242 + d)
        for a in agents:
            st = getattr(a, "stats", None)
            if st is None or not st.sis_decisions:
                continue
            per_decision.append((st.ess_sum / st.sis_decisions,
                                 st.sis_decisions, st.exact_decisions))
    if not per_decision:
        return None
    ess = np.array([p[0] for p in per_decision])
    sis = sum(p[1] for p in per_decision)
    exact = sum(p[2] for p in per_decision)
    return {
        "gamma": gamma, "n_draws": n_draws, "deals": n_deals,
        "sis_tilt": tilt,
        "seats": len(per_decision),
        "sis_decisions": sis, "exact_decisions": exact,
        "mean_ess": float(ess.mean()),
        "p10_ess": float(np.percentile(ess, 10)),
        "median_ess": float(np.median(ess)),
        "p90_ess": float(np.percentile(ess, 90)),
        "efficiency": float(ess.mean() / n_draws),
    }


def main(argv):
    n_deals = int(argv[0]) if argv else 8
    n_draws = int(argv[1]) if len(argv) > 1 else 160
    tilts = [float(g) for g in argv[2:]] or [0.0]
    out = []
    for t in tilts:
        r = probe(n_deals, 0.35, n_draws, tilt=t)
        if r is None:
            print(f"tilt={t}: no SIS decisions (exact path throughout)")
            continue
        out.append(r)
        print(f"tilt={r['sis_tilt']:<5} gamma={r['gamma']:<5} draws={r['n_draws']:<4} "
              f"ESS mean={r['mean_ess']:7.1f} "
              f"(p10 {r['p10_ess']:6.1f}  med {r['median_ess']:6.1f}  "
              f"p90 {r['p90_ess']:6.1f})  "
              f"efficiency={r['efficiency']:.3f}  "
              f"sis/exact={r['sis_decisions']}/{r['exact_decisions']}")
    dest = ROOT / "results" / "ess_probe.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
