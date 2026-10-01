"""What the transposition memo is worth, measured rather than assumed.

The memo was written on the reasoning that two branches reaching the same
weighted belief set at the same depth have the same value. That is true, and it
is also nearly vacuous once the key includes the path since the root -- which
it must, because leaving the history out is the bug that produced five
impossible negative gains at m = 2.

So the memo went from "sound and useful" to "sound" without anyone checking the
second half. This checks it: same positions, same budget, memo on and memo off,
and both the value and the cost recorded.

TWO THINGS HAVE TO HOLD FOR TURNING IT OFF TO BE A SPEEDUP
----------------------------------------------------------
1. Every position must return the SAME value both ways. A memo is supposed to
   be invisible to the answer; if a value moves, the memo was doing something
   other than remembering, and the speedup is a change of result wearing a
   speedup's clothes. This run refuses to report a timing if any value differs.
2. The time must actually fall. A dict lookup is cheap and it is entirely
   possible that removing it changes nothing measurable, in which case the
   honest report is "no difference" and the memo stays as it is.

    py scripts4/ii_memo_cost.py [n_positions] [max_support]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (ExactII, SolveTimeout, _clone,
                            consistent_deals_multi)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
NODES = 300_000
BACKSTOP = 300.0


def positions(n, lo, hi, n_games=40):
    rules = RuleConfig()
    out = []
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
            if len(live) == 2:
                agents[p].bel.update(obs)
                deals = consistent_deals_multi(obs, agents[p].bel, live,
                                               limit=hi + 1)
                if deals and lo <= len(deals) <= hi:
                    states = []
                    for hands in deals:
                        t = GameState.from_components(
                            rules, list(hands), st.turn, list(st.set_winner))
                        t.history = list(st.history)
                        states.append(t)
                    out.append((rules, live, p, states))
                    if len(out) >= n:
                        return out
            st.apply(p, agents[p].act(obs))
    return out


def run(rules, live, p, states, use_memo):
    w = [1.0 / len(states)] * len(states)
    sv = ExactII(rules, list(live), p, SPEC)
    sv.use_memo = use_memo
    sv.max_nodes = NODES
    sv.deadline = time.monotonic() + BACKSTOP
    t0 = time.perf_counter()
    try:
        v = sv.solve([_clone(s) for s in states], list(w))
    except SolveTimeout:
        v = None
    return v, time.perf_counter() - t0, sv.nodes, len(sv._memo)


def main(n: int = 10, max_support: int = 24) -> int:
    pos = positions(n, 6, max_support)
    print(f"{len(pos)} positions, support 6-{max_support}, {NODES:,} nodes\n")
    rows = []
    for i, (rules, live, p, states) in enumerate(pos):
        # Memo ON first, so any warm-cache advantage from the shared champion
        # oracle falls to the arm being argued AGAINST. A speedup that only
        # shows up when it runs second is an artefact of running second.
        von, ton, non, entries = run(rules, live, p, states, True)
        voff, toff, noff, _ = run(rules, live, p, states, False)
        rows.append({"support": len(states), "v_on": von, "v_off": voff,
                     "t_on": ton, "t_off": toff, "nodes_on": non,
                     "nodes_off": noff, "entries": entries,
                     "hits": (None if von is None else non - entries)})
        same = ("same" if von == voff else "DIFFERENT")
        print(f"  sup {len(states):>3}  on {ton:7.2f}s  off {toff:7.2f}s  "
              f"x{ton/max(toff,1e-9):5.2f}  {non:>7} nodes  "
              f"{(non-entries) if von is not None else 0:>6} hits  {same}",
              flush=True)

    diff = [r for r in rows if r["v_on"] != r["v_off"]]
    if diff:
        print(f"\n{len(diff)} positions returned a DIFFERENT value with the "
              f"memo off. The memo is not value-neutral, which is a bug in "
              f"its own right. Refusing to report a timing.")
        for r in diff[:5]:
            print(f"  support {r['support']}: on {r['v_on']} off {r['v_off']}")
        return 1

    ok = [r for r in rows if r["v_on"] is not None]
    if not ok:
        print("\nEvery position hit the budget both ways; nothing to compare.")
        return 1
    ton = sum(r["t_on"] for r in ok)
    toff = sum(r["t_off"] for r in ok)
    hits = sum(r["hits"] for r in ok)
    look = sum(r["nodes_on"] for r in ok)
    print(f"\n{len(ok)}/{len(rows)} positions solved both ways, all to the "
          f"same value")
    print(f"  memo hits: {hits:,} in {look:,} lookups "
          f"({100.0*hits/max(1,look):.4f}%)")
    print(f"  total time: on {ton:.1f}s, off {toff:.1f}s "
          f"({100.0*(ton-toff)/ton:+.1f}% by removing it)")
    print(f"  peak entries stored: {max(r['entries'] for r in ok):,}")
    out = ROOT / "results" / "ii_memo_cost.json"
    out.write_text(json.dumps({
        "n": len(ok), "node_budget": NODES, "max_support": max_support,
        "hits": hits, "lookups": look,
        "hit_rate": hits / max(1, look),
        "seconds_memo_on": ton, "seconds_memo_off": toff,
        "speedup": ton / toff if toff else None,
        "max_entries": max(r["entries"] for r in ok),
        "values_identical": True, "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 10,
                          int(a[1]) if len(a) > 1 else 24))
