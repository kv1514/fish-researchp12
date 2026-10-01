"""Which gate produced each of OUR declarations, and how often it was wrong.

Our margin against v0.7 is declaration accuracy (96.5% against 78.9%), so the
0.176 wrong declarations per game are the only channel through which a
half-suit our team already owns can be lost --- an opposing team that holds no
card of a half-suit can never ask into it (``fish/engine.py:200``) and a
declaration it makes on one awards the set to us (``fish/engine.py:322``).
This asks WHICH of the three gates in ``fish4/agent4.py::act`` produced each
declaration, at what confidence, and with how much information still to come.

Traced, not re-derived: ``trace=True`` reads arrays the policy already
computed and is asserted bit-identical by ``tests4/test_trace.py``.

    py scripts4/declare_triggers.py [n_deals] [n_jobs] [out.jsonl]
"""
from __future__ import annotations

import json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import half_suit_cards, team_of
from fish.engine import ClaimEvent, GameState, PassEvent
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 900_000
AGENT0 = 9000
NHS = 9


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    name, kw = V06_DEPLOYED
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent((name, dict(kw, trace=True))) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    kv_team = 0 if kv_even else 1
    decls, passes = [], []
    #: asks we made whose top-ranked candidate could not possibly land -- the
    #: doomed-ask gate fired and found nothing worth declaring
    doomed_asks = 0
    ply = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        kv_side = team_of(mover) == kv_team
        counts = list(st.hand_counts())
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = getattr(agents[mover], "last_trace", None) if kv_side else None
        ev = st.apply(mover, act)
        if isinstance(ev, ClaimEvent) and kv_side:
            ct = team_of(ev.claimer)
            opp_cards = sum(counts[o] for o in range(6) if team_of(o) != ct)
            team_holds_all = all(team_of(h) == ct for h in ev.revealed)
            decls.append({
                "ply": ply, "hs": ev.half_suit, "claimer": ev.claimer,
                "ok": int(ev.winner == ct),
                "own_class": int(team_holds_all),
                "why": (tr or {}).get("why"),
                "kind": (tr or {}).get("kind"),
                "solver": (tr or {}).get("solver"),
                "conf": (tr or {}).get("confidence"),
                "opp_cards": opp_cards,
                "my_cards": counts[ev.claimer],
                "live": sum(1 for x in st.set_winner if x is None) + 1,
                "counts": counts,
            })
        elif kv_side and tr and tr.get("kind") == "ask":
            ranked = tr.get("ranked") or []
            if ranked and ranked[0].get("p_hit", 1.0) <= 0.0:
                doomed_asks += 1
        if isinstance(ev, PassEvent) and kv_side:
            opts = [t for t in range(6) if team_of(t) == team_of(ev.player)
                    and t != ev.player and counts[t]]
            passes.append({"ply": ply, "player": ev.player,
                           "to": ev.teammate, "opts": opts,
                           "counts": counts,
                           "opp_cards": sum(counts[o] for o in range(6)
                                            if team_of(o) != team_of(ev.player)),
                           "live": sum(1 for x in st.set_winner if x is None)})
        ply += 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "margin": 2 * kv - NHS,
            "plies": ply, "decls": decls, "passes": passes,
            "doomed_asks": doomed_asks}


def main(n_deals=200, n_jobs=0, out="results/declare_triggers.jsonl"):
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)]
    t0 = time.time()
    with Pool(n_jobs) as pool, Path(out).open("w") as fh:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            fh.write(json.dumps(r) + "\n")
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 200,
                          int(a[1]) if len(a) > 1 else 0,
                          a[2] if len(a) > 2 else "results/declare_triggers.jsonl"))
