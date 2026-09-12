"""What is the better ask, and how does it differ from the champion's?

The bound runs established that beating the champion in the endgame is almost
always ONE move -- on 88% of exactly solved positions a single deviation
followed by ordinary champion play attains the exact optimum -- and that the
better move is an ASK on 131 of 154 improvable m = 1 positions and 128 of 138
at m = 2. So the defect is in ask selection, not in claim timing.

This asks what separates the two asks. It needs no new search: the journals
already record the better action, and the champion's action is one agent call.
The comparison is therefore cheap enough to run over every position both layers
produced, which is what makes a per-position PAIRED test possible -- the same
belief, the same hand, two asks, so nothing about the position can explain the
difference between them.

THE FEATURE
-----------
For an ask (target t, card c) under belief {(deal, w)}:

    p_hit = sum of w over deals in which t holds c

That is the probability the ask succeeds and the asker keeps the turn. It is
the one number the champion's objective is most directly built around, so if
the exact optimum systematically disagrees about it, the disagreement is
diagnosable rather than merely present.

WHAT WOULD MAKE THIS A DEAD END
-------------------------------
If the better ask's p_hit matches the champion's, ask safety is not the axis
the champion is wrong on, and the difference lies somewhere this does not look
-- which card, which target, what it reveals. That is a real possible outcome
and it is the one this reports rather than hunting for a feature that splits.

    py scripts4/ii_one_move.py [layer] [n_games]
"""

from __future__ import annotations

import json
import re
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, _champion_action, _clone,
                            consistent_deals_multi)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
JOURNALS = {1: ROOT / "results" / "ii_bound_m1_journal.jsonl",
            2: ROOT / "results" / "ii_bound_journal.jsonl"}
ASK = re.compile(r"Ask\(target=(\d+), card=(\d+)\)")


def _load(path):
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    keep = max(set(r["solver"] for r in rows),
               key=lambda f: sum(1 for r in rows if r["solver"] == f))
    return {(r["game"], r["index"]): r
            for r in rows if r["solver"] == keep}


def _p_hit(states, weights, target, card):
    tot = 0.0
    for s, w in zip(states, weights):
        if s.hands[target] >> card & 1:
            tot += w
    return tot


def main(layer: int = 1, n_games: int = 200) -> int:
    rules = RuleConfig()
    want = _load(JOURNALS[layer])
    print(f"layer m = {layer}; {len(want)} journalled positions")
    pairs = []
    for g in range(n_games):
        if not any(k[0] == g for k in want):
            continue
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
            if len(live) == layer:
                idx += 1
                rec = want.get((g, idx))
                if rec is not None and rec["support"] > 1 \
                        and rec["gain_lower"] > 1e-9:
                    agents[p].bel.update(obs)
                    deals = consistent_deals_multi(obs, agents[p].bel, live,
                                                   limit=rec["support"] + 1)
                    if len(deals) == rec["support"]:
                        states = []
                        for hands in deals:
                            t = GameState.from_components(
                                rules, list(hands), st.turn,
                                list(st.set_winner))
                            t.history = list(st.history)
                            states.append(t)
                        w = [1.0 / len(states)] * len(states)
                        champ = _champion_action(SPEC, rules, p, states[0])
                        mc = ASK.match(repr(champ) if champ else "")
                        mb = ASK.match(rec["best_one_ply"] or "")
                        if mc and mb:
                            pairs.append({
                                "game": g, "index": idx,
                                "support": rec["support"],
                                "gain": rec["gain_lower"],
                                "champ_p": _p_hit(states, w, int(mc.group(1)),
                                                  int(mc.group(2))),
                                "best_p": _p_hit(states, w, int(mb.group(1)),
                                                 int(mb.group(2))),
                                "same_target": mc.group(1) == mb.group(1),
                                "same_hs": (int(mc.group(2))
                                            // CARDS_PER_HALF_SUIT
                                            == int(mb.group(2))
                                            // CARDS_PER_HALF_SUIT)})
            st.apply(p, agents[p].act(obs))

    if not pairs:
        print("no improvable ask-vs-ask pairs found")
        return 1
    # Pairs where the two asks are literally the same move cannot show a
    # difference and are not evidence of one. They are counted, not averaged in.
    diff = [q for q in pairs if abs(q["champ_p"] - q["best_p"]) > 1e-12
            or not q["same_target"] or not q["same_hs"]]
    n = len(diff)
    d = [q["best_p"] - q["champ_p"] for q in diff]
    m = sum(d) / n
    var = sum((x - m) ** 2 for x in d) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5
    print(f"\n{len(pairs)} positions where the champion's ask is beaten by "
          f"another ask; {n} where the two differ")
    print(f"  champion's ask succeeds with p = "
          f"{sum(q['champ_p'] for q in diff)/n:.4f}")
    print(f"  the better ask with       p = "
          f"{sum(q['best_p'] for q in diff)/n:.4f}")
    print(f"  paired difference {m:+.4f} "
          f"(95% CI [{m-1.96*se:+.4f}, {m+1.96*se:+.4f}]), "
          f"t = {m/se:+.2f}" if se > 0 else "  zero variance")
    riskier = sum(1 for x in d if x < -1e-9)
    safer = sum(1 for x in d if x > 1e-9)
    print(f"  the better ask is RISKIER on {riskier}, SAFER on {safer}, "
          f"equally likely on {n - riskier - safer}")
    certain = sum(1 for q in diff if q["champ_p"] > 1 - 1e-9)
    print(f"  the champion's ask was a CERTAIN hit on {certain} of {n}, and "
          f"was still beaten")
    st_ = sum(1 for q in diff if q["same_target"])
    hs_ = sum(1 for q in diff if q["same_hs"])
    print(f"  same target as the champion's: {st_}/{n}; "
          f"same half-suit: {hs_}/{n}")
    if abs(m) < 2 * se:
        print("\n  Ask safety is NOT the axis. The better ask succeeds about "
              "as often as the\n  champion's, so whatever the champion is "
              "getting wrong is not how likely\n  the ask is to land, and "
              "looking harder at this feature will not find it.")
    out = ROOT / "results" / f"ii_one_move_m{layer}.json"
    out.write_text(json.dumps({
        "layer": layer, "n_pairs": len(pairs), "n_differing": n,
        "champ_p_mean": sum(q["champ_p"] for q in diff) / n,
        "best_p_mean": sum(q["best_p"] for q in diff) / n,
        "paired_diff": m, "paired_se": se,
        "better_is_riskier": riskier, "better_is_safer": safer,
        "champion_certain_and_beaten": certain,
        "same_target": st_, "same_half_suit": hs_,
        "pairs": diff}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 1,
                          int(a[1]) if len(a) > 1 else 200))
