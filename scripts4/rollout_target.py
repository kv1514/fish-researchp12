"""Does a marginal card still matter by the end of the game?

The paper's attempt to LEARN the ask objective failed, and it diagnosed the
failure precisely (Section "Learning the ask objective"): not the statistics,
not the model class, but the rollout policy. Its words:

    A rollout has to be finished by a policy that can attach to a determinized
    mid-game position, and the belief tracker cannot: it is anchored on the
    initial deal and refuses. That leaves a public-information heuristic, which
    throws away most of the value of a marginal card, so a card won by a good
    ask is largely squandered before the game ends and the ask stops mattering
    to the final differential.

Its evidence was a number: position-centred rollout value rose by only +0.101
sets across the ENTIRE range of P(success). Winning the card you asked for
barely changed how the deal ended, which makes the target uninformative however
carefully it is fitted.

``scripts4/ask_regret.py`` finishes its rollouts with the full v0.4 policy,
exact posterior and all. The belief tracker attaches after all: hand it the real
public history alongside the determinized current hand and ``initial_hand()``
back-computes a consistent deal to anchor on. Nothing is caught and softened --
``FishBot4.act`` RAISES ``BeliefContradiction`` rather than falling back, so a
tracker that could not attach would crash the run rather than quietly degrade it.

So the paper's blocker is removable, and this script measures whether removing it
removes the symptom. The test is the paper's own: regress position-centred
rollout value on P(success). If the slope is still near +0.101 the diagnosis was
wrong and something else is flattening the target; if it is much larger, the
continuation really was the wall, and the whole learning line is worth re-running
against a target that now carries signal.

Usage: python scripts4/rollout_target.py [n_pos] [n_worlds] [min_resolved] [out]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.beliefs import BeliefState
from fish.observation import Observation
from fish4.askfeat import (TERM_NAMES, AskWeights, DecisionContext,
                           ask_feature_matrix)
from fish4.posterior import Posterior

from ask_regret import GAMMA, SPEC, _legal_asks, _rollout, harvest

PAPER_SLOPE = 0.101


def gather(n_pos: int, n_worlds: int, min_resolved: int, seed0: int = 8821):
    rows = []
    positions = harvest(80, min_resolved, n_pos)
    t0 = time.time()
    for pi, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(seed0 + pi), n_draws=160,
                         n_worlds=n_worlds, obs=obs, gamma=GAMMA)
        worlds = post.worlds()
        asks = _legal_asks(obs)
        if len(asks) < 2 or len(worlds) < 4:
            continue
        ctx = DecisionContext(obs, bel, post)
        p, F = ask_feature_matrix(ctx, asks)
        p = np.asarray(p, dtype=np.float64)
        F = np.asarray(F, dtype=np.float64)
        seeds = [[(seed0 + 7919 * pi + 31 * wi + q) for q in range(6)]
                 for wi in range(len(worlds))]
        for ai, a in enumerate(asks):
            vals = []
            for wi, w in enumerate(worlds):
                v = _rollout(rules, w, turn, sw, hist, a, seat, seeds[wi])
                if v is not None:
                    vals.append(v)
            if not vals:
                continue
            rows.append({"position": pi, "p_success": float(p[ai]),
                         "q": float(np.mean(vals)), "n_worlds": len(vals),
                         "features": F[ai].tolist()})
        print(f"  pos {pi:>3}  asks={len(asks):>2}  "
              f"[{time.time() - t0:.0f}s]", flush=True)
    return rows


def centred_slope(rows, key="p_success"):
    """Slope of rollout value on ``key``, with every position's mean removed.

    Position centring is what makes this comparable across positions: a late
    position where our team is already three sets up has a high rollout value
    for every ask, and that between-position variation says nothing about
    whether the ask mattered.
    """
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    xs, ys = [], []
    for _, group in by.items():
        if len(group) < 2:
            continue
        x = np.array([g[key] for g in group], dtype=float)
        y = np.array([g["q"] for g in group], dtype=float)
        if np.std(x) < 1e-12:
            continue                       # no contrast to learn from
        xs.append(x - x.mean())
        ys.append(y - y.mean())
    if not xs:
        return None
    X = np.concatenate(xs)
    Y = np.concatenate(ys)
    b = float(np.sum(X * Y) / np.sum(X * X))
    resid = Y - b * X
    # clustered by position, since asks within one share worlds and seeds
    num = 0.0
    i = 0
    for x in xs:
        k = len(x)
        e = resid[i:i + k]
        num += float(np.sum(x * e)) ** 2
        i += k
    se = float(np.sqrt(num) / np.sum(X * X))
    return {"slope": b, "se_clustered": se, "n_points": int(X.size),
            "n_positions": len(xs),
            "range": float(max(r[key] for r in rows)
                           - min(r[key] for r in rows))}


def main(argv):
    n_pos = int(argv[0]) if argv else 40
    n_worlds = int(argv[1]) if len(argv) > 1 else 12
    min_resolved = int(argv[2]) if len(argv) > 2 else 4
    dest = (Path(argv[3]) if len(argv) > 3
            else ROOT / "results" / "rollout_target.json")

    print("does a marginal card survive to the end of the deal?")
    print(f"{n_pos} positions | {n_worlds} worlds | "
          f">= {min_resolved} half-suits resolved | full v0.4 continuation\n")
    rows = gather(n_pos, n_worlds, min_resolved)
    if not rows:
        print("no usable positions")
        return

    s = centred_slope(rows)
    print(f"\ncandidate asks scored   {s['n_points']} "
          f"across {s['n_positions']} positions")
    print(f"P(success) slope        {s['slope']:+.4f} "
          f"+/- {s['se_clustered']:.4f}  (clustered by position)")
    print(f"the paper, with a public-information continuation:  "
          f"+{PAPER_SLOPE:.3f}")
    z = (s["slope"] - PAPER_SLOPE) / s["se_clustered"] if s["se_clustered"] else float("nan")
    print(f"difference              {s['slope'] - PAPER_SLOPE:+.4f}  "
          f"({z:+.1f} SE)")
    if s["slope"] > PAPER_SLOPE + 2 * s["se_clustered"]:
        print("\nThe target carries more signal than it did. The paper's "
              "diagnosis was right\nabout the mechanism and the mechanism is "
              "removable: with a real belief tracker\nfinishing the rollout, "
              "winning the card you asked for still shows up in how\nthe deal "
              "ends, so the learning line is worth re-running.")
    elif s["slope"] < PAPER_SLOPE + 2 * s["se_clustered"]:
        print("\nThe slope is not meaningfully larger. Whatever flattens this "
              "target, it is\nnot only the continuation policy -- so the "
              "learning line stays blocked, and\nfor a reason that has not "
              "been identified yet.")

    out = {"n_positions": n_pos, "n_worlds": n_worlds,
           "min_resolved": min_resolved, "paper_slope": PAPER_SLOPE,
           "p_success_slope": s, "rows": rows}
    for j, name in enumerate(TERM_NAMES):
        for r in rows:
            r[f"f_{name}"] = r["features"][j]
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
