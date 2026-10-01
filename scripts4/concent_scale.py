"""How big is the corrected concentration feature, and at what weight does it
actually change a decision?

The v1 term was screened once, at weight 0.15 over 160 pairs, and returned
-0.037 [-0.653, +0.578] (paper, the everything-else-we-tried table). That
interval is four times the ship bar in each direction, so it could not have
detected anything -- but there is a worse possibility, and this measures it:
that 0.15 was an INERT weight. A term whose feature is typically 0.01 in
magnitude, weighted 0.15, moves a score by 0.0015 against success
probabilities that differ by tenths. Such a run reports a null about the
harness, not about the idea.

So before any arm is chosen: collect the feature over real decisions and count,
per candidate weight, how often adding it changes which ask is taken. That
count is what sizes the experiment -- scripts4/pairing_value.py showed the
precision a paired run achieves is governed by how often its knob changes a
decision, not by how large the effect is.

    py scripts4/concent_scale.py [n_games] [n_jobs]
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import TERM_NAMES

CONCENT = TERM_NAMES.index("concent")
RULES_D = {"wrong_distribution_outcome": "opponent"}
WEIGHTS = [0.05, 0.15, 0.3, 0.6, 1.0, 2.0]


def _one(seed: int) -> dict:
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4 import askfeat as AF

    rules = RuleConfig(**RULES_D)
    rows, flips = [], Counter()
    real = AF.score_asks

    def spy(ctx, asks, weights):
        s, p = real(ctx, asks, weights)
        if len(asks) > 1:
            _, F = AF.ask_feature_matrix(ctx, asks)
            col = F[:, CONCENT]
            rows.append([float(x) for x in col])
            base = int(np.argmax(s))
            for w in WEIGHTS:
                if int(np.argmax(s + w * col)) != base:
                    flips[w] += 1
            flips["n"] += 1
        return s, p

    AF.score_asks = spy
    # agent4 imported score_asks by name at module load, so patching the
    # module attribute is not enough -- the binding it holds must move too.
    import fish4.agent4 as A4
    real4 = A4.score_asks
    A4.score_asks = spy
    try:
        agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 5150 + seed * 13 + p)
        for _ in range(600):
            if st.is_terminal:
                break
            st.apply(st.turn,
                     agents[st.turn].act(Observation.from_state(st, st.turn)))
    finally:
        AF.score_asks = real
        A4.score_asks = real4
    return {"rows": rows, "flips": dict(flips)}


def main(n_games: int = 8, n_jobs: int = 1) -> int:
    with Pool(n_jobs) as pool:
        out = pool.map(_one, [7_300 + i for i in range(n_games)])
    vals = [abs(x) for r in out for row in r["rows"] for x in row]
    spans = [max(row) - min(row) for r in out for row in r["rows"] if row]
    flips = Counter()
    for r in out:
        for k, v in r["flips"].items():
            flips[float(k) if k != "n" else "n"] += v
    n = flips["n"]
    v = np.array(vals)
    sp = np.array(spans)
    print(f"\n=== the corrected concentration feature, over {n:,} decisions "
          f"with a choice ===\n")
    print(f"  |feature| over {len(v):,} candidate asks")
    for q in (50, 75, 90, 99):
        print(f"    p{q:<3d} {np.percentile(v, q):.4f}")
    print(f"    max  {v.max():.4f}   mean {v.mean():.4f}")
    print(f"\n  SPREAD within one decision (max - min across its candidates),")
    print(f"  which is what actually competes with the score gap")
    for q in (50, 75, 90, 99):
        print(f"    p{q:<3d} {np.percentile(sp, q):.4f}")
    print(f"\n  how often weight w changes which ask is taken")
    print(f"  {'w':>6} {'flips':>8} {'share':>8}")
    out_w = {}
    for w in WEIGHTS:
        c = flips[w]
        out_w[w] = c / n if n else 0.0
        print(f"  {w:6.2f} {c:8,d} {out_w[w]:8.1%}")
    print("\n  A weight that changes nothing is not a dose. The arms for any")
    print("  pre-registration go where this share is meaningful, and the")
    print("  sample size follows from it: scripts4/pairing_value.py showed a")
    print("  knob firing on 80% of decisions gets 1.1x from pairing while one")
    print("  firing on 0.9% gets 414x.")
    dest = ROOT / "results" / "concent_scale.json"
    dest.write_text(json.dumps(
        {"n_decisions": n, "n_candidates": len(v),
         "abs_percentiles": {str(q): float(np.percentile(v, q))
                             for q in (50, 75, 90, 99)},
         "spread_percentiles": {str(q): float(np.percentile(sp, q))
                                for q in (50, 75, 90, 99)},
         "flip_share": {str(w): out_w[w] for w in WEIGHTS}}, indent=1))
    print(f"\nwrote results/{dest.name}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 8,
                          int(a[1]) if len(a) > 1 else 1))
