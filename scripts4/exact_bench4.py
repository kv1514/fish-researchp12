"""Absolute strength: how often does a policy choose a provably optimal move?

Every other metric in this project is relative. This one is not: in positions
small enough to solve exactly there is a right answer, and disagreeing with it
is a defect rather than a preference.

Run against ``results/exact_positions_v2.json`` (988 positions harvested from
260 real games by four different generator policies, so the corpus is not shaped
by one agent's habits), which reaches TWO unresolved half-suits. v0.3's
benchmark could only reach one, and the exact solver's own analysis showed why
that mattered: at one live half-suit the perfect-information value has the
closed form ``sign(mover's team) x (2f - m)`` with ``f`` the number of live
half-suits the moving team has a foothold in, so a one-half-suit benchmark is
largely certifying agreement with "the team on move wins the half-suit". The
two-half-suit slice is the one with teeth.

Three regimes are reported, because they mean different things.

``resolved``
    Every live card's location is already publicly determined, so hidden
    information is not a factor and the perfect-information optimum IS the
    optimum. A strong agent should reach 100%; a shortfall is a bug.
``uncertain``
    Genuine hidden information remains. Agreement is a comparative signal, and
    100% is not the target.
``progress-optimal``
    The stricter criterion. Fish's state graph is cyclic, and in a cyclic game
    Bellman-optimality is not optimality: an action can preserve the value while
    walking a cycle forever and banking nothing. In 28.6% of decided
    two-half-suit states some value-preserving action makes no progress, so
    agreement with the merely value-preserving set overstates play.

Usage:  py scripts4/exact_bench4.py [max_positions]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.observation import Observation
from fish4.exact2_corpus import action_from_dict, state_from_record
from fish4.registry4 import REGISTRY, make_agent

AGENTS = [
    ("random", ("random", {})),
    ("heuristic", ("heuristic", {})),
    ("memory", ("memory", {})),
    ("probabilistic", ("probabilistic", {})),
    ("v0.3 champion", ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})),
    ("v0.4 no-gamma", ("fishbot4", {})),
    ("v0.4 champion", ("fishbot4", {"opponent_gamma": 0.35})),
    ("v0.4 no-tablebase", ("fishbot4", {"opponent_gamma": 0.35,
                                        "use_tablebase": False})),
]


def bench(label, spec, records, seed=0):
    rng = random.Random(seed)
    r = {"label": label, "spec": list(spec), "errors": 0}
    for key in ("res", "unc"):
        for suffix in ("_total", "_opt", "_prog"):
            r[key + suffix] = 0
    for key in ("m1", "m2"):
        r[key + "_total"] = 0
        r[key + "_prog"] = 0
    for rec in records:
        state = state_from_record(rec)
        seat = state.turn
        agent = make_agent(spec)
        agent.begin_game(seat, state.rules, rng.getrandbits(64))
        obs = Observation.from_state(state, seat)
        try:
            action = agent.act(obs)
        except Exception as exc:
            r["errors"] += 1
            if r["errors"] <= 3:
                print(f"    [{label}] {type(exc).__name__}: {exc}",
                      file=sys.stderr)
            continue
        opt = {repr(action_from_dict(a)) for a in rec["optimal_actions"]}
        prog = {repr(action_from_dict(a))
                for a in rec["progress_optimal_actions"]}
        is_opt = repr(action) in opt
        is_prog = repr(action) in prog
        key = "res" if rec["information_resolved"] else "unc"
        r[key + "_total"] += 1
        r[key + "_opt"] += int(is_opt)
        r[key + "_prog"] += int(is_prog)
        mk = "m1" if rec["n_live_half_suits"] == 1 else "m2"
        r[mk + "_total"] += 1
        r[mk + "_prog"] += int(is_prog)
    return r


def main(max_positions=None):
    path = ROOT / "results" / "exact_positions_v2.json"
    data = json.loads(path.read_text())
    records = data["positions"]
    if max_positions:
        records = records[:max_positions]
    n_res = sum(1 for r in records if r["information_resolved"])
    print(f"{len(records)} positions, {n_res} information-resolved, "
          f"{sum(1 for r in records if r['n_live_half_suits'] == 2)} "
          f"two-half-suit\n", file=sys.stderr)

    rows = []
    t0 = time.time()
    print(f"{'agent':20s} {'resolved':>18s} {'uncertain':>18s} "
          f"{'m=1 prog':>10s} {'m=2 prog':>10s} {'err':>4s}")
    for label, spec in AGENTS:
        if spec[0] not in REGISTRY:
            continue
        r = bench(label, spec, records)
        rows.append(r)
        rr = r["res_prog"] / max(1, r["res_total"])
        ur = r["unc_prog"] / max(1, r["unc_total"])
        m1 = r["m1_prog"] / max(1, r["m1_total"])
        m2 = r["m2_prog"] / max(1, r["m2_total"])
        print(f"{label:20s} {rr:8.1%} ({r['res_prog']:3d}/{r['res_total']:3d}) "
              f"{ur:8.1%} ({r['unc_prog']:3d}/{r['unc_total']:3d}) "
              f"{m1:10.1%} {m2:10.1%} {r['errors']:4d}", flush=True)
    out = ROOT / "results" / "exact_agreement_v04.json"
    out.write_text(json.dumps({"n_positions": len(records),
                               "n_resolved": n_res, "rows": rows}, indent=2))
    print(f"\n({time.time()-t0:.0f}s)  Saved {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
