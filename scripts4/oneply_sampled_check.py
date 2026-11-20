"""Does a SAMPLED one-ply target pick the same ask as the exact one?

This is the premise the whole v0.6 direction rests on, and it is testable
before any of that direction is built.

The v0.5 result was that fitting the ask objective against the EXACT one-ply
value -- play ask $a$, then revert to engine play, averaged over the enumerated
belief -- found a real defect and produced a correction worth $+0.1220$ sets in
play. That target is only computable where the belief support can be
enumerated, which is $95\\%$ of $m = 1$ decisions, $53\\%$ of $m = 2$, $13\\%$ of
$m = 3$ and none of the rest. Since $m \\le 2$ is under a tenth of all
decisions, almost the whole game is out of reach of it.

The obvious generalisation replaces the enumerated belief with the agent's own
posterior SAMPLES, which exist at every $m$. Whether that is a generalisation
or a different quantity wearing the same name is an empirical question, and the
endgame is exactly where it can be answered, because both are computable there.

WHY THIS IS NOT THE FIT THAT ALREADY FAILED
-------------------------------------------
``jobs/PREREGISTRATION_learned_weights.md`` learned the ask weights against a
paired ROLLOUT REGRESSION target across the whole game, and the result was
-0.745 sets over 2000 pairs: demonstrably worse. Three things differ here, and
this run is about the first of them:

  1. the target -- an average of exact continuations over sampled worlds,
     rather than a regression slope estimated from noisy paired rollouts;
  2. the objective -- the VALUE OF THE ACTION THE POLICY PICKS, not the fit of
     a regression, which is what made the eleven-parameter endgame fit
     detectably worse out of sample while a one-parameter fit generalised;
  3. the complexity -- one parameter, conditional on $m$.

If the answer here is that sampling does not reproduce the exact ranking, the
generalisation is dead on its premise and none of that machinery gets built.

THE MEASURE
-----------
Regret, in the exact target's own units: the exact value of the best ask, minus
the exact value of the ask the sampled target chooses. Zero means the sampled
target would have made the same decision. Agreement rate alone is not enough --
disagreeing about two asks of equal value costs nothing, and the endgame study
found that ties are common.

    py scripts4/oneply_sampled_check.py [n_positions] [draws...]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import ExactII, _clone, _info_key, consistent_deals_multi
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
TARGETS = ROOT / "results" / "ii_ask_targets.jsonl"
WORLD_COUNTS = (8, 16, 32, 64)


def _load_targets():
    rows = [json.loads(x) for x in TARGETS.read_text().splitlines() if x.strip()]
    keep = max(set(r["solver"] for r in rows),
               key=lambda f: sum(1 for r in rows if r["solver"] == f))
    return {(r["layer"], r["game"], r["index"]): r
            for r in rows if r["solver"] == keep}


def _sampled_worlds(rules, seat, st, n_worlds, seed_salt):
    """Posterior draws as the agent would take them, at a chosen world count."""
    obs = Observation.from_state(st, seat)
    key = _info_key(seat, obs)
    a = make_agent(SPEC)
    a.begin_game(seat, rules, int.from_bytes(key[:8], "big") ^ seed_salt)
    a.bel.update(obs)
    post = Posterior(a.bel, a.rng, n_draws=a.n_draws, n_worlds=n_worlds,
                     mode=a.infer_mode, obs=obs, gamma=a.opponent_gamma,
                     depth_mode=a.depth_mode, count_mode=a.count_mode,
                     opp_lambda=a.opp_lambda,
                     gamma_schedule=a.gamma_schedule, sis_tilt=a.sis_tilt)
    return obs, post.worlds()


def main(n_positions: int = 60, draws=WORLD_COUNTS) -> int:
    rules = RuleConfig()
    want = _load_targets()
    print(f"{len(want)} positions carry an exact one-ply value for every ask")
    stats = {k: {"n": 0, "same": 0, "regret": 0.0, "worst": 0.0} for k in draws}
    seen = 0
    for (layer, g, idx) in sorted(want):
        if seen >= n_positions:
            break
        rec = want[(layer, g, idx)]
        vals = rec["values"]
        if sum(1 for v in vals if v is not None) < 2:
            continue
        # Replay to the position.
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        hit = None
        seen_idx = 0
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == layer:
                seen_idx += 1
                if seen_idx == idx:
                    hit = (p, live, [_clone(st)][0])
                    break
            st.apply(p, agents[p].act(obs))
        if hit is None:
            continue
        p, live, st = hit
        obs = Observation.from_state(st, p)
        asks = obs.legal_asks()
        if [repr(a) for a in asks] != rec["asks"]:
            # The replay must land on the same decision, or the exact values
            # belong to a different action list and the comparison is void.
            continue
        best_exact = max(v for v in vals if v is not None)
        probe = ExactII(rules, list(live), p, SPEC)
        seen += 1
        for k in draws:
            _, worlds = _sampled_worlds(rules, p, st, k, 0x5EED)
            approx = []
            for i, a in enumerate(asks):
                if vals[i] is None:
                    approx.append(None)
                    continue
                tot, ok = 0.0, True
                for hands in worlds:
                    t = GameState.from_components(rules, list(hands), st.turn,
                                                  list(st.set_winner))
                    t.history = list(st.history)
                    try:
                        t.apply(p, a)
                    except Exception:
                        ok = False
                        break
                    tot += probe.champion_value([t], [1.0])
                approx.append(tot / len(worlds) if ok else None)
            live_i = [i for i, v in enumerate(approx) if v is not None]
            pick = max(live_i, key=lambda i: approx[i])
            exact_pick = max(live_i, key=lambda i: vals[i])
            s = stats[k]
            s["n"] += 1
            s["same"] += int(pick == exact_pick)
            r = best_exact - vals[pick]
            s["regret"] += r
            s["worst"] = max(s["worst"], r)
        if seen % 10 == 0:
            print(f"  {seen} positions", flush=True)

    print(f"\n{seen} positions compared\n")
    print("  worlds   picks the exact best   mean regret   worst")
    out = {}
    for k in draws:
        s = stats[k]
        if not s["n"]:
            continue
        m = s["regret"] / s["n"]
        print(f"  {k:>6}   {s['same']:>4}/{s['n']:<4} "
              f"({100.0*s['same']/s['n']:5.1f}%)      {m:+.4f}      "
              f"{s['worst']:+.4f}")
        out[k] = {"n": s["n"], "same": s["same"], "mean_regret": m,
                  "worst_regret": s["worst"]}
    if out:
        best = max(out)
        r = out[best]["mean_regret"]
        print()
        if r > 0.05:
            print(f"  At {best} worlds the sampled target still costs "
                  f"{r:+.4f} against the exact one.\n  That is a large "
                  f"fraction of the whole endgame gain the exact target\n  "
                  f"produced ({0.1220:+.4f} in play), so the generalisation "
                  f"is not free and\n  the sampled target is a different "
                  f"quantity rather than a cheaper one.")
        else:
            print(f"  At {best} worlds the sampled target costs {r:+.4f} "
                  f"against the exact one.\n  It reproduces the exact "
                  f"decision closely enough to be worth carrying to\n  the "
                  f"values of $m$ where the exact target does not exist.")
    dest = ROOT / "results" / "oneply_sampled_check.json"
    dest.write_text(json.dumps({"n_positions": seen, "by_worlds": out},
                               indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          tuple(int(x) for x in a[1:]) or WORLD_COUNTS))
