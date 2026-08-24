"""Where does belief compute actually go? Profile before optimizing.

Established by this script: world SAMPLING dominates agent compute, not
constraint propagation and not the rule engine. That finding drove the
cached, OR-seeded sampler (736 -> 178 us/world).
"""

import cProfile
import io
import pstats
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.agents import ProbabilisticAgent
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def collect_positions(n_games=6, seed=0):
    rules = RuleConfig()
    out = []
    rng = random.Random(seed)
    for g in range(n_games):
        state = GameState.deal(rules, seed=100 + g)
        agents = [ProbabilisticAgent(n_samples=8) for _ in range(6)]
        for p, a in enumerate(agents):
            a.begin_game(p, rules, rng.getrandbits(64))
        step = 0
        while not state.is_terminal and step < 120:
            p = state.turn
            obs = Observation.from_state(state, p)
            if step in (10, 30, 60, 90):
                bel = BeliefState(rules, observer=p)
                bel.update(obs)
                out.append((obs, bel))
            state.apply(p, agents[p].act(obs))
            step += 1
    return out


def bench_sampling(positions, n=200):
    rng = random.Random(1)
    t0 = time.perf_counter()
    for _, bel in positions:
        for _ in range(n):
            bel.sample_current_hands(rng)
    dt = time.perf_counter() - t0
    total = len(positions) * n
    print(f"  sampling: {total} worlds in {dt:.2f}s = {total/dt:,.0f} worlds/s "
          f"({dt/total*1e6:.0f} us/world)")
    return dt


def bench_update(positions, repeats=20):
    rules = RuleConfig()
    t0 = time.perf_counter()
    count = 0
    for obs, _ in positions:
        for _ in range(repeats):
            b = BeliefState(rules, observer=obs.player)
            b.update(obs)
            count += 1
    dt = time.perf_counter() - t0
    print(f"  full belief rebuild: {count} in {dt:.2f}s = "
          f"{dt/count*1e3:.2f} ms each")
    return dt


def profile_sampler(positions, top=16):
    pr = cProfile.Profile()
    rng = random.Random(3)
    pr.enable()
    for _, bel in positions[:8]:
        for _ in range(40):
            bel.sample_current_hands(rng)
    pr.disable()
    s = io.StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(top)
    print("\n--- sampler profile ---")
    print("\n".join(s.getvalue().splitlines()[4:top + 8]))


if __name__ == "__main__":
    print("collecting real mid-game positions...")
    positions = collect_positions()
    print(f"{len(positions)} positions\n")
    print("== belief benchmarks ==")
    t_sample = bench_sampling(positions)
    t_update = bench_update(positions)
    print(f"\n  sampling / rebuild ratio: {t_sample/t_update:.1f}x")
    profile_sampler(positions)
