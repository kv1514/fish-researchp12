"""The large-scale head-to-head: KV's FishBot v0.6 vs Dylan's FishBot v0.7.

Parallel across every core, journalled per game so a run survives the
process cap and never replays a game it already has.

ON SAMPLE SIZE, HONESTLY. A game costs about 0.8 s (the bridge spawns one
process per decision of theirs), and this box has four cores, so a million
games is roughly 55 hours of continuous compute -- not available here. It
would also not change the answer. The standard error of the margin falls as
1/sqrt(n):

      1,000 games   +/- 0.13 sets      already decisive
     10,000 games   +/- 0.04 sets
    100,000 games   +/- 0.013 sets
  1,000,000 games   +/- 0.004 sets

The question "who wins" was settled at the first rung; every rung after it
buys decimal places. What more games DO buy is resolution on rarer things --
how often the underdog wins a game, the shape of the margin distribution,
whether the edge is uniform across half-suits -- so this script reports
those rather than just a mean.

    py scripts4/mega_match.py [n_deals] [n_jobs]

Each deal is played twice, once with our seats even and once odd, so
neither engine gets the opening move more often.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 900_000
AGENT0 = 9000
JOURNAL = ROOT / "results" / "mega_match_journal.jsonl"


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    kv_team = 0 if kv_even else 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
    ask = {"kv": [0, 0], "dy": [0, 0]}
    dec = {"kv": [0, 0], "dy": [0, 0]}
    mis = {"kv": 0, "dy": 0}
    for ev in st.history:
        if isinstance(ev, AskEvent):
            s = "kv" if team_of(ev.asker) == kv_team else "dy"
            ask[s][1] += 1
            ask[s][0] += int(ev.success)
        elif isinstance(ev, ClaimEvent):
            s = "kv" if team_of(ev.claimer) == kv_team else "dy"
            dec[s][1] += 1
            if ev.winner == team_of(ev.claimer):
                dec[s][0] += 1
            elif all(team_of(h) == team_of(ev.claimer) for h in ev.revealed):
                mis[s] += 1
    return {"deal": deal_seed, "kv_even": kv_even, "kv": kv, "dylan": dy,
            "margin": kv - dy, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "ask": ask, "dec": dec, "mis": mis}


def report(rows) -> dict:
    by = {(r["deal"], r["kv_even"]): r for r in rows}
    g = list(by.values())
    n = len(g)
    m = [x["margin"] for x in g]
    mean = sum(m) / n
    var = sum((x - mean) ** 2 for x in m) / (n - 1)
    sd = var ** 0.5
    se = (var / n) ** 0.5
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    wins = sum(1 for x in m if x > 0)
    losses = sum(1 for x in m if x < 0)
    ties = n - wins - losses
    wr = wins / n
    wse = (wr * (1 - wr) / n) ** 0.5
    kv_sets = sum(x["kv"] for x in g)
    dy_sets = sum(x["dylan"] for x in g)

    def r2(key, side, i=0):
        num = sum(x[key][side][i] for x in g)
        den = sum(x[key][side][1] for x in g)
        return (num / den if den else 0.0), den

    ak, nak = r2("ask", "kv")
    ad, nad = r2("ask", "dy")
    dk, ndk = r2("dec", "kv")
    dd, ndd = r2("dec", "dy")
    dist = Counter(m)
    print(f"\n=== KV's FishBot v0.6  vs  Dylan's FishBot v0.7 ===")
    print(f"{n:,} games   bridge fallbacks {sum(x['fallbacks'] for x in g)}   "
          f"unfinished {sum(1 for x in g if not x['terminal'])}")
    print(f"  margin        {mean:+.4f} sets/game  "
          f"95% CI [{lo:+.4f}, {hi:+.4f}]   sd {sd:.2f}")
    print(f"  sets          KV {kv_sets:,} - {dy_sets:,} Dylan   "
          f"({100*kv_sets/(kv_sets+dy_sets):.2f}% of decided)")
    print(f"  games won     {100*wr:.2f}% +/- {100*1.96*wse:.2f}   "
          f"({wins:,}W / {ties:,}T / {losses:,}L)")
    print(f"  ask hit       KV {100*ak:.2f}% (n={nak:,})   "
          f"Dylan {100*ad:.2f}% (n={nad:,})")
    print(f"  declare right KV {100*dk:.2f}% (n={ndk:,})   "
          f"Dylan {100*dd:.2f}% (n={ndd:,})")
    print(f"  misdeclares   KV {sum(x['mis']['kv'] for x in g):,}   "
          f"Dylan {sum(x['mis']['dy'] for x in g):,}")
    print("  margin distribution (sets, ours minus theirs):")
    for k in sorted(dist):
        bar = "#" * max(1, round(60 * dist[k] / n))
        print(f"    {k:+3d}  {100*dist[k]/n:5.2f}%  {bar}")
    return {"rules": RULES_D, "n_games": n, "margin": mean, "ci95": [lo, hi],
            "sd": sd, "kv_sets": kv_sets, "dylan_sets": dy_sets,
            "kv_set_share": kv_sets / (kv_sets + dy_sets),
            "wins": wins, "ties": ties, "losses": losses, "win_rate": wr,
            "win_rate_ci95": [wr - 1.96 * wse, wr + 1.96 * wse],
            "ask_hit_kv": ak, "ask_hit_dylan": ad,
            "declare_right_kv": dk, "declare_right_dylan": dd,
            "misdeclares_kv": sum(x["mis"]["kv"] for x in g),
            "misdeclares_dylan": sum(x["mis"]["dy"] for x in g),
            "bridge_fallbacks": sum(x["fallbacks"] for x in g),
            "margin_distribution": {str(k): dist[k] for k in sorted(dist)}}


def main(n_deals: int = 2000, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    done, rows = set(), []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["deal"], r["kv_even"]))
                rows.append(r)
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)
            if (SEED0 + i, ke) not in done]
    print(f"{len(done):,} games journalled, {len(todo):,} to play "
          f"on {n_jobs} workers", flush=True)
    t0 = time.time()
    if todo:
        with Pool(n_jobs) as pool, JOURNAL.open("a") as fh:
            for i, r in enumerate(pool.imap_unordered(_one, todo,
                                                      chunksize=4)):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                if (i + 1) % 200 == 0:
                    el = time.time() - t0
                    print(f"  {i+1:,}/{len(todo):,}  "
                          f"{(i+1)/el:.1f} games/s  "
                          f"{el/60:.1f} min", flush=True)
                    fh.flush()
    if len(rows) < 100:
        print(f"{len(rows)} games; too few to report")
        return 1
    out = report(rows)
    (ROOT / "results" / "mega_match.json").write_text(json.dumps(out, indent=1))
    print("wrote results/mega_match.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 2000,
                          int(a[1]) if len(a) > 1 else 0))
