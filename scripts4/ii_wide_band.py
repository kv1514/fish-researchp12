"""Solve m = 2 positions in the band the main study skips, and test the trend.

``scripts4/ii_support_bias.py`` shows the exact gain rising with belief support
and declines to extrapolate: the fit covers supports 2-24 and the unsolved
positions run to 60,480 deals. This stops extrapolating and measures, in the
band immediately above the cap where the cost is still payable.

The positions are the SAME ones ``scripts4/ii_endgame.py`` skipped -- same
seeds, same game lines -- so the two sets are directly comparable and the only
difference is which side of the support cap a position fell.

WHAT WOULD MAKE THE TREND FALSE
-------------------------------
If the gain in this band comes back at or below the narrow band's, the rise
measured over supports 2-24 does not continue, and the claim that the headline
figures are lower bounds is weakened to "over the range we can see". That is a
real possible outcome: a position with a hundred candidate deals may be one
where nothing the deviator does helps much, so exact play and the heuristic
converge rather than diverge.

    py scripts4/ii_wide_band.py [n_games] [lo] [hi]
"""

from __future__ import annotations

import hashlib
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
#: Far above the study's 300,000. These positions are the point of the run, so
#: they get a budget that reflects that rather than the one tuned for sweeping
#: a whole layer.
WIDE_NODES = 3_000_000
#: Wall-clock backstop. Deliberately short relative to the node budget: the
#: first band position tried spent thirty minutes and 2.5M nodes without
#: finishing, and at that rate the run is a day long. A position that cannot
#: reach 3,000,000 nodes inside this is out of reach for the purpose either
#: way, and failing fast is what makes the band measurable at all.
BACKSTOP = 420.0
JOURNAL = ROOT / "results" / "ii_wide_band_journal.jsonl"


def _fp() -> str:
    # The rules are part of what the stored numbers MEAN: a row computed
    # under one misdeclaration rule must never be resumed into a run playing
    # the other, so the rule set is in the hash.
    return hashlib.sha256(
        (ROOT / "fish4" / "exact_ii.py").read_bytes()
        + repr(RuleConfig()).encode()).hexdigest()[:12]


def main(n_games: int = 60, lo: int = 25, hi: int = 120) -> int:
    rules = RuleConfig()
    fp = _fp()
    done = set()
    rows = []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp:
                    done.add((r["game"], r["index"]))
                    if r["kind"] == "solved":
                        rows.append(r)
    print(f"  solver {fp}; {len(done)} positions already attempted")

    for g in range(n_games):
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
            if len(live) == 2:
                agents[p].bel.update(obs)
                deals = consistent_deals_multi(obs, agents[p].bel, live,
                                               limit=hi + 1)
                if deals and lo <= len(deals) <= hi:
                    idx += 1
                    if (g, idx) not in done:
                        states = []
                        for hands in deals:
                            t = GameState.from_components(
                                rules, list(hands), st.turn,
                                list(st.set_winner))
                            t.history = list(st.history)
                            states.append(t)
                        w = [1.0 / len(states)] * len(states)
                        sv = ExactII(rules, list(live), p, SPEC)
                        sv.max_nodes = WIDE_NODES
                        sv.deadline = time.monotonic() + BACKSTOP
                        t0 = time.time()
                        try:
                            v = sv.solve([_clone(s) for s in states], list(w))
                            cv = sv.champion_value(
                                [_clone(s) for s in states], list(w))
                            rec = {"game": g, "index": idx, "solver": fp,
                                   "kind": "solved", "support": len(deals),
                                   "value": v, "champion": cv,
                                   "gain": v - cv, "nodes": sv.nodes,
                                   "seconds": time.time() - t0}
                            rows.append(rec)
                            print(f"    game {g} support {len(deals):>4}  "
                                  f"gain {v-cv:+.4f}  {sv.nodes:>9} nodes  "
                                  f"{time.time()-t0:6.0f}s", flush=True)
                        except SolveTimeout:
                            # WHICH limit bit. Reporting both as "over budget"
                            # hides the difference between a position needing
                            # more search and one that is merely slow -- the
                            # first is a statement about Fish, the second about
                            # this machine.
                            why = ("nodes" if sv.nodes >= WIDE_NODES
                                   else "wall clock")
                            rec = {"game": g, "index": idx, "solver": fp,
                                   "kind": "over_budget", "limit": why,
                                   "support": len(deals), "nodes": sv.nodes,
                                   "seconds": time.time() - t0}
                            print(f"    game {g} support {len(deals):>4}  "
                                  f"hit the {why} limit after {sv.nodes} "
                                  f"nodes, {time.time()-t0:.0f}s", flush=True)
                        with JOURNAL.open("a") as fh:
                            fh.write(json.dumps(rec) + "\n")
            st.apply(p, agents[p].act(obs))

    fails = []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp and r["kind"] == "over_budget":
                    fails.append(r)
    if fails:
        byn = sum(1 for r in fails if r.get("limit") == "nodes")
        print(f"\n{len(fails)} positions unsolved: {byn} exhausted "
              f"{WIDE_NODES:,} nodes, {len(fails)-byn} ran out of wall clock")
    if not rows:
        print("\nNothing solved in the band. That is itself the finding: the")
        print("support range immediately above the study's cap is not")
        print("reachable at this budget, so the coverage limit is a hard one")
        print("and the support-bias caveat cannot be settled by more compute")
        print("of this kind.")
        return 1
    gains = sorted(r["gain"] for r in rows)
    n = len(gains)
    mean = sum(gains) / n
    var = sum((x - mean) ** 2 for x in gains) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5
    neg = sum(1 for x in gains if x < -1e-9)
    sups = sorted(r["support"] for r in rows)
    print(f"\n{n} positions solved with support in [{lo}, {hi}]")
    print(f"  support: min {sups[0]}, median {sups[n//2]}, max {sups[-1]}")
    print(f"  exact gain: mean {mean:+.4f}  95% CI "
          f"[{mean-1.96*se:+.4f}, {mean+1.96*se:+.4f}]")
    print(f"  median {gains[n//2]:+.4f}, max {gains[-1]:+.4f}")
    if neg:
        print(f"\n  {neg} NEGATIVE gains, which cannot happen. Refusing to "
              f"write a result.")
        return 1

    narrow = ROOT / "results" / "ii_endgame_m2.json"
    if narrow.exists():
        d = json.loads(narrow.read_text())
        print(f"\n  the study's band (support <= 24): "
              f"{d['mean_gain']:+.4f} over {d['n_solved']} positions")
        print(f"  this band  (support {lo}-{hi}): {mean:+.4f} over {n}")
        if mean > d["mean_gain"]:
            print(f"  The rise continues above the cap.")
        else:
            print(f"  The rise does NOT continue: the trend measured over "
                  f"supports 2-24\n  does not extend here, and the 'lower "
                  f"bound' reading weakens to\n  'over the range we can see'.")
    out = ROOT / "results" / "ii_wide_band.json"
    out.write_text(json.dumps({
        "lo": lo, "hi": hi, "n_solved": n, "mean_gain": mean,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "median_support": sups[n // 2], "max_support": sups[-1],
        "node_budget": WIDE_NODES, "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          int(a[1]) if len(a) > 1 else 25,
                          int(a[2]) if len(a) > 2 else 120))
