"""The headline match: KRAKEN v1.0 against Dylan's FishBot v0.7.

Not another screen -- this is the number the README and the paper quote, so
it is run on its own fresh seeds, journalled, and reported with the detail
a reader needs to believe it: the margin with a confidence interval, how
the sets split, who misdeclares, and WHERE the margin comes from (which
half-suits, and whether it is asks or declarations).

Both engines play their native misdeclaration rule (a misdeclared set goes
to the opponents). Seats alternate so neither side owns the opening move
more often than the other.

    py scripts4/v06_vs_v07_confirm.py [n_deals]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import HALF_SUIT_NAMES, team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")
SEED0 = 550_000
AGENT0 = 5500
JOURNAL = ROOT / "results" / "v06_vs_v07_journal.jsonl"


def play(deal_seed: int, kv_even: bool) -> dict:
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(RULES, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, AGENT0 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    kv_team = 0 if kv_even else 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)

    asks = {"kv": [0, 0], "dy": [0, 0]}         # [hits, total]
    decl = {"kv": [0, 0], "dy": [0, 0]}         # [correct, total]
    by_hs = {}
    for ev in st.history:
        side = "kv" if (team_of(getattr(ev, "asker", getattr(
            ev, "claimer", 0))) == kv_team) else "dy"
        if isinstance(ev, AskEvent):
            asks[side][1] += 1
            asks[side][0] += int(ev.success)
        elif isinstance(ev, ClaimEvent):
            decl[side][1] += 1
            decl[side][0] += int(ev.winner == team_of(ev.claimer))
    for hs, w in enumerate(st.set_winner):
        if w is not None:
            by_hs[hs] = 1 if w == kv_team else -1
    return {"deal": deal_seed, "kv_even": kv_even, "kv": kv, "dylan": dy,
            "margin": kv - dy, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "asks": asks, "decl": decl, "by_hs": by_hs}


def main(n_deals: int = 250) -> int:
    done, rows = set(), []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["deal"], r["kv_even"]))
                rows.append(r)
    print(f"{len(done)} games already journalled", flush=True)
    for i in range(n_deals):
        seed = SEED0 + i
        for kv_even in (True, False):
            if (seed, kv_even) in done:
                continue
            t0 = time.time()
            r = play(seed, kv_even)
            r["seconds"] = round(time.time() - t0, 1)
            rows.append(r)
            with JOURNAL.open("a") as fh:
                fh.write(json.dumps(r) + "\n")
        if (i + 1) % 25 == 0:
            print(f"  deal {i + 1}/{n_deals}", flush=True)

    by = {(r["deal"], r["kv_even"]): r for r in rows}
    games = list(by.values())
    n = len(games)
    if n < 40:
        print(f"{n} games so far; too few to report")
        return 1
    m = [g["margin"] for g in games]
    mean = sum(m) / n
    var = sum((x - mean) ** 2 for x in m) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    kv_sets = sum(g["kv"] for g in games)
    dy_sets = sum(g["dylan"] for g in games)
    wins = sum(1 for g in games if g["margin"] > 0)
    losses = sum(1 for g in games if g["margin"] < 0)
    ties = n - wins - losses
    fb = sum(g["fallbacks"] for g in games)

    def rate(key, side, idx=0):
        num = sum(g[key][side][idx] for g in games)
        den = sum(g[key][side][1] for g in games)
        return (num / den if den else 0.0), den

    ask_kv, nak = rate("asks", "kv")
    ask_dy, nad = rate("asks", "dy")
    dec_kv, ndk = rate("decl", "kv")
    dec_dy, ndd = rate("decl", "dy")
    hs_edge = {}
    for g in games:
        for hs, v in g["by_hs"].items():
            hs_edge[int(hs)] = hs_edge.get(int(hs), 0) + v

    print(f"\n=== KRAKEN v1.0  vs  Dylan's FishBot v0.7 ===")
    print(f"{n} games, {fb} bridge fallbacks, "
          f"{sum(1 for g in games if not g['terminal'])} unfinished")
    print(f"  margin      {mean:+.3f} sets/game  [{lo:+.3f}, {hi:+.3f}]")
    print(f"  sets        KV {kv_sets} - {dy_sets} Dylan "
          f"({100*kv_sets/(kv_sets+dy_sets):.1f}% of decided)")
    print(f"  games       {wins}W / {ties}T / {losses}L "
          f"({100*wins/n:.1f}% won)")
    print(f"  ask hit     KV {100*ask_kv:.1f}% (n={nak})   "
          f"Dylan {100*ask_dy:.1f}% (n={nad})")
    print(f"  declare ok  KV {100*dec_kv:.1f}% (n={ndk})   "
          f"Dylan {100*dec_dy:.1f}% (n={ndd})")
    print("  net sets by half-suit (positive = ours):")
    for hs in sorted(hs_edge, key=lambda h: -hs_edge[h]):
        print(f"      {HALF_SUIT_NAMES[hs]:<16} {hs_edge[hs]:+d}")

    (ROOT / "results" / "v06_vs_v07.json").write_text(json.dumps({
        "rules": RULES.to_dict(), "spec": V06_DEPLOYED[1], "n_games": n,
        "margin": mean, "ci95": [lo, hi], "kv_sets": kv_sets,
        "dylan_sets": dy_sets, "kv_set_share": kv_sets / (kv_sets + dy_sets),
        "wins": wins, "ties": ties, "losses": losses,
        "win_rate": wins / n, "bridge_fallbacks": fb,
        "ask_hit_kv": ask_kv, "ask_hit_dylan": ask_dy,
        "declare_ok_kv": dec_kv, "declare_ok_dylan": dec_dy,
        "net_sets_by_half_suit": {HALF_SUIT_NAMES[h]: v
                                  for h, v in sorted(hs_edge.items())},
    }, indent=1))
    print("wrote results/v06_vs_v07.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 250))
