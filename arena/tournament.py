"""Round-robin duelling over duplicate deals.

WHY ``independent_seeds=True`` IS NOT OPTIONAL HERE.

``fish4.match.play_matchup`` seeds agent randomness BY SEAT unless told
otherwise. Under that default a policy played against a copy of itself makes
bit-identical decisions in both halves of a duplicate-deal pair, so its
differential is exactly ``(a-b) + (b-a) = 0`` on every deal and the diagonal of
a round-robin is 50.0% *by construction*. A diagonal like that is not the
sanity check it looks like: it would read 50.0% even if the harness were
broken, because no measurement is taking place.

With independent streams the two sides break ties differently, the differential
becomes a real random variable with mean zero, and the diagonal becomes an
actual measurement of the harness's own noise. That is the only version of the
diagonal worth printing, so the arena fixes it on and says so.

Duplicate deals: every deal is played twice with the sides swapped, and the
PAIR is the unit of analysis. That is what makes a few hundred deals resolve
what would otherwise need thousands.
"""

from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.rules import RuleConfig
from fish4.match import play_matchup
from arena.roster import resolve


def duel(a: str, b: str, n_deals: int, base_seed: int, n_jobs: int = 4,
         rules: RuleConfig | None = None) -> dict:
    """One ordered matchup. Returns win rate for ``a`` and the set margin."""
    res = play_matchup(resolve(a), resolve(b), n_deals,
                       rules=rules or RuleConfig(),
                       base_seed=base_seed, n_jobs=n_jobs,
                       agent_seed_base=base_seed ^ 0x5EED,
                       independent_seeds=True)
    # `pair_score` counts a tied PAIR as half, which is the right unit here:
    # a duplicate-deal pair is one observation, not two games.
    lo, hi = res.wilson()
    margin, m_lo, m_hi = res.diff_ci()
    return {"a": a, "b": b, "n_pairs": res.n,
            "win_rate": res.pair_score(),
            "wins": res.x_wins, "ties": res.ties, "losses": res.y_wins,
            "score_ci95": [lo, hi],
            "margin": margin, "margin_ci95": [m_lo, m_hi]}


def run_tournament(field: list[str], n_deals: int = 200, base_seed: int = 90_000,
                   n_jobs: int = 4, include_diagonal: bool = True,
                   progress: bool = True) -> dict:
    """Every ordered pair in ``field``. The diagonal is a harness null."""
    cells, t0 = {}, time.time()
    pairs = [(a, b) for a, b in itertools.product(field, field)
             if include_diagonal or a != b]
    # Each ordered pair gets its own deal block, so no two cells share deals
    # and the matrix has no hidden correlation between its entries.
    for i, (a, b) in enumerate(pairs):
        seed = base_seed + 1000 * i
        cells[f"{a}|{b}"] = duel(a, b, n_deals, seed, n_jobs)
        if progress:
            c = cells[f"{a}|{b}"]
            print(f"  [{i+1:>3}/{len(pairs)}] {a:>18} vs {b:<18} "
                  f"{c['win_rate']:6.1%}  margin {c['margin']:+.3f}  "
                  f"[{time.time()-t0:.0f}s]", file=sys.stderr, flush=True)
    return {"field": field, "n_deals_per_cell": n_deals,
            "base_seed": base_seed, "independent_seeds": True,
            "duplicate_deals": True, "cells": cells,
            "seconds": time.time() - t0}
