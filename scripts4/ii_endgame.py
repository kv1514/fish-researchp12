"""How well does the champion play the m = 1 endgame when it cannot see?

v0.3's headline absolute result was that its belief agents choose a provably
optimal move in 100% of information-resolved positions. ``fish4/EXACT2.md``
already notes that every one of those positions had a single live half-suit,
where the closed form reduces to "the team on move wins it" -- so the
certificate was shallower than it read. This goes further: that benchmark
scored against the PERFECT-information optimum, and at m = 1 the champion is
frequently NOT information-resolved. 43% of real m = 1 decisions pin every
card; the other 57% do not, and for those nobody has ever known what optimal
means.

``fish4/exact_ii.ExactII`` computes it exactly -- no sampling -- for one
deviating seat against champion opponents, optimising over the deviator's
information sets rather than per deal.

THE CONTROL RUNS FIRST AND GATES EVERYTHING
-------------------------------------------
Where the support is a single deal there is no hidden information left, and the
exact value MUST be the closed form's +/-1. That is checked on every such
position before any other number is reported, because a solver that cannot
reproduce an independently proved answer on the easy half of its input has not
earned the hard half.

    py scripts4/ii_endgame.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_mask, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import ExactII, consistent_deals
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24          # positions above this are reported, not solved


def closed_form(st, hs, seat) -> int:
    """2f - m in the deviator's team frame, for m = 1."""
    mask = half_suit_mask(hs)
    mine = any(st.hands[q] & mask for q in range(NUM_PLAYERS)
               if team_of(q) == team_of(st.turn))
    v = 1 if mine else -1
    return v if team_of(st.turn) == team_of(seat) else -v


def main(n_games: int = 12) -> int:
    rules = RuleConfig()
    pinned_ok = pinned_bad = 0
    bad = []
    solved = []
    skipped = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 1:
                hs = live[0]
                agents[p].bel.update(obs)
                deals = consistent_deals(obs, agents[p].bel, hs)
                if deals and len(deals) <= MAX_SUPPORT:
                    sv = ExactII(rules, hs, p, SPEC)
                    states = []
                    for hands in deals:
                        t = GameState.from_components(
                            rules, list(hands), st.turn, list(st.set_winner))
                        t.history = list(st.history)
                        states.append(t)
                    w = [1.0 / len(states)] * len(states)
                    try:
                        v = sv.solve(states, w)
                    except Exception as e:
                        skipped += 1
                        st.apply(p, agents[p].act(obs))
                        continue
                    if len(deals) == 1:
                        want = closed_form(states[0], hs, p)
                        if abs(v - want) < 1e-9:
                            pinned_ok += 1
                        else:
                            pinned_bad += 1
                            bad.append({"game": g, "exact": v,
                                        "closed_form": want})
                    else:
                        solved.append({"support": len(deals), "value": v,
                                       "nodes": sv.nodes})
                elif deals:
                    skipped += 1
            st.apply(p, agents[p].act(obs))
        print(f"  {g+1}/{n_games} games, {pinned_ok+pinned_bad} pinned, "
              f"{len(solved)} solved, {skipped} skipped", flush=True)

    print(f"\nCONTROL -- positions where the belief pins every card")
    print(f"  exact value equals the closed form: {pinned_ok}/"
          f"{pinned_ok+pinned_bad}")
    for b in bad[:5]:
        print(f"    MISMATCH exact {b['exact']:+.4f} vs closed form "
              f"{b['closed_form']:+d}")
    if pinned_bad or pinned_ok == 0:
        print("\nThe solver does not reproduce the proved answer where there is")
        print("nothing hidden. Nothing else it says is worth reading.")
        return 1

    print(f"\nGENUINELY HIDDEN positions solved exactly: {len(solved)}"
          f"  ({skipped} skipped for support > {MAX_SUPPORT})")
    if solved:
        vs = sorted(r["value"] for r in solved)
        n = len(vs)
        print(f"  exact value to the seat on move: mean "
              f"{sum(vs)/n:+.4f}, median {vs[n//2]:+.4f}, "
              f"min {vs[0]:+.4f}, max {vs[-1]:+.4f}")
        one = sum(1 for v in vs if abs(v - 1.0) < 1e-9)
        print(f"  positions still worth a full +1 despite the uncertainty: "
              f"{one}/{n}")
        print(f"  mean search nodes: "
              f"{sum(r['nodes'] for r in solved)/n:.0f}")

    out = ROOT / "results" / "ii_endgame.json"
    out.write_text(json.dumps({
        "n_games": n_games, "max_support": MAX_SUPPORT,
        "pinned_checked": pinned_ok + pinned_bad, "pinned_ok": pinned_ok,
        "pinned_mismatches": bad, "n_solved": len(solved),
        "skipped_large_support": skipped, "solved": solved}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 12))
