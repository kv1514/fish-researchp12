"""How much does the choice model's dropped denominator actually vary?

The likelihood the engine computes is

    P(observed asks | world)  proportional to  product of depth^gamma

and the proportionality hides a denominator. Under a proper choice model a
player picks half-suit H with probability depth_H^alpha divided by the sum over
the half-suits they could legally ask in. The engine drops that sum.

At alpha = 1 dropping it is exact, and that is why alpha = 1 was chosen: the
depths of a hand sum to its size, which is public, so the denominator is the
same number in every hypothesised world and cancels out of a self-normalised
estimate. That argument fails for any other exponent.

It matters now because the measured exponent is not 1. Fitted as a proper
conditional logit -- with the denominator included -- it is 1.207 on initial-deal
depth and 2.195 on depth at the ask. If the engine is to use either, the question
is whether the denominator it drops is close enough to constant across the worlds
it is reweighting for the omission to be harmless.

That is measurable rather than arguable: draw worlds from the posterior at real
positions, compute each asker's denominator in each world, and look at the
spread. A denominator that barely moves is a denominator worth dropping.

Usage: python scripts4/normaliser_variation.py [n_positions] [n_worlds]
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
from fish.cards import NUM_PLAYERS, half_suit_cards, half_suit_of
from fish.engine import AskEvent, ClaimEvent
from fish.observation import Observation
from fish4.posterior import Posterior
from ask_regret import harvest                                   # noqa: E402

GAMMA = 0.35


def denominators(obs, worlds, alpha):
    """Per (asker, world), the sum of depth^alpha over their live half-suits.

    'Live' is the game's own rule for where an ask is legal: the half-suit is
    unresolved and the player holds at least one card of it. Depth is read from
    the sampled world, which is what makes this world-dependent at all.
    """
    n_hs = len(obs.set_winner)
    live_hs = [h for h in range(n_hs) if obs.set_winner[h] is None]
    askers = sorted({ev.asker for ev in obs.history
                     if isinstance(ev, AskEvent) and ev.asker != obs.player})
    out = {}
    for p in askers:
        vals = []
        for w in worlds:
            hand = w[p]
            tot = 0.0
            for h in live_hs:
                d = sum(1 for c in half_suit_cards(h) if hand >> c & 1)
                if d:
                    tot += float(d) ** alpha
            vals.append(tot)
        if vals:
            out[p] = np.asarray(vals, dtype=np.float64)
    return out


def main(argv):
    n_pos = int(argv[0]) if argv else 24
    n_worlds = int(argv[1]) if len(argv) > 1 else 24
    alphas = [float(a) for a in argv[2:]] or [1.0, 1.207, 2.195]

    positions = harvest(40, 2, n_pos)
    print(f"{len(positions)} positions | {n_worlds} worlds each\n")
    stats = {a: [] for a in alphas}
    for pi, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(31337 + pi), n_draws=160,
                         n_worlds=n_worlds, obs=obs, gamma=GAMMA)
        worlds = post.worlds()
        if len(worlds) < 4:
            continue
        for a in alphas:
            for p, v in denominators(obs, worlds, a).items():
                if v.mean() > 0:
                    stats[a].append(float(v.std() / v.mean()))

    print(f"{'alpha':>7} {'mean CV':>9} {'median':>9} {'p90':>9} {'max':>9} "
          f"{'samples':>8}")
    out = []
    for a in alphas:
        v = np.asarray(stats[a])
        if not v.size:
            continue
        rec = {"alpha": a, "mean_cv": float(v.mean()),
               "median_cv": float(np.median(v)), "p90_cv": float(np.percentile(v, 90)),
               "max_cv": float(v.max()), "n": int(v.size)}
        out.append(rec)
        print(f"{a:>7.3f} {rec['mean_cv']:>9.4f} {rec['median_cv']:>9.4f} "
              f"{rec['p90_cv']:>9.4f} {rec['max_cv']:>9.4f} {rec['n']:>8}")

    print("\nCV is the coefficient of variation of the dropped denominator "
          "across worlds.")
    print("At alpha = 1 it must be exactly 0 -- the depths sum to the hand "
          "size, which is public.")
    print("Anything above 0 is bias the engine absorbs into gamma rather than "
          "modelling.")
    dest = ROOT / "results" / "normaliser_variation.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "scripts4"))
    main(sys.argv[1:])
