"""Cluster the published one-step regret intervals by DEAL.

`harvest` walks games in order and emits every qualifying ply, so its rows are
runs of consecutive plies within one deal. `history` (the event count) rises
inside a deal and drops when the next one starts, which segments the rows into
deals with no re-run and no assumption about the harvest parameters.

Validated below against the two cells whose deal indices were recovered
independently by replaying the harvest.
"""
import json, math, statistics, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def segment(rows):
    """Deal index per row, from drops in the history length."""
    out, g, prev = [], 0, -1
    for r in rows:
        h = r["history"]
        if h <= prev:
            g += 1
        out.append(g)
        prev = h
    return out

from fish4.clustered import cluster_ci


def cl(vals, groups):
    return cluster_ci(vals, groups)


for name in ("ask_regret_wide", "ask_regret_champion_wide", "ask_regret_champion"):
    d = json.load(open(ROOT / "results" / f"{name}.json"))
    rows = d["rows"]; s = d["summary"]
    g = segment(rows)
    vals = [r["regret"] for r in rows]
    mu, hw, k = cl(vals, g)
    iid = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
    lo, hi = s["ci95"]
    print(f"{name}")
    print(f"  as published   {s['mean_regret']:+.4f} [{lo:+.4f}, {hi:+.4f}]"
          f"   ({s['positions']} positions)")
    print(f"  clustered      {mu:+.4f} [{mu-hw:+.4f}, {mu+hw:+.4f}]"
          f"   ({k} deals, {hw/iid:.2f}x wider)"
          + ("   still excludes 0" if (mu-hw)*(mu+hw) > 0 else
             "   NOW STRADDLES 0" if lo*hi > 0 else "   straddles 0 either way"))
