"""Does the lookahead help or hurt ONE-STEP ask selection? Same rollouts, two
incumbents.

WHY THIS EXISTS
---------------
`results/ask_regret_wide.json` (the ask objective in isolation, 208 positions)
gives cross-fitted regret **-0.0188 [-0.0808, +0.0431]** and "captures 107.4% of
what one-step lookahead can find". `results/ask_regret_champion_wide.json`
(V06_DEPLOYED, 162 positions) gives **+0.1641 [+0.0797, +0.2484]** and 52.0%.

Read side by side that says the lookahead makes one-step ask selection worse.
**Those two runs cannot support that claim** and three things break the
comparison:

1. **Different populations.** Each run harvests from self-play by its own
   policy: 19.0 legal asks a position against 22.1, and a best-worst spread of
   1.5576 against 1.4295. The champion reaches sharper positions.
2. **Different value functions.** `_rollout` plays the continuation with the
   same SPEC, so the two runs score their actions under different games.
3. **An actor/evaluator mismatch in one arm only.** The world-sampling
   posterior is hardcoded at `n_draws=160`. The isolated agent also acts at
   160, so its actor and evaluator agree; the champion acts at 480 and is
   scored on worlds drawn at 160.

THE CLEAN EXPERIMENT, AND IT IS CHEAP
-------------------------------------
The per-world rollout values do not depend on the actor at all -- only the
INCUMBENT does. So one set of positions, one set of worlds and one set of
rollouts can score BOTH actors, and every one of the three confounds above is
held fixed by construction. The rollout policy is still one policy, but it is
the SAME one for both incumbents, which is all the comparison needs.

    py scripts4/actor_compare.py [n_positions] [n_worlds] [out.json] [n_games]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import Ask
from fish.observation import Observation
from fish.beliefs import BeliefState
from fish4.posterior import Posterior
from fish4.registry4 import V06_DEPLOYED, make_agent
from scripts4.ask_regret import (GAMMA, SPEC, _legal_asks, _rollout,
                                 crossfit_regret, harvest)

#: The two incumbents. Everything else is shared.
ACTORS = {"objective only": {"opponent_gamma": 0.35},
          "champion": dict(V06_DEPLOYED[1])}


def main(argv):
    n_positions = int(argv[0]) if argv else 120
    n_worlds = int(argv[1]) if len(argv) > 1 else 24
    dest = Path(argv[2]) if len(argv) > 2 else (
        ROOT / "results" / "actor_compare.json")
    n_games = int(argv[3]) if len(argv) > 3 else 0
    seed0 = 7373

    print(f"actor comparison | {n_positions} positions | {n_worlds} worlds")
    print(f"positions and rollouts both use SPEC = {SPEC}")
    print(f"incumbents compared on IDENTICAL rollouts: {list(ACTORS)}\n")

    positions = harvest(n_games or max(60, n_positions // 2), 5, n_positions)
    rows, t0 = [], time.time()
    for pi, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=tuple(hist))
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(seed0 + pi), n_draws=160,
                         n_worlds=n_worlds, obs=obs, gamma=GAMMA)
        worlds = post.worlds()
        if len(worlds) < 4:
            continue
        asks = _legal_asks(obs)
        if len(asks) < 2:
            continue

        picks = {}
        for name, spec in ACTORS.items():
            a = make_agent(("fishbot4", dict(spec)))
            a.begin_game(seat, rules, seed0 + pi)
            act = a.act(obs)
            if not isinstance(act, Ask):
                picks = {}
                break               # a claim: outside this comparison
            if act not in asks:
                asks.append(act)
            picks[name] = act
        if not picks:
            continue

        nw = len(worlds)
        seeds = [[(seed0 + 7919 * pi + 31 * wi + p) for p in range(NUM_PLAYERS)]
                 for wi in range(nw)]
        per = {}
        for a in asks:
            vals = [(_rollout(rules, w, turn, sw, hist, a, seat, seeds[wi]))
                    for wi, w in enumerate(worlds)]
            vals = [np.nan if v is None else float(v) for v in vals]
            if not np.all(np.isnan(vals)):
                per[a] = np.asarray(vals, dtype=np.float64)
        if len(per) < 2 or any(p not in per for p in picks.values()):
            continue

        row = {"position": pi, "n_asks": len(per),
               "same_pick": int(len(set(picks.values())) == 1)}
        ok = True
        for name, act in picks.items():
            _, naive, xf = crossfit_regret(per, act)
            if xf is None:
                ok = False
                break
            row[name] = xf
        if not ok:
            continue
        rows.append(row)
        print(f"  pos {pi:3d} asks={len(per):3d} same={row['same_pick']} "
              + "  ".join(f"{n}={row[n]:+.3f}" for n in ACTORS)
              + f"  [{time.time()-t0:.0f}s]", flush=True)

    if len(rows) < 20:
        print("too few positions")
        return
    print("\n" + "=" * 74)
    print(f"  ACTOR COMPARISON, {len(rows)} positions, IDENTICAL rollouts")
    print("=" * 74)
    out = {"n": len(rows), "n_worlds": n_worlds, "rollout_spec": SPEC,
           "actors": {}}
    same = np.array([r["same_pick"] for r in rows], dtype=float)
    print(f"\n  the two actors chose the same ask in {same.mean():.1%} "
          f"of positions")
    print(f"\n  {'incumbent':<18}{'regret':>12}{'+/-':>10}")
    vals = {}
    for name in ACTORS:
        x = np.array([r[name] for r in rows], dtype=float)
        vals[name] = x
        h = 1.96 * x.std(ddof=1) / len(x) ** 0.5
        print(f"  {name:<18}{x.mean():>+12.4f}{h:>10.4f}")
        out["actors"][name] = {"regret": float(x.mean()), "half_width": float(h)}
    a, b = list(ACTORS)
    d = vals[b] - vals[a]
    h = 1.96 * d.std(ddof=1) / len(d) ** 0.5
    print(f"\n  PAIRED difference ({b} minus {a}): {d.mean():+.4f} +/- {h:.4f}")
    print("  paired on the position, so the deal variance that dominates")
    print("  everything here cancels. Positive means the champion's pick is")
    print("  WORSE by one-step rollout value.")
    out["paired_difference"] = {"of": b, "minus": a,
                                "mean": float(d.mean()), "half_width": float(h)}
    # Only the positions where they disagree carry any information about the
    # difference; the rest contribute an exact zero and shrink the interval
    # without adding evidence.
    dis = np.array([r for r, s in zip(d, same) if s == 0], dtype=float)
    if len(dis) > 2:
        hd = 1.96 * dis.std(ddof=1) / len(dis) ** 0.5
        print(f"\n  on the {len(dis)} positions where they DISAGREED: "
              f"{dis.mean():+.4f} +/- {hd:.4f}")
        out["disagreements"] = {"n": len(dis), "mean": float(dis.mean()),
                                "half_width": float(hd)}
    dest.write_text(json.dumps(out | {"rows": rows}, indent=1))
    print("\nwrote", dest)


if __name__ == "__main__":
    main(sys.argv[1:])
