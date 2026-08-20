"""Why does search lose to its own prior? Measure, do not guess.

Findings this script established (see RESEARCH_LOG.md):
  D1  eval@depth correlates +0.73 with the true final differential, so the
      evaluation function is NOT the problem.
  D2  the spread of one action's value across sampled worlds (0.698) is
      ~2.4x the gap between the best and worst action (0.293). Comparing
      actions on DIFFERENT worlds therefore ranks luck, not skill. This is
      why PIMC and ISMCTS both lost, and why common random numbers fixed it.
"""

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.agents import HeuristicAgent, ProbabilisticAgent
from fish.agents.search import evaluate
from fish.cards import team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def rollout(state, my_team, depth, rng, rules, policy_cls=HeuristicAgent):
    rollers = [policy_cls() for _ in range(6)]
    for p, r in enumerate(rollers):
        r.begin_game(p, rules, rng.getrandbits(64))
    for _ in range(depth):
        if state.is_terminal:
            break
        p = state.turn
        state.apply(p, rollers[p].act(Observation.from_state(state, p)))
    return evaluate(state, my_team)


def clone(obs, world):
    return GameState.from_components(obs.rules, list(world), obs.turn,
                                     list(obs.set_winner))


def main(n_positions: int = 24, seed: int = 0):
    rules = RuleConfig()
    rng = random.Random(seed)
    positions = []
    for g in range(n_positions):
        state = GameState.deal(rules, seed=1000 + g)
        agents = [ProbabilisticAgent(n_samples=16) for _ in range(6)]
        for p, a in enumerate(agents):
            a.begin_game(p, rules, rng.getrandbits(64))
        for _ in range(rng.randint(20, 60)):
            if state.is_terminal:
                break
            p = state.turn
            state.apply(p, agents[p].act(Observation.from_state(state, p)))
        if state.is_terminal:
            continue
        obs = Observation.from_state(state, state.turn)
        if obs.legal_asks():
            positions.append((obs, list(state.hands), agents[state.turn]))
    print(f"collected {len(positions)} positions\n")

    print("== D1: does eval@depth predict the true final differential? ==")
    for depth in (12, 24, 48, 200):
        evals, finals = [], []
        for obs, true_hands, _ in positions[:20]:
            mt = team_of(obs.player)
            evals.append(rollout(clone(obs, true_hands), mt, depth,
                                 random.Random(7), rules))
            finals.append(rollout(clone(obs, true_hands), mt, 100000,
                                  random.Random(7), rules))
        corr = (statistics.correlation(evals, finals)
                if len(evals) > 2 and statistics.pstdev(evals) > 0
                else float("nan"))
        print(f"  depth {depth:5d}: corr(eval, final) = {corr:+.3f}  "
              f"sd(eval)={statistics.pstdev(evals):.2f}")

    print("\n== D2: world-to-world noise vs action-to-action gap ==")
    world_sds, action_gaps = [], []
    for obs, _, agent in positions[:12]:
        mt = team_of(obs.player)
        worlds = [agent.bel.sample_current_hands(rng) for _ in range(16)]
        per_action = []
        for a in obs.legal_asks()[:6]:
            vals = []
            for w in worlds:
                st = clone(obs, w)
                try:
                    st.apply(obs.player, a)
                except Exception:
                    continue
                vals.append(rollout(st, mt, 24, random.Random(11), rules))
            if vals:
                per_action.append(statistics.fmean(vals))
                world_sds.append(statistics.pstdev(vals) if len(vals) > 1 else 0)
        if len(per_action) > 1:
            action_gaps.append(max(per_action) - min(per_action))
    ws = statistics.fmean(world_sds) if world_sds else 0
    ag = statistics.fmean(action_gaps) if action_gaps else 1e-9
    print(f"  mean sd across worlds for one action : {ws:.3f}")
    print(f"  mean gap between best/worst action   : {ag:.3f}")
    print(f"  => noise/signal ratio                : {ws/max(1e-9, ag):.2f}")
    print("\n  A ratio above 1 means any search that evaluates different")
    print("  actions on different sampled worlds is ranking luck.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 24)
