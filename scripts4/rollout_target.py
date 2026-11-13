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

Usage: python scripts4/rollout_target.py [n_pos] [n_worlds] [min_resolved]
                                        [continuation] [out]

``continuation`` is ``v04`` (the engine) or ``public`` (the incumbent
heuristic). The second is the control: the published +0.101 was measured on a
DIFFERENT position distribution -- the learning harvest, which spans the whole
deal -- so comparing it to a number from late positions attributes to the
continuation what may be position mix. Running both arms on the same positions
is the only version of the comparison the numbers support.
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


def _public_seeded_rollout(rules, world, turn, set_winner, history,
                           root_action, root_seat, seat_seeds):
    """The SECOND control: the weak policy, but handed the public log too.

    The two arms above differ in two things, not one. The engine finishes the
    game AND is handed the real public history; the heuristic finishes the game
    AND starts from an empty log, blind to every card the table has already
    watched change hands. Reading the whole contrast as "the continuation
    policy" is therefore the two-factor error this section of the paper is
    about, committed one level further in.

    This arm holds the information fixed and moves only the policy. If it lands
    near the unseeded heuristic, the contrast is the policy's and the published
    reading stands. If it lands near the engine, most of what was attributed to
    finishing the game properly was really the log.
    """
    return _public_rollout(rules, world, turn, set_winner, history,
                           root_action, root_seat, seat_seeds, seed_log=True)


def _public_rollout(rules, world, turn, set_winner, history, root_action,
                    root_seat, seat_seeds, seed_log: bool = False):
    """The CONTROL arm: finish the deal with the public-information heuristic.

    Same positions, same worlds, same seeds, same root action as ``_rollout``.
    The only difference is who plays the rest of the game -- and, necessarily,
    that the determinized state starts with an empty public log, which is the
    knowledge set ``PublicInfoHeuristic`` is defined and audited against and
    what the original learning rollouts gave it.

    This arm exists because without it the comparison is confounded. The
    published +0.101 was measured over the LEARNING harvest, whose positions run
    the whole deal (median two half-suits resolved); this script harvests late
    positions (four or more, by construction). Attributing a difference between
    the two to the continuation policy, when the position distributions also
    differ, is not something the numbers support. Running both arms here holds
    the positions fixed so that the continuation is the only thing that moves.
    """
    from fish.cards import team_of
    from fish.engine import GameState, IllegalAction
    from fish4.learn.rollout import PublicInfoHeuristic

    from ask_regret import MAX_ACTIONS, NUM_PLAYERS, _score

    state = GameState.from_components(rules, list(world), turn,
                                      list(set_winner))
    if seed_log:
        state.history = list(history)
    agents = [PublicInfoHeuristic() for _ in range(NUM_PLAYERS)]
    for pl, a in enumerate(agents):
        a.begin_game(pl, rules, seat_seeds[pl])
    try:
        state.apply(root_seat, root_action)
    except IllegalAction:
        return None
    n = 0
    while not state.is_terminal and n < MAX_ACTIONS:
        pl = state.turn
        state.apply(pl, agents[pl].act(Observation.from_state(state, pl)))
        n += 1
    return _score(state, team_of(root_seat))


def gather(n_pos: int, n_worlds: int, min_resolved: int, seed0: int = 8821,
           continuation: str = "v04"):
    roll = {"v04": _rollout, "public": _public_rollout,
            "public-seeded": _public_seeded_rollout}[continuation]
    rows = []
    # The DEAL each position came from. `harvest` emits consecutive plies, so
    # 113 positions here came from FOUR deals -- clustering the slope by
    # position treats 110 clusters as independent when there are four, and
    # widens the published half-width 2.33x once corrected.
    deals: list[int] = []
    positions = harvest(80, min_resolved, n_pos, games_out=deals)
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
                v = roll(rules, w, turn, sw, hist, a, seat, seeds[wi])
                if v is not None:
                    vals.append(v)
            if not vals:
                continue
            rows.append({"position": pi, "deal": deals[pi],
                         "p_success": float(p[ai]),
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
    # Cluster on the DEAL where the rows carry one. Asks within a position
    # share worlds and seeds, and positions within a deal share the hands and
    # the whole history before them -- clustering on the position stops one
    # level short. Files written before the `deal` field fall back to the
    # position and say so, rather than silently reporting the tighter number.
    if rows and "deal" not in rows[0]:
        import sys as _sys
        print("  NOTE: rows carry no deal index; clustering on the POSITION, "
              "which understates the interval (see fish4/clustered.py)",
              file=_sys.stderr)
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    xs, ys, cl = [], [], []
    for pi, group in by.items():
        if len(group) < 2:
            continue
        x = np.array([g[key] for g in group], dtype=float)
        y = np.array([g["q"] for g in group], dtype=float)
        if np.std(x) < 1e-12:
            continue                       # no contrast to learn from
        xs.append(x - x.mean())
        ys.append(y - y.mean())
        cl.append(group[0].get("deal", pi))
    if not xs:
        return None
    X = np.concatenate(xs)
    Y = np.concatenate(ys)
    b = float(np.sum(X * Y) / np.sum(X * X))
    resid = Y - b * X
    # CR1 on whatever unit `cl` names -- the deal where the rows carry one,
    # the position otherwise. Scores are summed WITHIN a cluster before being
    # squared, which is the whole point: two positions in the same deal that
    # both push the slope up must not each get counted as evidence.
    from fish4.match import _t_critical
    acc: dict[object, float] = {}
    i = 0
    for x, c in zip(xs, cl):
        k = len(x)
        acc[c] = acc.get(c, 0.0) + float(np.sum(x * resid[i:i + k]))
        i += k
    n_cl = len(acc)
    num = sum(v * v for v in acc.values())
    corr = n_cl / (n_cl - 1.0) if n_cl > 1 else 1.0
    se = float(np.sqrt(num * corr) / np.sum(X * X))
    t = _t_critical(n_cl - 1, 0.95) if n_cl > 1 else float("inf")
    return {"slope": b, "se_clustered": se, "n_points": int(X.size),
            "n_positions": len(xs), "n_clusters": n_cl,
            "clustered_on": "deal" if any("deal" in g[0] for g in by.values())
                            else "position",
            "t_crit": t,
            "ci95": [b - t * se, b + t * se],
            "range": float(max(r[key] for r in rows)
                           - min(r[key] for r in rows))}


def main(argv):
    n_pos = int(argv[0]) if argv else 40
    n_worlds = int(argv[1]) if len(argv) > 1 else 12
    min_resolved = int(argv[2]) if len(argv) > 2 else 4
    continuation = argv[3] if len(argv) > 3 else "v04"
    default = ("rollout_target.json" if continuation == "v04"
               else f"rollout_target_{continuation}.json")
    dest = (Path(argv[4]) if len(argv) > 4
            else ROOT / "results" / default)

    named = {"v04": "full v0.4",
             "public": "public-information heuristic",
             "public-seeded": "public-information heuristic, public log seeded",
             }[continuation]
    print("does a marginal card survive to the end of the deal?")
    print(f"{n_pos} positions | {n_worlds} worlds | "
          f">= {min_resolved} half-suits resolved | {named} continuation\n")
    rows = gather(n_pos, n_worlds, min_resolved, continuation=continuation)
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
           "continuation": continuation,
           "min_resolved": min_resolved, "paper_slope": PAPER_SLOPE,
           "p_success_slope": s, "rows": rows}
    for j, name in enumerate(TERM_NAMES):
        for r in rows:
            r[f"f_{name}"] = r["features"][j]
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
