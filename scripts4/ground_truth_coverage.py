"""How much of a real Fish game do we actually have ground truth for?

``results/determinization_gap.json`` established that the exact tables solve the
perfect-information game and overstate the mover's team by **+5.29 sets** on the
positions real play reaches, rising to **+8.18 at a fresh deal**. So a tablebase
value is legitimate only where there is nothing hidden left to determinize over.

``fish4/tablebase4.pinned_state`` enforces exactly that: it returns ``None``
unless the acting seat's belief pins EVERY live card, in which case the
reconstruction equals the true state and the perfect-information value is the
real one. That gate is the boundary of the project's ground truth.

This measures where that boundary falls in practice:

  * what fraction of decisions the tables can legitimately answer
  * how late in the game the first such decision arrives
  * how many half-suits are still live when it does

A note on which question this answers. "Two thirds of m=3 positions solvable"
describes the SOLVER's reach over positions handed to it. This describes the
GAME's reach -- how much of what a player actually faces is inside that
boundary. The two are different numbers and only the second bounds what can be
claimed about Fish.

    py scripts4/ground_truth_coverage.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent
from fish4.tablebase4 import pinned_state

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def main(n_games: int = 30) -> int:
    rules = RuleConfig()
    rows = []
    per_game = []
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=90_000 + g)
        ar = random.Random(91_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))

        step = 0
        first = None
        n_dec = 0
        n_pinned = 0
        while not st.is_terminal and step < 600:
            p = st.turn
            obs = Observation.from_state(st, p)
            bel = agents[p].bel
            bel.update(obs)
            live = sum(1 for w in obs.set_winner if w is None)
            ps = pinned_state(obs, bel)
            ok = ps is not None and 0 < live <= 2
            n_dec += 1
            if ok:
                n_pinned += 1
                if first is None:
                    first = {"step": step, "live": live,
                             "cards_left": sum(obs.hand_counts)}
            rows.append({"live": live, "pinned": bool(ps is not None),
                         "solvable": ok,
                         "cards_left": sum(obs.hand_counts)})
            st.apply(p, agents[p].act(obs))
            step += 1
        per_game.append({"decisions": n_dec, "solvable": n_pinned,
                         "first": first, "total_steps": step})
        print(f"  {g+1}/{n_games} games", flush=True)

    live = np.array([r["live"] for r in rows])
    pin = np.array([r["pinned"] for r in rows])
    sol = np.array([r["solvable"] for r in rows])
    cards = np.array([r["cards_left"] for r in rows])

    print(f"\n{len(rows)} decisions from {n_games} games\n")
    print(f"belief pins every live card:              "
          f"{pin.mean()*100:>6.2f}% of decisions")
    print(f"...and the layer is within the solver:    "
          f"{sol.mean()*100:>6.2f}% of decisions")

    print("\nby half-suits still live:")
    print(f"  {'live':>5}{'decisions':>11}{'pinned':>9}{'solvable':>10}")
    for L in sorted(set(live.tolist()), reverse=True):
        m = live == L
        if m.sum() < 5:
            continue
        print(f"  {L:>5}{int(m.sum()):>11}{pin[m].mean()*100:>8.1f}%"
              f"{sol[m].mean()*100:>9.1f}%")

    firsts = [g["first"] for g in per_game if g["first"]]
    never = sum(1 for g in per_game if not g["first"])
    print(f"\ngames where ground truth is EVER available: "
          f"{len(firsts)}/{n_games}  (never: {never})")
    if firsts:
        fs = np.array([f["step"] for f in firsts])
        fc = np.array([f["cards_left"] for f in firsts])
        tot = np.array([g["total_steps"] for g in per_game if g["first"]])
        print(f"when it first arrives:")
        print(f"  mean step {fs.mean():.1f} of {tot.mean():.1f}  "
              f"= {(fs/tot).mean()*100:.1f}% of the way through")
        print(f"  cards still in hands: {fc.mean():.1f} of 54")
    frac = np.array([g["solvable"] / max(1, g["decisions"]) for g in per_game])
    print(f"\nper game, share of decisions with ground truth: "
          f"{frac.mean()*100:.2f}%  (max {frac.max()*100:.1f}%)")

    out = ROOT / "results" / "ground_truth_coverage.json"
    out.write_text(json.dumps({
        "n_games": n_games, "n_decisions": len(rows),
        "pinned_share": float(pin.mean()), "solvable_share": float(sol.mean()),
        "games_with_any": len(firsts), "games_with_none": never,
        "first_arrival_step_mean": float(np.mean([f["step"] for f in firsts]))
        if firsts else None,
        "first_arrival_cards_left_mean": float(
            np.mean([f["cards_left"] for f in firsts])) if firsts else None,
        "by_live": {int(L): {"n": int((live == L).sum()),
                             "pinned": float(pin[live == L].mean()),
                             "solvable": float(sol[live == L].mean())}
                    for L in sorted(set(live.tolist()))
                    if (live == L).sum() >= 5}}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 30))
