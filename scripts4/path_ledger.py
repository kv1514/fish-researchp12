"""Which code path declared it, and was it right.

A duel compares two arms and cannot see a defect they share. Every number in
this project is a paired margin, and a paired margin is blind by construction
to anything both sides do equally badly: the difference cancels it. So the
declaration ledger is a different instrument, not a better version of the same
one. It attributes every declaration in a run to the branch that produced it
and scores that branch on its own.

There are four paths, and `fish4/agent4.py` reaches them in this order:

  exact      the tablebase declaration in the endgame
  voluntary  claim4.voluntary_claim, bar 0.97
  gate       the doomed-ask branch: the ask we were about to make cannot
             land, so declare instead if p_exact >= 0.5
  forced     no legal ask exists at all -> claim4.forced_claim

The paths are read off the agent's own trace (`fish4/trace.py`), which is
asserted RNG-free by `tests4/test_trace.py`, so instrumenting a run cannot
change it. That property is what makes this rideable: the ledger can be taken
on the same games that produce a margin, rather than on a separate population
that might not be the same population.

    py scripts4/path_ledger.py [n_deals] [n_jobs] [--vs v07|self] [--arm k=v,..]
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 6_400_000
AGENT0 = 64_000

#: the trace `why` string each path writes, from fish4/agent4.py
PATHS = {
    "exact": "exact",
    "voluntary": "voluntary",
    "gate": "cannot land",
    "forced": "forced",
}


def _path_of(why: str) -> str:
    for name, needle in PATHS.items():
        if needle in why:
            return name
    return "other"


def _one(args) -> dict:
    deal_seed, kv_even, arm, vs = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.claim4 import ClaimEvaluator

    params = dict(V06_DEPLOYED[1], trace=True, **arm)
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        if ours:
            agents.append(make_agent(("fishbot4", params)))
        elif vs == "v07":
            agents.append(make_agent(("dylan_v07", {})))
        else:
            agents.append(make_agent(("fishbot4", dict(V06_DEPLOYED[1]))))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    # `best_candidate` is where p_team is computed and thrown away; capture the
    # pair the gate actually saw, per seat, rather than recomputing it after.
    real = ClaimEvaluator.best_candidate
    seen = {}

    def spy(self):
        r = real(self)
        if r is not None:
            seen[int(self.me)] = (float(r[0]), float(r[1]))
        return r
    ClaimEvaluator.best_candidate = spy

    rows = []
    try:
        for _ in range(600):
            if st.is_terminal:
                break
            mover = st.turn
            seen.pop(mover, None)
            act = agents[mover].act(Observation.from_state(st, mover))
            tr = agents[mover].last_trace
            ev = st.apply(mover, act)
            if not isinstance(ev, ClaimEvent):
                continue
            # The exact solver writes kind="exact" with no `why`; the other
            # three all write kind="declare" and are told apart by it. A
            # declaration that matches none of the four is counted, not
            # dropped -- an unattributed declaration is a hole in the ledger
            # and the point of the ledger is that sets are conserved.
            kind = (tr or {}).get("kind", "")
            why = "exact" if kind == "exact" else (
                (tr or {}).get("why", "") if kind == "declare" else "")
            pe, pt = seen.get(mover, (None, None))
            rows.append({
                "path": _path_of(why),
                "ours": int(team_of(mover) == our_team),
                "right": int(ev.winner == team_of(mover)),
                # allocation-class: our own team held every card and we still
                # lost it, i.e. the split was wrong rather than the ownership
                "alloc": int(all(team_of(h) == team_of(mover)
                                 for h in ev.revealed)
                             and ev.winner != team_of(mover)),
                "p_exact": pe, "p_team": pt,
                "live": sum(1 for x in st.set_winner if x is None),
                "opp_cards": sum(bin(st.hands[q]).count("1")
                                 for q in range(NUM_PLAYERS)
                                 if team_of(q) != team_of(mover)),
            })
    finally:
        ClaimEvaluator.best_candidate = real

    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    return {"deal": deal_seed, "kv_even": kv_even,
            "margin": 2 * ours_sets - 9, "claims": rows}


def ledger(rows: list[dict], ours_only: bool = True) -> dict:
    """Per-path counts and error rates over a list of played deals."""
    by = defaultdict(lambda: {"n": 0, "wrong": 0, "alloc": 0})
    games = 0
    for r in rows:
        games += 1
        for c in r["claims"]:
            if ours_only and not c["ours"]:
                continue
            b = by[c["path"]]
            b["n"] += 1
            b["wrong"] += 1 - c["right"]
            b["alloc"] += c["alloc"]
    out = {}
    for name in list(PATHS) + ["other"]:
        b = by.get(name)
        if not b:
            continue
        out[name] = {
            "n": b["n"], "per_game": round(b["n"] / games, 4),
            "wrong": b["wrong"],
            "err": round(b["wrong"] / b["n"], 4) if b["n"] else None,
            "alloc": b["alloc"],
        }
    tot_n = sum(v["n"] for v in out.values())
    tot_w = sum(v["wrong"] for v in out.values())
    out["_total"] = {"games": games, "n": tot_n, "wrong": tot_w,
                     "wrong_per_game": round(tot_w / games, 4) if games else None}
    return out


def report(rows: list[dict]) -> dict:
    lg = ledger(rows)
    print(f"\n=== declaration path ledger: {lg['_total']['games']} games, "
          f"our seats only ===")
    print(f"  {'path':<11}{'n':>6}{'/game':>9}{'wrong':>7}{'err':>8}"
          f"{'alloc':>7}")
    for name, v in lg.items():
        if name.startswith("_"):
            continue
        e = "  --  " if v["err"] is None else f"{v['err']:.3f}"
        print(f"  {name:<11}{v['n']:>6}{v['per_game']:>9.3f}"
              f"{v['wrong']:>7}{e:>8}{v['alloc']:>7}")
    t = lg["_total"]
    print(f"  {'TOTAL':<11}{t['n']:>6}{'':>9}{t['wrong']:>7}"
          f"   wrong/game {t['wrong_per_game']}")
    return lg


def main(n_deals=120, n_jobs=0, vs="self", arm=None) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    arm = arm or {}
    todo = [(SEED0 + i, ke, arm, vs)
            for i in range(n_deals) for ke in (True, False)]
    t0 = time.time()
    rows = []
    with Pool(n_jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            rows.append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    out = {"rules": RULES_D, "vs": vs, "arm": arm, "n_deals": n_deals,
           "ledger": report(rows),
           "margin": round(sum(r["margin"] for r in rows) / len(rows), 4)}
    print(f"  margin {out['margin']:+.4f} sets/game")
    dest = ROOT / "results" / f"path_ledger_{vs}.json"
    dest.write_text(json.dumps(out, indent=1))
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    a = [x for x in argv if not x.startswith("--")]
    kw = {}
    for flag in (x for x in argv if x.startswith("--")):
        k, _, v = flag[2:].partition("=")
        if k == "vs":
            kw["vs"] = v
        elif k == "arm":
            kw["arm"] = {q.split("=")[0]: float(q.split("=")[1])
                         for q in v.split(",") if q}
        else:
            raise SystemExit(f"unknown flag --{k}")
    raise SystemExit(main(int(a[0]) if a else 120,
                          int(a[1]) if len(a) > 1 else 0, **kw))
