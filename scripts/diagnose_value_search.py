"""Why does value_search miss positions where NOTHING is hidden?

It scored 127/130 on information-resolved endgames: positions where every
remaining card's location is publicly determined, the correct move is
unambiguous, and its own prior already had it. Those three failures are a
defect, not a preference, so this script finds and dissects them.

For each failure we report: what the agent chose, what was optimal, what the
prior alone would have chosen, and whether the learned evaluation or the
paired significance test is responsible.
"""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.agents import AGENT_REGISTRY
from fish.benchmark_exact import collect_solvable_positions, solve_positions
from fish.cards import card_long_name, half_suit_mask, mask_to_cards, card_name
from fish.engine import Ask, Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

MODEL = str(ROOT / "checkpoints" / "pi_value_v1.pt")


def describe(a):
    if isinstance(a, Ask):
        return f"ASK P{a.target} for {card_long_name(a.card)}"
    if isinstance(a, Claim):
        return f"CLAIM hs{a.half_suit} {tuple(a.assignment)}"
    return str(a)


def main(n_games: int = 200, seed: int = 3):
    rules = RuleConfig()
    pos = collect_solvable_positions(n_games=n_games, seed=seed,
                                     max_live_cards=7)
    solved = [p for p in solve_positions(pos) if p["resolved"]]
    print(f"{len(solved)} information-resolved positions\n")

    rng = random.Random(7)
    failures = []
    for p in solved:
        state, sol = p["state"], p["solution"]
        seat = state.turn
        obs = Observation.from_state(state, seat)
        agent = AGENT_REGISTRY["value_search"](
            model_path=MODEL, n_worlds=16, n_candidates=6)
        agent.begin_game(seat, rules, rng.getrandbits(64))
        try:
            chosen = agent.act(obs)
        except Exception as e:
            print("agent error:", e)
            continue
        if any(chosen == o for o in sol["optimal_actions"]):
            continue

        # reproduce the prior's own top choice, with no search at all
        prior = AGENT_REGISTRY["probabilistic"]()
        prior.begin_game(seat, rules, rng.getrandbits(64))
        prior_choice = prior.act(obs)

        solver = sol["solver"]
        failures.append({
            "state": state, "sol": sol, "seat": seat, "obs": obs,
            "chosen": chosen, "prior": prior_choice,
            "chosen_value": solver.action_value(state, chosen),
            "prior_value": (solver.action_value(state, prior_choice)
                            if prior_choice is not None else None),
        })

    print(f"=== {len(failures)} failures on unambiguous positions ===\n")
    for i, f in enumerate(failures):
        st, sol = f["state"], f["sol"]
        print(f"--- failure {i+1}: P{f['seat']} to move ---")
        for pl in range(6):
            if st.hands[pl]:
                cards = " ".join(card_name(c) for c in mask_to_cards(st.hands[pl]))
                print(f"    P{pl}: {cards}")
        print(f"  exact value          : {sol['value']:+.0f}")
        print(f"  optimal actions      : "
              f"{[describe(a) for a in sol['optimal_actions']][:4]}")
        print(f"  value_search chose   : {describe(f['chosen'])}  "
              f"(value {f['chosen_value']:+.2f})")
        print(f"  prior alone chose    : {describe(f['prior'])}  "
              f"(value {f['prior_value']:+.2f})")
        blame = ("SEARCH overrode a correct prior"
                 if f["prior_value"] is not None
                 and abs(f["prior_value"] - sol["value"]) < 1e-9
                 else "the PRIOR was already wrong")
        print(f"  responsible          : {blame}")
        print()

    n_search_blame = sum(
        1 for f in failures
        if f["prior_value"] is not None
        and abs(f["prior_value"] - f["sol"]["value"]) < 1e-9)
    print(f"search overrode a correct prior in {n_search_blame}/{len(failures)}"
          f" failures")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
