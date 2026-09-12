"""The foreign-opponent check of the m=2 correction (prereg/foreign_opponent_m2.md).

Two configurations of this project's engine each play Dylan's FishBot v0.7 on
identical deals and rotations; the statistic is the paired difference of their
margins against that same foreign opponent. Journalled per (deal, rotation,
arm) so the run survives the ten-minute process cap and never replays a game.

    py scripts4/foreign_m2_check.py [n_deals] [first_deal]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35, "n_draws": 480, "w_lookahead": 0.25,
        "lookahead_depth": 3, "lookahead_beam": 4}
ARMS = {
    "on":  dict(BASE, endgame_m=2, endgame_d_info=2.0),
    "off": dict(BASE, endgame_m=0),
}
SEED0 = 331_000
AGENT0 = 3310
JOURNAL = ROOT / "results" / "foreign_m2_journal.jsonl"


def play(deal_seed: int, kv_even: bool, arm: str) -> dict:
    rules = RuleConfig()
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(("fishbot4", dict(ARMS[arm]))) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    fb = sum(getattr(a, "fallbacks", 0) for a in agents)
    kv_team = 0 if kv_even else 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "arm": arm,
            "kv": kv, "dylan": dy, "margin": kv - dy,
            "terminal": st.is_terminal, "fallbacks": fb}


def main(n_deals: int = 250, first: int = 0) -> int:
    done = set()
    rows = []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["deal"], r["kv_even"], r["arm"]))
                rows.append(r)
    print(f"{len(done)} games already journalled", flush=True)

    for i in range(first, n_deals):
        seed = SEED0 + i
        for kv_even in (True, False):
            for arm in ("on", "off"):
                if (seed, kv_even, arm) in done:
                    continue
                t0 = time.time()
                r = play(seed, kv_even, arm)
                r["seconds"] = round(time.time() - t0, 1)
                rows.append(r)
                with JOURNAL.open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
        if (i + 1) % 10 == 0:
            print(f"  deal {i + 1}/{n_deals}", flush=True)

    # ---- analysis, on however much is journalled ---------------------------
    by = {}
    for r in rows:
        by[(r["deal"], r["kv_even"], r["arm"])] = r
    diffs = []
    fbs = 0
    for (deal, ke, arm), r in by.items():
        if arm != "on":
            continue
        o = by.get((deal, ke, "off"))
        if o is None:
            continue
        diffs.append(r["margin"] - o["margin"])
        fbs += r["fallbacks"] + o["fallbacks"]
    n = len(diffs)
    if n < 20:
        print(f"{n} pairs so far; too few to report")
        return 1
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = m - 1.96 * se, m + 1.96 * se
    on = [r["margin"] for r in by.values() if r["arm"] == "on"]
    off = [r["margin"] for r in by.values() if r["arm"] == "off"]
    kv_sets = sum(r["kv"] for r in by.values())
    dy_sets = sum(r["dylan"] for r in by.values())
    print(f"\n{n} paired games vs Dylan's v0.7; bridge fallbacks {fbs}")
    print(f"  KV margin over Dylan, correction ON : "
          f"{sum(on)/len(on):+.3f} sets/game")
    print(f"  KV margin over Dylan, correction OFF: "
          f"{sum(off)/len(off):+.3f} sets/game")
    print(f"  paired effect of the correction: {m:+.4f} "
          f"[{lo:+.4f}, {hi:+.4f}]")
    if hi < 0:
        v = ("reversed", "Outcome 1: the correction REVERSES against a "
             "foreign opponent. Withdraw it from the deployed config.")
    elif lo > 0:
        v = ("transfers", "Outcome 3: it transfers, which is more than "
             "anyone claimed.")
    else:
        v = ("no-reversal", "Outcome 2: no reversal detected at a power "
             "sized for deception-scale flips. The correction stays; its "
             "sibling-measured size remains sibling-measured.")
    print(f"\n  {v[1]}")
    (ROOT / "results" / "foreign_m2_check.json").write_text(json.dumps({
        "n_pairs": n, "effect": m, "ci95": [lo, hi],
        "kv_margin_on": sum(on) / len(on),
        "kv_margin_off": sum(off) / len(off),
        "kv_sets": kv_sets, "dylan_sets": dy_sets,
        "kv_set_share": kv_sets / (kv_sets + dy_sets),
        "bridge_fallbacks": fbs, "verdict": v[0]}, indent=1))
    print("wrote results/foreign_m2_check.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 250,
                          int(a[1]) if len(a) > 1 else 0))
