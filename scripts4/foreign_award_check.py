"""R2 of prereg/rules_award_baseline.md: the foreign check, rule-matched.

Same design as scripts4/foreign_m2_check.py (the void-era run): the deployed
configuration with the endgame correction on and off, each vs three copies of
Dylan's FishBot v0.7 on identical deals and rotations, paired. Two changes,
both pre-registered: the games are played under the opponent-award baseline
(pinned explicitly, so the results file is self-describing rather than
default-dependent), and every game records how many sets the misdeclaration
rule actually touched (declarations wrong ONLY in their within-team split --
previously voided, now awarded).

Under this rule both engines price a wrong declaration identically, which
removes the one scoring-rule caveat the void-era run carried.

    py scripts4/foreign_award_check.py [n_deals] [first_deal]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35, "n_draws": 480, "w_lookahead": 0.25,
        "lookahead_depth": 3, "lookahead_beam": 4}
ARMS = {
    "on":  dict(BASE, endgame_m=2, endgame_d_info=2.0),
    "off": dict(BASE, endgame_m=0),
}
RULES = RuleConfig(wrong_distribution_outcome="opponent")
SEED0 = 332_000
AGENT0 = 3320
JOURNAL = ROOT / "results" / "foreign_award_journal.jsonl"


def play(deal_seed: int, kv_even: bool, arm: str) -> dict:
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(("fishbot4", dict(ARMS[arm]))) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(RULES, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, AGENT0 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    fb = sum(getattr(a, "fallbacks", 0) for a in agents)
    kv_team = 0 if kv_even else 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
    # The sets the rule change actually touches: wrong only within the team.
    mis_kv = mis_dy = 0
    for ev in st.history:
        if (isinstance(ev, ClaimEvent) and ev.winner is not None
                and ev.winner != team_of(ev.claimer)
                and all(team_of(h) == team_of(ev.claimer)
                        for h in ev.revealed)):
            if team_of(ev.claimer) == kv_team:
                mis_kv += 1
            else:
                mis_dy += 1
    return {"deal": deal_seed, "kv_even": kv_even, "arm": arm,
            "kv": kv, "dylan": dy, "margin": kv - dy,
            "mis_kv": mis_kv, "mis_dylan": mis_dy,
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
    mis_kv = sum(r.get("mis_kv", 0) for r in by.values())
    mis_dy = sum(r.get("mis_dylan", 0) for r in by.values())
    games = len(by)
    print(f"\n{n} paired games vs Dylan's v0.7 under opponent-award; "
          f"bridge fallbacks {fbs}")
    print(f"  KV margin over Dylan, correction ON : "
          f"{sum(on)/len(on):+.3f} sets/game")
    print(f"  KV margin over Dylan, correction OFF: "
          f"{sum(off)/len(off):+.3f} sets/game")
    print(f"  paired effect of the correction: {m:+.4f} "
          f"[{lo:+.4f}, {hi:+.4f}]")
    print(f"  misdeclared (awarded) sets: KV {mis_kv}, Dylan {mis_dy} "
          f"over {games} games")
    if hi < 0:
        v = ("reversed", "Outcome 1: the correction REVERSES against a "
             "foreign opponent under the award rule. Withdraw it from the "
             "deployed config.")
    elif lo > 0:
        v = ("transfers", "Outcome 3: it transfers, which is more than "
             "anyone claimed.")
    else:
        v = ("no-reversal", "Outcome 2: no reversal detected at a power "
             "sized for deception-scale flips. The correction stays.")
    print(f"\n  {v[1]}")
    (ROOT / "results" / "foreign_award_check.json").write_text(json.dumps({
        "rules": RULES.to_dict(), "n_pairs": n, "effect": m,
        "ci95": [lo, hi],
        "kv_margin_on": sum(on) / len(on),
        "kv_margin_off": sum(off) / len(off),
        "kv_sets": kv_sets, "dylan_sets": dy_sets,
        "kv_set_share": kv_sets / (kv_sets + dy_sets),
        "misdeclares_kv": mis_kv, "misdeclares_dylan": mis_dy,
        "games": games,
        "bridge_fallbacks": fbs, "verdict": v[0]}, indent=1))
    print("wrote results/foreign_award_check.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 250,
                          int(a[1]) if len(a) > 1 else 0))
