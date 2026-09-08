"""What did the stateless bridge cost them? Same deals, both bridges, paired.

WHAT IS ALREADY ESTABLISHED. `scripts4/shim_statefulness_parity.py` showed that
our stateless bridge and their arbiter's incremental play are not the same
agent from their v0.4 onward, and are exactly the same agent before it:

    v0.2   0 of 323 decisions differ        scripted baseline
    v0.3   0 of 338                         scripted baseline
    v0.4   81 of 415   19.5%                the fitted belief arrives
    v0.5   137 of 336  40.8%
    v0.6   36 of 292   12.3%
    v0.7   84 of 296   28.4%

That is a fact about decisions. It is not yet a number of sets, and a
divergence is not automatically a handicap -- a different move is not
necessarily a worse one. This prices it.

THE DESIGN. Every deal is played twice on identical cards, identical seat
assignment and identical agent seeds, with our champion unchanged in both arms.
The only thing that differs is whether their engine keeps its state between
decisions:

    arm A   fish4/dylan_v07.py             stateless, one process per decision
    arm B   fish4/dylan_v07_persistent.py  one process per seat per deal

Both arms use the same frozen spec, the same card map, the same event encoding
and the same legality checking -- arm B inherits all of it and overrides only
the transport -- so a paired difference is the statelessness and nothing else.
The statistic is our margin in A minus our margin in B, per pair, with the pair
as the independent unit.

READING IT. Positive means we scored MORE against the stateless bridge than
against the persistent one, i.e. the stateless bridge was costing them and the
published margin is inflated by that much. Negative means the reverse. Zero
means the divergent decisions were not, on balance, worse ones, and the
published margin survives its bridge.

WHAT IT IS NOT. Not a corrected cross-engine headline. This contrast runs
entirely inside our arbiter and our dialect, so it prices ONE of the several
things that separate our arbiter's answer from theirs. Their arbiter's own
answer is `results/reverse_arbiter_v07.json`, and the gap between the two is
not assumed to be this one term.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                      # noqa: E402
from fish.observation import Observation               # noqa: E402
from fish.rules import RuleConfig                      # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 8_100_000
AGENT0 = 81_000
MAX_ACTIONS = 600

#: This project's standing threshold for a difference worth acting on.
SHIP_BAR = 0.15


def _one(args) -> dict:
    """One deal, played under both bridges with everything else held fixed."""
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07_persistent import DylanV07Persistent

    rules = RuleConfig(**RULES_D)
    out = {"deal": deal_seed, "kv_even": kv_even}
    for arm in ("stateless", "persistent"):
        agents = []
        for p in range(6):
            kv = (p % 2 == 0) == kv_even
            if kv:
                agents.append(make_agent(KRAKEN_V1))
            elif arm == "stateless":
                agents.append(make_agent(("dylan_v07", {})))
            else:
                agents.append(DylanV07Persistent())
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        t0 = time.time()
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            st.apply(st.turn, agents[st.turn].act(
                Observation.from_state(st, st.turn)))
        kv_team = 0 if kv_even else 1
        ours = sum(1 for w in st.set_winner if w == kv_team)
        theirs = sum(1 for w in st.set_winner if w == 1 - kv_team)
        # Their wrong declarations, counted from the record rather than
        # inferred: a claim whose winner is not the claimer's own team.
        from fish.engine import ClaimEvent
        their_wrong = sum(
            1 for e in st.history
            if isinstance(e, ClaimEvent)
            and (e.claimer & 1) != kv_team % 2
            and e.winner != (e.claimer & 1))
        their_decl = sum(1 for e in st.history if isinstance(e, ClaimEvent)
                         and (e.claimer & 1) != kv_team % 2)
        out[arm] = {
            "ours": ours, "theirs": theirs, "margin": ours - theirs,
            "terminal": st.is_terminal,
            "their_declarations": their_decl,
            "their_wrong_declarations": their_wrong,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "seconds": round(time.time() - t0, 2),
        }
        for a in agents:
            close = getattr(a, "_close", None)
            if close:
                close()
    out["cost_to_them"] = out["stateless"]["margin"] - out["persistent"]["margin"]
    return out


def report(rows: list[dict]) -> dict:
    n = len(rows)
    d = [r["cost_to_them"] for r in rows]
    mean = sum(d) / n
    sd = statistics.stdev(d) if n > 1 else 0.0
    se = sd / (n ** 0.5) if n else 0.0
    lo, hi = mean - 1.96 * se, mean + 1.96 * se

    def agg(arm, key):
        return sum(r[arm][key] for r in rows) / n

    out = {
        "question": "what the stateless bridge cost their engine, in sets",
        "design": "paired: identical deal, seats and agent seeds in both arms; "
                  "our champion unchanged; only their bridge differs",
        "scope": "measured inside OUR arbiter and OUR dialect, so it prices one "
                 "of the several things separating our arbiter's answer from "
                 "theirs, not the whole gap",
        "pairs": n,
        "margin_stateless": agg("stateless", "margin"),
        "margin_persistent": agg("persistent", "margin"),
        "cost_to_them": mean,
        "ci95": [lo, hi],
        "sd": sd,
        "ship_bar": SHIP_BAR,
        "exceeds_ship_bar": abs(mean) >= SHIP_BAR and lo * hi > 0,
        "their_wrong_declarations_stateless":
            agg("stateless", "their_wrong_declarations"),
        "their_wrong_declarations_persistent":
            agg("persistent", "their_wrong_declarations"),
        "their_declarations_stateless": agg("stateless", "their_declarations"),
        "their_declarations_persistent": agg("persistent", "their_declarations"),
        "fallbacks": sum(r[a]["fallbacks"] for r in rows
                         for a in ("stateless", "persistent")),
        "unfinished": sum(1 for r in rows for a in ("stateless", "persistent")
                          if not r[a]["terminal"]),
    }

    print(f"\n=== what the stateless bridge cost their engine ===")
    print(f"{n:,} deals, each played under both bridges on the same cards\n")
    print(f"  our margin, stateless bridge    {out['margin_stateless']:+.4f} sets/game")
    print(f"  our margin, persistent bridge   {out['margin_persistent']:+.4f}")
    print(f"  the bridge was worth            {mean:+.4f} "
          f"[{lo:+.4f}, {hi:+.4f}] to US")
    print(f"  ship bar                        +/-{SHIP_BAR}")
    print(f"\n  their wrong declarations/game   "
          f"{out['their_wrong_declarations_stateless']:.4f} stateless   "
          f"{out['their_wrong_declarations_persistent']:.4f} persistent")
    print(f"  their declarations/game         "
          f"{out['their_declarations_stateless']:.4f} stateless   "
          f"{out['their_declarations_persistent']:.4f} persistent")
    print(f"\n  fallbacks {out['fallbacks']}   unfinished {out['unfinished']}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=120)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "bridge_statefulness_price.json"))
    a = ap.parse_args(argv)

    jobs = a.jobs or max(1, (os.cpu_count() or 2))
    todo = [(a.seed + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games ({a.deals} deals x 2 seatings x 2 arms) "
          f"on {jobs} workers", flush=True)

    rows = []
    t0 = time.time()
    with Pool(jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.append(r)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(todo)} pairs, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)

    if len(rows) < 30:
        print(f"{len(rows)} pairs; too few to report", file=sys.stderr)
        return 1
    out = report(rows)
    out["seconds"] = round(time.time() - t0, 1)
    out["per_pair"] = rows
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
