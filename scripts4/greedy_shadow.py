"""Proposition 1's empirical shadow, measured instead of asserted.

Proposition 1 says a possession-chain search whose transition edits only the
asked card's row is exactly greedy at every depth, so the uncoupled version of
this search is a no-op BY CONSTRUCTION. The paper reports its empirical shadow:
with the coupling off the search's chosen branch was the highest-probability
branch at every multi-branch node, against a handful of non-greedy choices with
it on.

Those counts were in the paper and in no results file. This measures them.

WHAT A "MULTI-BRANCH NODE" IS. A call to ``possession_value`` at depth >= 2
with more than one legal ask in the beam. Its branches are sorted by descending
probability, so index 0 IS the greedy choice and any other index is a departure
from it. ``fish4.lookahead._RECORDER`` reports (depth, n_branches, chosen) from
inside the real search -- not from a reimplementation of it here, which would
measure the copy.

WHAT THIS CANNOT SHOW. The proposition is about greedy equivalence AT A NODE.
The step from there to "the arm plays identically" is a modelling inference, and
setting couple=False does not restore the proposition's hypotheses outright: the
transition still zeroes the asked row and decrements the target's count. So a
zero here is consistent with the proposition and is not a proof of it.

Usage: python scripts4/greedy_shadow.py [n_games] [seed0]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fish4.lookahead as L                                     # noqa: E402
from fish.cards import NUM_PLAYERS                              # noqa: E402
from fish.engine import GameState                               # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from fish4.agent4 import FishBot4                               # noqa: E402
from fish4.askfeat import DecisionContext                       # noqa: E402
from fish4.posterior import Posterior                           # noqa: E402
from fish4.registry4 import V04_STRONGEST                       # noqa: E402

DEPTH = V04_STRONGEST[1]["lookahead_depth"]
BEAM = V04_STRONGEST[1]["lookahead_beam"]


def _tally(couple: bool, positions):
    """Run the real search over the given positions, recording every node."""
    seen = {"nodes": 0, "non_greedy": 0, "no_viable_branch": 0, "by_depth": {}}

    seen["departures"] = []

    def rec(depth, n_branches, chosen, qs):
        # A node where EVERY branch had p <= 0 expands nothing and returns 0
        # with best_i == -1. That is not a decision, so it is not a node at
        # which the search can depart from greedy, and counting it as one
        # reported three phantom departures against a proposition that predicts
        # none. Drop it before anything else.
        if chosen < 0:
            seen["no_viable_branch"] = seen.get("no_viable_branch", 0) + 1
            return
        seen["nodes"] += 1
        d = seen["by_depth"].setdefault(str(depth), {"nodes": 0, "non_greedy": 0})
        d["nodes"] += 1
        # "Greedy" means the highest-probability branch that is actually a
        # CANDIDATE. Branches with p <= 0 are skipped before any continuation
        # is computed, so index 0 is only the greedy choice when it was viable;
        # otherwise the greedy choice is the first viable branch. Testing
        # chosen != 0 without that distinction reports a departure every time
        # the top-ranked branch had zero probability, which is not a departure.
        viable = [j for j, q in enumerate(qs) if q is not None] if qs else []
        greedy = viable[0] if viable else 0
        if chosen != greedy:
            seen["non_greedy"] += 1
            d["non_greedy"] += 1
            # How big is the departure? A gap at the scale of floating-point
            # noise is a tie broken by roundoff, not a decision -- and this
            # project has already shipped one bug that turned out to be exactly
            # that (a filter on a quantity analytically zero). Record the gap so
            # the two can be told apart instead of guessed at.
            q0 = qs[greedy] if qs and qs[greedy] is not None else 0.0
            gap = (qs[chosen] - q0) if qs and qs[chosen] is not None else 0.0
            rel = gap / max(abs(q0), 1e-300)
            seen["departures"].append(
                {"depth": depth, "n_branches": n_branches, "chosen": chosen,
                 "greedy_index": greedy, "q_greedy": q0,
                 "q_chosen": qs[chosen] if qs else None,
                 "abs_gap": gap, "rel_gap": rel})

    L._RECORDER = rec
    try:
        for ctx, asks in positions:
            L.lookahead_bonus(ctx, asks, depth=DEPTH, beam=BEAM, couple=couple)
    finally:
        L._RECORDER = None
    return seen


def _collect(n_games, seed0):
    """Champion-trajectory positions: the states the engine actually reaches."""
    rules = RuleConfig()
    out = []
    for g in range(n_games):
        st = GameState.deal(rules, seed=seed0 + g)
        agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
        for p, a in enumerate(agents):
            a.begin_game(p, rules, 800_000 + 41 * g + p)
        n = 0
        while not st.is_terminal and n < 400:
            seat = st.turn
            obs = Observation.from_state(st, seat)
            asks = obs.legal_asks()
            if len(asks) > 1:
                ag = agents[seat]
                ag.bel.update(obs)
                post = Posterior(ag.bel, ag.rng, n_draws=ag.n_draws,
                                 n_worlds=ag.n_worlds, obs=obs,
                                 gamma=ag.opponent_gamma)
                out.append((DecisionContext(obs, ag.bel, post), asks))
            st.apply(seat, agents[seat].act(obs))
            n += 1
        if (g + 1) % 5 == 0:
            print(f"  {g + 1}/{n_games} games, {len(out)} positions",
                  flush=True)
    return out


def main(argv) -> int:
    n_games = int(argv[0]) if argv else 12
    seed0 = int(argv[1]) if len(argv) > 1 else 91_000

    print("does the uncoupled search ever depart from greedy?\n")
    print(f"depth {DEPTH}, beam {BEAM}, champion trajectories\n")
    positions = _collect(n_games, seed0)
    if not positions:
        print("no multi-ask positions collected")
        return 1
    print(f"\n{len(positions)} decision points with more than one legal ask\n")

    on = _tally(True, positions)
    off = _tally(False, positions)

    print(f"{'coupling':<12}{'multi-branch nodes':>20}{'non-greedy':>13}"
          f"{'share':>9}")
    for name, t in (("on", on), ("off", off)):
        sh = t["non_greedy"] / t["nodes"] if t["nodes"] else 0.0
        print(f"{name:<12}{t['nodes']:>20,}{t['non_greedy']:>13,}"
              f"{100 * sh:>8.3f}%")
    print(f"\n(excluded from both: {on['no_viable_branch']:,} nodes where "
          f"every branch had p <= 0,\n which expand nothing and make no "
          f"choice)")

    for name, t in (("coupling ON", on), ("coupling OFF", off)):
        deps = t.get("departures", [])
        if not deps:
            continue
        rels = sorted(abs(d["rel_gap"]) for d in deps)
        tiny = sum(1 for r in rels if r < 1e-9)
        print(f"\n{name}: {len(deps)} departure(s); relative q gap "
              f"min {rels[0]:.2e}, median {rels[len(rels)//2]:.2e}, "
              f"max {rels[-1]:.2e}")
        print(f"  at or below 1e-9 (a tie broken by roundoff): {tiny} of "
              f"{len(deps)}")

    print()
    if off["non_greedy"] == 0:
        print(f"With the coupling OFF the search chose the "
              f"highest-probability branch at\nall {off['nodes']:,} "
              f"multi-branch nodes, which is what Proposition 1 predicts and "
              f"is\nnow measured rather than asserted. With it ON there are "
              f"{on['non_greedy']:,} departures.")
    else:
        share_off = off["non_greedy"] / off["nodes"]
        share_on = on["non_greedy"] / on["nodes"]
        print(f"With the coupling OFF the search departed from greedy at "
              f"{off['non_greedy']:,} of {off['nodes']:,}\nnodes "
              f"({100 * share_off:.4f}%), against {on['non_greedy']:,} "
              f"({100 * share_on:.3f}%) with it on --- a factor of "
              f"{share_on / share_off:.0f}.")
        print()
        print("Proposition 1 predicts exactly zero, and this is not zero. It is "
              "also not a\ncontradiction, because couple=False does not "
              "restore the proposition's\nhypotheses: the transition still "
              "decrements the target's count, so a player\nreduced to zero "
              "cards drops out of legal_asks and the available branch SET\n"
              "changes downstream. That is a channel the exchange argument does "
              "not cover,\nand it is the module's own stated caveat rather "
              "than a new one.")
        print()
        print("So the empirical shadow is a near-null with a mechanism, not a "
              "null. Quoting\nit as 'N of N' overstates it, and the departures "
              "are real rather than\nfloating-point ties -- their relative q "
              "gaps are printed above.")

    out = {"n_games": n_games, "depth": DEPTH, "beam": BEAM,
           "n_positions": len(positions),
           "coupled": on, "uncoupled": off}
    dest = ROOT / "results" / "greedy_shadow.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
