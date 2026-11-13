"""Is the m = 3 defect real, or is it the maximum of a noisy estimate?

``oneply_m3_defect.py`` reports that the engine's ask is beaten by another on
96% of m = 3 positions, with a mean gain of +0.6257. Taken at face value that
is a bigger defect than the endgame's. Taken carefully it is not yet evidence
of anything, because the target is SAMPLED and the statistic is a MAXIMUM over
fifteen to twenty-one candidate asks. The maximum of noisy estimates is biased
upward whether or not any candidate is genuinely better, so "some ask beat the
engine's" is close to guaranteed at that action count. The endgame results did
not have this problem: their target was exact.

THE CONTROL
-----------
Cross-fitting. Draw two INDEPENDENT sets of posterior worlds, A and B, for the
same position:

  * choose the best ask under A -- selection happens on A alone;
  * score that ask, and the engine's, under B -- evaluation happens on B alone.

The B-sample gain is unbiased for the chosen ask, because nothing about B was
used to choose it. The difference between the naive A-gain and the cross-fitted
B-gain is exactly the selection bias, measured rather than argued.

WHAT EACH OUTCOME MEANS
-----------------------
If the cross-fitted gain is near zero, the defect at m = 3 is an artefact of
maximising a noisy estimate and this whole direction stops here. If it stays
clearly positive, the defect is real and the difference from the naive figure
is the size of the bias, which is worth knowing on its own for anything else
that maximises a sampled target.

    py scripts4/oneply_crossfit_control.py [n_positions] [n_worlds] [layer]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import ExactII, _champion_action, _info_key
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def _worlds(rules, seat, st, n_worlds, salt):
    obs = Observation.from_state(st, seat)
    key = _info_key(seat, obs)
    a = make_agent(SPEC)
    a.begin_game(seat, rules, (int.from_bytes(key[:8], "big") ^ salt)
                 & ((1 << 63) - 1))
    a.bel.update(obs)
    post = Posterior(a.bel, a.rng, n_draws=a.n_draws, n_worlds=n_worlds,
                     mode=a.infer_mode, obs=obs, gamma=a.opponent_gamma,
                     depth_mode=a.depth_mode, count_mode=a.count_mode,
                     opp_lambda=a.opp_lambda,
                     gamma_schedule=a.gamma_schedule, sis_tilt=a.sis_tilt)
    return obs, post.worlds()


def _values(rules, live, seat, st, asks, worlds):
    probe = ExactII(rules, list(live), seat, SPEC)
    out = []
    for a in asks:
        tot, ok = 0.0, True
        for hands in worlds:
            t = GameState.from_components(rules, list(hands), st.turn,
                                          list(st.set_winner))
            t.history = list(st.history)
            try:
                t.apply(seat, a)
            except Exception:
                ok = False
                break
            tot += probe.champion_value([t], [1.0])
        out.append(tot / len(worlds) if ok else None)
    return out


def main(n_positions: int = 25, n_worlds: int = 48, layer: int = 3) -> int:
    rules = RuleConfig()
    naive, cross = [], []
    rows = []
    for g in range(400):
        if len(rows) >= n_positions:
            break
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal or len(rows) >= n_positions:
                break
            p = st.turn
            obs0 = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs0.set_winner) if w is None]
            if len(live) == layer:
                t0 = time.time()
                obsA, wA = _worlds(rules, p, st, n_worlds, 0xA1)
                _, wB = _worlds(rules, p, st, n_worlds, 0xB2)
                asks = obsA.legal_asks()
                champ = _champion_action(SPEC, rules, p, st)
                cr = [repr(x) for x in asks]
                if len(asks) >= 2 and repr(champ) in cr:
                    ci = cr.index(repr(champ))
                    vA = _values(rules, live, p, st, asks, wA)
                    vB = _values(rules, live, p, st, asks, wB)
                    ok = [i for i, v in enumerate(vA)
                          if v is not None and vB[i] is not None]
                    if ci in ok and len(ok) >= 2:
                        bi = max(ok, key=lambda i: vA[i])
                        naive.append(vA[bi] - vA[ci])
                        cross.append(vB[bi] - vB[ci])
                        rows.append({"game": g, "n_asks": len(asks),
                                     "naive": vA[bi] - vA[ci],
                                     "cross": vB[bi] - vB[ci],
                                     "seconds": time.time() - t0})
                        if len(rows) % 5 == 0:
                            print(f"    {len(rows)} positions", flush=True)
            st.apply(p, agents[p].act(obs0))

    if len(rows) < 10:
        print(f"only {len(rows)} positions; too few")
        return 1

    def stat(v):
        n = len(v)
        m = sum(v) / n
        var = sum((x - m) ** 2 for x in v) / (n - 1)
        return m, (var / n) ** 0.5, n

    mn, sn, n = stat(naive)
    mc, sc, _ = stat(cross)
    bias = mn - mc
    print(f"\nm = {layer}, {n} positions, {n_worlds} worlds per sample")
    print(f"  naive gain (chosen and scored on the SAME sample): "
          f"{mn:+.4f} [{mn-1.96*sn:+.4f}, {mn+1.96*sn:+.4f}]")
    print(f"  cross-fitted (chosen on A, scored on B):           "
          f"{mc:+.4f} [{mc-1.96*sc:+.4f}, {mc+1.96*sc:+.4f}]")
    print(f"  selection bias: {bias:+.4f} "
          f"({100.0*bias/mn:.0f}% of the naive figure)")
    if mc - 1.96 * sc > 0:
        print(f"\n  The defect survives cross-fitting. An ask chosen without "
              f"reference to the\n  sample it is scored on still beats the "
              f"engine's, so this is not the\n  maximum of noise.")
        verdict = "real"
    elif mc + 1.96 * sc < 0:
        print(f"\n  Cross-fitted, the chosen ask is WORSE than the engine's. "
              f"The naive figure\n  was selection, and worse than nothing.")
        verdict = "reversed"
    else:
        print(f"\n  Cross-fitted, the gain does not clear zero. The naive "
              f"{mn:+.4f} was mostly\n  or entirely the maximum of a noisy "
              f"estimate, and this direction stops\n  here rather than being "
              f"pushed to a bigger sample.")
        verdict = "not-shown"
    dest = ROOT / "results" / f"oneply_crossfit_m{layer}.json"
    dest.write_text(json.dumps({
        "layer": layer, "worlds": n_worlds, "n": n,
        "naive": mn, "naive_ci": [mn - 1.96 * sn, mn + 1.96 * sn],
        "cross": mc, "cross_ci": [mc - 1.96 * sc, mc + 1.96 * sc],
        "selection_bias": bias, "verdict": verdict, "rows": rows}, indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 25,
                          int(a[1]) if len(a) > 1 else 48,
                          int(a[2]) if len(a) > 2 else 3))
