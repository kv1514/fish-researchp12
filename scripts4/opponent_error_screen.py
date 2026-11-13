"""Which opponents misdeclare at all? A screen, not a registration.

`scripts4/margin_identity.py` shows that the two large channels of the margin
are both about the opponents: how many half-suits they declare and how often
they are wrong when they do. Against `dylan_v07` -- the standard opponent, and
the only one every figure in this project is measured against -- the second
number is 21.4%, against the champion's own 3.2%.

Before asking whether signalling's effect on that rate GENERALISES, there has
to be somewhere for it to generalise to. An opponent that never misdeclares has
no error rate to raise, and a null against one says nothing about the
mechanism. This screen prices the baseline for each policy in the registry so
that a generality registration can name opponents with room in them, chosen
before any arm is played rather than after a null.

Descriptive. It fixes no threshold, decides no ship, and is not a registration.

    py scripts4/opponent_error_screen.py [n_deals] [n_jobs] [out.json]
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.clustered import cluster_ci, fmt                    # noqa: E402
from scripts4 import signal_vs_defer as run                    # noqa: E402

#: Every honest policy in the registry. `oracle_gated` reads hidden state and
#: is refused by `signal_vs_defer._opponent`; it is left out here by name too,
#: so a reader does not have to know that to trust the table.
OPPONENTS = ("dylan_v07", "heuristic", "probabilistic", "memory", "tuned",
             "search", "ev_claim", "value_search", "paired_search", "self")

#: Its own seed base, barred from every registration's, because a screen that
#: shares deals with the run it motivates has scored that run on its own
#: pilot.
SEED0 = 12_500_000
AGENT0 = 125_000
N_DEALS = 60


def _one(args):
    vs, deal_seed, kv_even = args
    run.VS, run.AGENT0 = vs, AGENT0
    r = run._play(deal_seed, kv_even, {})
    return {"vs": vs, "deal": deal_seed,
            "margin": r["margin"], "declares": r["opp_declares"],
            "wrong": r["opp_wrong"], "terminal": r["terminal"],
            "ours": sum(n for n, _ in r["paths"].values()),
            "ours_wrong": sum(w for _, w in r["paths"].values())}


def report(rows, n_deals: int) -> dict:
    out: dict = {"what": "baseline declaration accuracy of each opponent",
                 "descriptive": True, "seed_deal": SEED0,
                 "seed_agent": AGENT0, "n_deals": n_deals,
                 "opponents": {}}
    print(f"\n=== who misdeclares, and how often   "
          f"({n_deals} deals x 2 parities each)")
    print(f"  {'opponent':<15}{'margin':>19}{'their decl':>12}"
          f"{'their err':>11}{'our err':>10}{'headroom':>10}")
    by = {}
    for r in rows:
        by.setdefault(r["vs"], []).append(r)
    for vs in OPPONENTS:
        rs = by.get(vs)
        if not rs:
            continue
        deals = [r["deal"] for r in rs]
        m = cluster_ci([r["margin"] for r in rs], deals)
        d = sum(r["declares"] for r in rs)
        w = sum(r["wrong"] for r in rs)
        od = sum(r["ours"] for r in rs)
        ow = sum(r["ours_wrong"] for r in rs)
        err = w / d if d else None
        #: what the THEIRS channel could give if they never got one right
        head = 2 * (d - w) / len(rs)
        out["opponents"][vs] = {
            "margin": m[0], "margin_half_width": m[1],
            "their_declares_per_game": d / len(rs),
            "their_err": err, "our_err": (ow / od) if od else None,
            "theirs_headroom": head, "games": len(rs),
            "unfinished": sum(1 for r in rs if not r["terminal"])}
        e = "  --  " if err is None else f"{err:.4f}"
        print(f"  {vs:<15}{fmt(*m):>19}{d / len(rs):>12.3f}{e:>11}"
              f"{(ow / od if od else 0):>10.4f}{head:>10.3f}")
    print(f"\n  An opponent with a `their err` near zero has no error rate to "
          f"raise.\n  A generality test against one measures the floor, not "
          f"the mechanism.")
    return out


def main(n_deals: int = N_DEALS, n_jobs: int | None = None,
         out: str | None = None) -> int:
    jobs = [(vs, SEED0 + i, bool(k)) for vs in OPPONENTS
            for i in range(n_deals) for k in (0, 1)]
    t0 = time.time()
    with Pool(n_jobs or max(1, (os.cpu_count() or 4) - 1)) as pool:
        rows = pool.map(_one, jobs, chunksize=1)
    payload = report(rows, n_deals)
    payload["minutes"] = round((time.time() - t0) / 60, 1)
    path = Path(out) if out else ROOT / "results" / "opponent_error_screen.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}  ({payload['minutes']} min)")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else N_DEALS,
                          int(a[1]) if len(a) > 1 else None,
                          a[2] if len(a) > 2 else None))
