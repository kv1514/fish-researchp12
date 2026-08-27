"""Bound the m = 2 positions the exact solver cannot reach.

Two thirds of the $m = 2$ layer is unsolved, and the paper currently says only
that -- unsolved, unknown, and the reported mean is therefore a lower bound
"because the unreachable positions are the wide ones". That argument leans on a
trend fitted over supports 2-24 and extrapolated across a gap that runs to
60,480 deals. It is an argument, not a measurement.

This replaces the argument with two things that are true by construction.

THE UPPER BOUND
---------------
Solving ONE deal is the perfect-information relaxation of the position: the
deviator is told the deal and may pick a different action in each. Any genuine
imperfect-information policy must pick one action per information set, so it is
a policy the relaxation is also allowed to play. Hence

    V_II  <=  sum_d w_d * V_PI(d)                                       (U)

for every position, solved or not. ``ExactII`` on a single state IS V_PI(d) --
same code, same champion opponents, no new solver to trust.

THE LOWER BOUND
---------------
Any single policy's value is attainable, so it bounds the optimum from below.
Take the best root action that is legal in every deal, then play the champion:

    V_II  >=  max_a sum_d w_d * champion_value(deal d after a)           (L)

The champion's own root action is one of the candidates, so L >= C and the
bounded gain never goes negative.

WHAT THE UPPER BOUND RESTS ON, AND WHAT IT DOES NOT
---------------------------------------------------
The two bounds do not depend on the same things, and the difference matters.

The LOWER bound is safe under any restriction of the action set: leaving a move
out can only make the best candidate worse, so L stays attainable and stays a
lower bound whatever ``_claim_candidates`` does.

The UPPER bound is not. If V_PI(d) were computed over a restricted action set
that excluded a genuinely optimal move, it would UNDERSTATE the relaxation and
U would stop being a bound. So it inherits one assumption from the exact study:
that a declaration true in no candidate deal is weakly dominated. It scores -1
for that half-suit, which is the least it can score, so no line beginning with a
false claim beats the same line beginning with a true one or with an ask. That
is the same argument ``_claim_candidates`` already rests on, and it is now
load-bearing for a bound as well as for a speedup, which is why it is written
down here rather than assumed.

THE CONTROL
-----------
On a position the exact solver DID solve, the exact value must lie inside
[L, U]. That check needs no ground truth beyond what is already computed, it
covers all three quantities at once, and a single violation means one of them
is wrong. The run refuses to write a result if any position violates it.

WHAT WOULD MAKE THE PAPER'S CLAIM FALSE
---------------------------------------
The claim is that the reported +0.3250 over solved m = 2 positions is a LOWER
bound on the whole layer. If the mean of U - C over the unsolved positions
comes back at or below +0.3250, then the true gain there is at or below it too,
the whole-layer mean is BELOW the reported one, and the claim is refuted -- not
weakened, refuted, and by a bound rather than by an extrapolation.

    py scripts4/ii_bound_unsolved.py [n_games] [max_support]
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, SolveTimeout, _champion_action, _clone,
                            consistent_deals_multi)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
#: Per-DEAL budget for the perfect-information solve. One deal is a far smaller
#: tree than the belief set, so this is generous rather than tight.
PI_NODES = 40_000
PI_BACKSTOP = 25.0
#: Total budget for the whole upper-bound stage of ONE position. Without it a
#: 400-deal position is 400 separate solves and can run for hours; with it the
#: stage stops and the remaining deals take the trivial bound, which costs
#: tightness and costs nothing in soundness. Bounding every position loosely
#: beats bounding a handful tightly and calling the rest unknown.
PI_TOTAL_NODES = 400_000
PI_TOTAL_SECONDS = 90.0
#: Budget for the lower-bound stage. Taking the max over a SUBSET of the
#: actions is still a lower bound -- it can only be smaller -- so running out
#: of time here costs tightness and never soundness. The champion's own action
#: is always evaluated first, so however little budget is left the bound is at
#: least the champion's value and the reported gain cannot go negative.
LOWER_SECONDS = 120.0
#: How wide a support this run will enumerate. The exact study capped at 24;
#: this is the whole point of the run, so it goes far wider. Positions above it
#: are counted and reported, never silently dropped.
MAX_SUPPORT = 400
#: Positions at or below this support ALSO get a full exact solve, in this same
#: run, on the same state object -- that is the control. It is computed here
#: rather than joined to ``results/ii_endgame_m2.json`` because that file keys
#: its rows by game alone, with several rows per game in encounter order and
#: only for the positions it attempted. Lining those up against a different
#: enumeration would be a guess, and a control built on a guessed join checks
#: nothing. Recomputing costs a few seconds a position and removes the join.
CONTROL_MAX_SUPPORT = 12
CONTROL_NODES = 300_000
CONTROL_BACKSTOP = 120.0
JOURNAL = ROOT / "results" / "ii_bound_journal.jsonl"


def _fp() -> str:
    """Fingerprint the solver AND this script.

    The solver alone is not enough here. The numbers in the journal are the
    bounds, and the bounds are defined in this file -- change the fallback, the
    budget or the action set and every stored row means something different
    while the solver hash sits unchanged. Rows from another fingerprint are
    ignored rather than mixed in.
    """
    h = hashlib.sha256()
    h.update((ROOT / "fish4" / "exact_ii.py").read_bytes())
    h.update(Path(__file__).resolve().read_bytes())
    return h.hexdigest()[:12]


def _pi_upper(rules, live, me, states, weights):
    """Sum_d w_d V_PI(d), with a rigorous fallback for any deal not solved.

    A deal whose single-deal solve runs out of budget falls back to
    ``_upper``, the most that deal could ever pay. That keeps the sum an upper
    bound whatever happens; it only makes it looser. The count of fallbacks is
    returned so a loose bound is never mistaken for a tight one.
    """
    tot = 0.0
    fell_back = 0
    nodes = 0
    stop = time.monotonic() + PI_TOTAL_SECONDS
    probe = ExactII(rules, list(live), me, SPEC)
    for s, w in zip(states, weights):
        if nodes >= PI_TOTAL_NODES or time.monotonic() > stop:
            tot += w * probe._upper([s], [1.0])
            fell_back += 1
            continue
        sv = ExactII(rules, list(live), me, SPEC)
        sv.max_nodes = PI_NODES
        sv.deadline = min(time.monotonic() + PI_BACKSTOP, stop)
        try:
            v = sv.solve([_clone(s)], [1.0])
        except SolveTimeout:
            v = sv._upper([s], [1.0])
            fell_back += 1
        nodes += sv.nodes
        tot += w * v
    return tot, fell_back, nodes


def _one_ply_lower(rules, live, me, states, weights):
    """max over root actions legal in EVERY deal of "play it, then champion".

    The champion's own root action is included explicitly, so the returned
    value is at least the champion's and the bounded gain cannot be negative.
    """
    probe = ExactII(rules, list(live), me, SPEC)
    acts = [a for a in probe._legal(states[0]) if not isinstance(a, Claim)]
    acts = acts + probe._claim_candidates(states)
    champ = _champion_action(SPEC, rules, me, states[0])
    if champ is not None and not any(repr(a) == repr(champ) for a in acts):
        acts.append(champ)
    # Champion first, unconditionally: it is what makes L >= C true.
    if champ is not None:
        acts.sort(key=lambda a: repr(a) != repr(champ))
    best = None
    best_act = None
    stop = time.monotonic() + LOWER_SECONDS
    skipped = 0
    for a in acts:
        if best is not None and time.monotonic() > stop:
            skipped += 1
            continue
        tot = 0.0
        ok = True
        for s, w in zip(states, weights):
            t = _clone(s)
            try:
                t.apply(me, a)
            except Exception:
                ok = False          # not legal in this deal: not an II action
                break
            tot += w * probe.champion_value([t], [1.0])
        if not ok:
            continue
        if best is None or tot > best:
            best, best_act = tot, a
    return (best if best is not None else 0.0), repr(best_act), skipped


def main(n_games: int = 60, max_support: int = MAX_SUPPORT) -> int:
    rules = RuleConfig()
    fp = _fp()
    done = set()
    rows = []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp:
                    done.add((r["game"], r["index"]))
                    rows.append(r)
    print(f"  solver {fp}; {len(done)} positions already bounded")

    too_wide = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        idx = 0
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 2:
                idx += 1
                if (g, idx) not in done:
                    agents[p].bel.update(obs)
                    deals = consistent_deals_multi(obs, agents[p].bel, live,
                                                   limit=max_support + 1)
                    if not deals:
                        pass
                    elif len(deals) > max_support:
                        too_wide += 1
                    else:
                        states = []
                        for hands in deals:
                            t = GameState.from_components(
                                rules, list(hands), st.turn,
                                list(st.set_winner))
                            t.history = list(st.history)
                            states.append(t)
                        w = [1.0 / len(states)] * len(states)
                        probe = ExactII(rules, list(live), p, SPEC)
                        t0 = time.time()
                        c = probe.champion_value(
                            [_clone(s) for s in states], list(w))
                        u, fb, pn = _pi_upper(rules, live, p, states, w)
                        lo, act, skipped = _one_ply_lower(
                            rules, live, p, states, w)
                        exact = None
                        if len(deals) <= CONTROL_MAX_SUPPORT:
                            sv = ExactII(rules, list(live), p, SPEC)
                            sv.max_nodes = CONTROL_NODES
                            sv.deadline = time.monotonic() + CONTROL_BACKSTOP
                            try:
                                exact = sv.solve(
                                    [_clone(s) for s in states], list(w))
                            except SolveTimeout:
                                exact = None
                        rec = {"game": g, "index": idx, "solver": fp,
                               "support": len(deals), "champion": c,
                               "upper": u, "lower": lo,
                               "gain_upper": u - c, "gain_lower": lo - c,
                               "exact": exact,
                               "gain_exact": (None if exact is None
                                              else exact - c),
                               "pi_fallbacks": fb, "pi_nodes": pn,
                               "best_one_ply": act,
                               "actions_skipped": skipped,
                               "seconds": time.time() - t0}
                        rows.append(rec)
                        with JOURNAL.open("a") as fh:
                            fh.write(json.dumps(rec) + "\n")
                        ex = ("" if exact is None
                              else f"  exact {exact-c:+.3f}")
                        print(f"    g{g} sup {len(deals):>4}  gain in "
                              f"[{lo-c:+.3f}, {u-c:+.3f}]{ex}  "
                              f"{fb} fb / {skipped} skip  "
                              f"{time.time()-t0:5.1f}s", flush=True)
            st.apply(p, agents[p].act(obs))

    if not rows:
        print("no positions bounded")
        return 1

    bad = [r for r in rows if r["gain_lower"] > r["gain_upper"] + 1e-9]
    if bad:
        print(f"\n{len(bad)} positions with lower > upper. One of the two is "
              f"wrong. Refusing to write a result.")
        for r in bad[:5]:
            print(f"  g{r['game']} i{r['index']}: "
                  f"[{r['gain_lower']:+.4f}, {r['gain_upper']:+.4f}]")
        return 1
    neg = [r for r in rows if r["gain_lower"] < -1e-9]
    if neg:
        print(f"\n{len(neg)} positions with a NEGATIVE lower bound, which "
              f"cannot happen: the champion's own move is a candidate. "
              f"Refusing to write a result.")
        return 1

    # -- the control: every exactly solved position must land inside ---------
    checked = viol = 0
    for r in rows:
        if r.get("gain_exact") is None:
            continue
        checked += 1
        ge = r["gain_exact"]
        if not (r["gain_lower"] - 1e-6 <= ge <= r["gain_upper"] + 1e-6):
            viol += 1
            print(f"  OUTSIDE: g{r['game']} i{r['index']} exact {ge:+.4f} "
                  f"not in [{r['gain_lower']:+.4f}, {r['gain_upper']:+.4f}]")
    print(f"\ncontrol: {checked - viol}/{checked} exactly solved positions "
          f"lie inside their own bounds")
    if viol:
        print("A bound that excludes the truth is not a bound. Refusing to "
              "write a result.")
        return 1
    if not checked:
        print("No position was solved exactly, so nothing checked the bounds. "
              "Refusing to write a result on an unchecked instrument.")
        return 1

    sol = [r for r in rows if r.get("gain_exact") is not None]
    # "Not solved here" is not the same as "not solvable": positions above
    # CONTROL_MAX_SUPPORT were never attempted exactly in this run. Both go in
    # the wide group, and the split is reported so neither is read as the other.
    uns = [r for r in rows if r.get("gain_exact") is None]
    untried = [r for r in uns if r["support"] > CONTROL_MAX_SUPPORT]

    def stat(v):
        n = len(v)
        if not n:
            return None
        m = sum(v) / n
        var = sum((x - m) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
        return m, (var / n) ** 0.5, n

    print(f"\n{len(rows)} positions bounded ({len(sol)} also solved exactly "
          f"here, {len(uns)} not -- of those {len(untried)} were never "
          f"attempted, being above support {CONTROL_MAX_SUPPORT}); "
          f"{too_wide} above support {max_support}")
    su = stat([r["gain_upper"] for r in sol])
    se = stat([r["gain_exact"] for r in sol])
    sl = stat([r["gain_lower"] for r in sol])
    if su:
        print(f"  where truth is known: exact {se[0]:+.4f}, "
              f"bounds [{sl[0]:+.4f}, {su[0]:+.4f}] over {se[2]} positions")
        print(f"    the upper bound overshoots the truth by "
              f"{su[0]-se[0]:+.4f}, the lower undershoots by "
              f"{se[0]-sl[0]:+.4f}")
    uu = stat([r["gain_upper"] for r in uns])
    ul = stat([r["gain_lower"] for r in uns])
    # How loose the bounds were allowed to get, said out loud. A fallback
    # loosens the upper bound and a skipped action loosens the lower one, so a
    # run where both are common is a run whose interval is wide by budget
    # rather than by the game.
    fb_pos = sum(1 for r in rows if r["pi_fallbacks"])
    sk_pos = sum(1 for r in rows if r.get("actions_skipped"))
    print(f"  loosened by budget: {fb_pos} positions took the trivial upper "
          f"bound for at least one deal, {sk_pos} left at least one action "
          f"unevaluated in the lower bound")
    head = None
    m2 = ROOT / "results" / "ii_endgame_m2.json"
    if m2.exists():
        head = json.loads(m2.read_text())["mean_gain"]
    if uu:
        print(f"  where it is not: bounds [{ul[0]:+.4f}, {uu[0]:+.4f}] "
              f"over {uu[2]} positions "
              f"(upper 95% CI [{uu[0]-1.96*uu[1]:+.4f}, "
              f"{uu[0]+1.96*uu[1]:+.4f}])")
    if uu and head is not None:
        print(f"\n  the paper reports {head:+.4f} over the solved positions "
              f"and calls it a lower bound on the layer.")
        if uu[0] <= head:
            print(f"  REFUTED: the unsolved positions cannot average more "
                  f"than {uu[0]:+.4f}, which is below it.")
        elif ul[0] > head:
            print(f"  Held, by attainment rather than by a trend: the "
                  f"unsolved positions' LOWER bound {ul[0]:+.4f} is already "
                  f"above {head:+.4f}, so a policy that achieves it exists.")
        else:
            print(f"  Not settled: the unsolved positions are bounded into "
                  f"[{ul[0]:+.4f}, {uu[0]:+.4f}], which straddles "
                  f"{head:+.4f}. The bound is real but too loose to decide.")

    out = ROOT / "results" / "ii_bound_unsolved.json"
    out.write_text(json.dumps({
        "n_games": n_games, "max_support": max_support,
        "n_bounded": len(rows), "n_also_solved": len(sol),
        "n_unsolved": len(uns), "too_wide": too_wide,
        "control_checked": checked, "control_ok": checked - viol,
        "positions_with_pi_fallback": sum(1 for r in rows
                                          if r["pi_fallbacks"]),
        "positions_with_skipped_actions": sum(
            1 for r in rows if r.get("actions_skipped")),
        "pi_nodes": PI_NODES, "control_max_support": CONTROL_MAX_SUPPORT,
        "n_never_attempted_exactly": len(untried),
        "headline_solved_mean": head,
        "solved_exact_mean": se[0] if se else None,
        "solved_lower_mean": sl[0] if sl else None,
        "solved_upper_mean": su[0] if su else None,
        "unsolved_upper_mean": uu[0] if uu else None,
        "unsolved_upper_se": uu[1] if uu else None,
        "unsolved_lower_mean": ul[0] if ul else None,
        "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          int(a[1]) if len(a) > 1 else MAX_SUPPORT))
