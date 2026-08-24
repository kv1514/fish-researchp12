"""Independent cross-check: exact2 must agree with the v0.3 solver everywhere
the v0.3 solver can answer. A faster solver that is subtly wrong would corrupt
the only absolute ground truth the project has, so this is run before the v2
tablebase is trusted in the champion.
"""
import random, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from fish.benchmark_exact import collect_solvable_positions
from fish.engine import GameState
from fish.exact import ExactSolver, solve_position
from fish.rules import RuleConfig
from fish4.exact2 import Exact2Solver

rules = RuleConfig()
n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 60
print(f"collecting from {n_games} games ...", flush=True)
raw = collect_solvable_positions(n_games=n_games, seed=4242,
                                 generator="probabilistic",
                                 max_live_cards=7, max_per_game=4)
print(f"  {len(raw)} positions", flush=True)
agree_v = agree_a = both = 0
mismatch = []
t1 = t2 = 0.0
for pos in raw:
    st = GameState.from_components(rules, pos["hands"], pos["turn"],
                                   pos["set_winner"])
    st.history = list(pos["history"])
    try:
        t0 = time.perf_counter(); s1 = ExactSolver(rules); v1, _ = s1.solve(st)
        opt1 = set(map(repr, s1.optimal_actions(st))); t1 += time.perf_counter() - t0
    except Exception:
        continue
    try:
        t0 = time.perf_counter(); s2 = Exact2Solver(rules); v2, _ = s2.solve(st)
        opt2 = set(map(repr, s2.optimal_actions(st))); t2 += time.perf_counter() - t0
    except Exception as e:
        mismatch.append(("exact2 refused", repr(e))); continue
    both += 1
    if abs(v1 - v2) < 1e-9:
        agree_v += 1
    else:
        mismatch.append(("value", v1, v2, pos["hands"], pos["turn"]))
    if opt1 == opt2:
        agree_a += 1
    elif abs(v1 - v2) < 1e-9:
        mismatch.append(("optimal-set", sorted(opt1), sorted(opt2)))
print(f"\ncompared {both} positions")
print(f"  value agreement          {agree_v}/{both}")
print(f"  optimal-action-set match {agree_a}/{both}")
print(f"  v0.3 solver time {t1:.1f}s   exact2 time {t2:.1f}s   "
      f"speedup {t1/max(t2,1e-9):.1f}x")
if mismatch:
    print(f"\n{len(mismatch)} mismatches; first 5:")
    for m in mismatch[:5]:
        print("   ", m)
else:
    print("\nno mismatches")
