"""Is exact m = 1 endgame play worth anything in actual play?

``fish4/endgame_ii.py`` replaces the heuristic at m = 1 decisions with
``fish4.exact_ii``'s exact best response. This measures whether that is worth
anything, paired on the deal against the identical configuration with the flag
off, so every source of variance except the policy itself cancels.

THE ARM MATTERS, BECAUSE THE SOLVER'S OPPONENT MODEL IS ONLY SOMETIMES RIGHT

    one    seat 0 alone -- five champions and us, exactly what the solver
           assumes, and the configuration the exploitability bound describes
    team   seats 0/2/4 -- right about the opponents, WRONG about the two
           teammates, who no longer play the champion's move
    all    every seat -- wrong about everyone

FIRING COUNTS ARE PART OF THE RESULT, NOT DIAGNOSTICS
-----------------------------------------------------
The first version of this measured +0.000 +/- 0.000 in the ``one`` arm across
40 paired deals, which reads like a clean null and was nothing of the kind: the
policy had fired twice. A configuration that never triggers produces exactly
that signature. Every arm reports how many m = 1 decisions the flagged seats
faced and how many the solver actually answered, and a run where the policy
never fired refuses to report a differential at all.

    py scripts4/exact_endgame_duel.py [arm] [n_pairs]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState, NULL_TEAM
from fish.observation import Observation
from fish.rules import RuleConfig
import fish4.endgame_ii as endgame_ii
from fish4.registry4 import V03_CHAMPION, make_agent

ON = ("fishbot4", {"exact_endgame": True})
#: The study's budget rather than the shipped one. In the team arm the policy
#: declined 65 of 279 candidates at (12 deals, 50,000 nodes); those are the
#: widest supports, so this asks whether the hardest positions are where the
#: value is or where it runs out.
ON_WIDE = ("fishbot4", {"exact_endgame": True,
                        "exact_endgame_max_support": 24,
                        "exact_endgame_max_nodes": 300_000})
OFF = ("fishbot4", {})
#: Cross-play opponent. The solver models every other seat as the v0.4
#: champion; against this one that model is simply WRONG, which is the point.
#: If the gain survives an opponent the solver was not modelling, the policy is
#: playing the endgame better. If it evaporates, the gain was exploitation of
#: one specific opponent wearing the clothes of an improvement.
OPPONENTS = {"champion": OFF, "v03": V03_CHAMPION}
MIN_RESULT_PAIRS = 100

FIRED = [0]
CANDIDATE = [0]
_orig = endgame_ii.ExactEndgameMixin.exact_ii_action


def _counting(self, obs):
    if getattr(self, "exact_endgame", False):
        if sum(1 for w in obs.set_winner if w is None) == 1:
            CANDIDATE[0] += 1
    a = _orig(self, obs)
    if a is not None:
        FIRED[0] += 1
    return a


endgame_ii.ExactEndgameMixin.exact_ii_action = _counting


def flagged(mode: int, p: int) -> bool:
    return (mode == "all" or (mode == "team" and team_of(p) == 0)
            or (mode == "one" and p == 0))


def play(rules, seed: int, aseed: int, mode, opp=OFF, on=ON):
    agents = [make_agent(on if flagged(mode, p) else
                         (OFF if team_of(p) == 0 else opp))
              for p in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    ar = random.Random(aseed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    for _ in range(600):
        if st.is_terminal:
            break
        p = st.turn
        st.apply(p, agents[p].act(Observation.from_state(st, p)))
    us = sum(1 for w in st.set_winner if w == 0)
    them = sum(1 for w in st.set_winner if w == 1)
    nulls = sum(1 for w in st.set_winner if w == NULL_TEAM)
    unres = sum(1 for w in st.set_winner if w is None)
    return us - them, nulls, unres


def main(mode: str = "team", n_pairs: int = 400, seed_block: int = 0,
         opponent: str = "champion", caps: str = "shipped") -> int:
    """``seed_block`` shifts every deal and agent seed by a disjoint offset.

    A screen whose interval clears zero gets re-tested on fresh seeds before it
    is believed. This project has already had a cell that excluded zero at
    +0.490, returned +0.068 on one fresh block and -0.066 on a second, and was
    noise. Blocks are 10,000 apart so no two overlap."""
    if mode not in ("one", "team", "all"):
        print(f"unknown arm {mode!r}")
        return 1
    if opponent not in OPPONENTS:
        print(f"unknown opponent {opponent!r}; choose from "
              f"{sorted(OPPONENTS)}")
        return 1
    opp = OPPONENTS[opponent]
    on = ON_WIDE if caps == "wide" else ON
    rules = RuleConfig()
    t0 = time.time()
    diffs, na, nb, ua, ub = [], 0, 0, 0, 0
    for g in range(n_pairs):
        base = 92_000 + 10_000 * seed_block
        a = play(rules, base + g, base + 500 + g, mode, opp, on)
        b = play(rules, base + g, base + 500 + g, "none", opp, on)
        diffs.append(a[0] - b[0])
        na += a[1]; nb += b[1]; ua += a[2]; ub += b[2]
        if (g + 1) % 50 == 0:
            print(f"  {g+1}/{n_pairs} pairs, fired {FIRED[0]}/{CANDIDATE[0]}",
                  flush=True)

    n = len(diffs)
    mean = sum(diffs) / n
    var = sum((x - mean) ** 2 for x in diffs) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    moved = sum(1 for x in diffs if x != 0)

    print(f"\narm {mode} vs {opponent}: {n} paired deals in "
          f"{time.time()-t0:.0f}s")
    print(f"  m = 1 decisions the flagged seats faced: {CANDIDATE[0]}")
    print(f"  of those the solver answered:            {FIRED[0]}")
    if FIRED[0] == 0:
        print("\nThe policy never fired. There is no differential to report --")
        print("this run measured the champion against itself.")
        return 1
    print(f"  paired deals whose outcome changed:      {moved}/{n}")
    # The control is the same seats WITHOUT the flag, whoever the opponent is.
    # Calling it "minus champion" was right only while the opponent was the
    # champion, and reads as a comparison against the wrong thing otherwise.
    print(f"\n  set differential, policy minus flag-off control: "
          f"{mean:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  nulls {na} vs {nb};  unresolved half-suits {ua} vs {ub}")
    if ua > ub:
        print("  MORE UNRESOLVED than the control: the policy is declining to")
        print("  finish half-suits, which the harness scores for nobody.")

    smoke = n_pairs < MIN_RESULT_PAIRS
    tag = (f"_b{seed_block}" if seed_block else "")
    tag += "" if opponent == "champion" else f"_vs{opponent}"
    tag += "" if caps == "shipped" else f"_{caps}"
    out = ROOT / "results" / (f"exact_endgame_{mode}{tag}"
                              + ("_smoke" if smoke else "") + ".json")
    out.write_text(json.dumps({
        "arm": mode, "n_pairs": n, "seed_block": seed_block,
        "opponent": opponent, "caps": caps,
        "mean": mean, "ci95": [lo, hi],
        "candidates": CANDIDATE[0], "fired": FIRED[0], "pairs_moved": moved,
        "nulls_policy": na, "nulls_control": nb,
        "unresolved_policy": ua, "unresolved_control": ub,
        "diffs": diffs}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}"
          + ("  -- below the result threshold, do not cite" if smoke else ""))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(a[0] if a else "team",
                          int(a[1]) if len(a) > 1 else 400,
                          int(a[2]) if len(a) > 2 else 0,
                          a[3] if len(a) > 3 else "champion",
                          a[4] if len(a) > 4 else "shipped"))
