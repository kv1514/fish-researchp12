"""python -m arena [n_deals] [n_jobs] [out.json]

A SMALL RUN MAY NOT SILENTLY REPLACE A LARGE ONE.

``results/arena.json`` used to be the destination for every run that did not
name one, so ``python -m arena 4 4`` -- the two-minute smoke run the README
offers to anyone trying the package out -- overwrote a 40-deal matrix with four
deals of noise. Nothing said so; the file kept its name, its shape and its
field, and only ``n_deals_per_cell`` changed. That is the defect
``scripts4.journal.result_for`` was written to end after it happened three
times on 2026-08-28, and it reached this package by a route that rule does not
cover: the arena reads no journal, so its populations are told apart by SIZE.

So the canonical name is earned. A run writes ``arena.json`` only when it is at
least as large as the matrix already there; a smaller one lands beside it under
its own size and says which file it wrote. An explicit third argument always
wins -- naming the destination is the one case where the caller has said what
they mean.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arena.roster import default_field
from arena.tournament import run_tournament
from arena.report import render_matrix, render_margins, render_field


def canonical_dest(canonical: Path, n_deals: int) -> Path:
    """``canonical`` if this run is at least as big as what is there already.

    Otherwise a sibling named for this run's size. Deliberately compares only
    the deal count: two runs of the same size over the same seeded field are
    the same population and may replace one another, and a bigger one is
    strictly better evidence than what it replaces.
    """
    try:
        prior = json.loads(canonical.read_text())
        have = int(prior.get("n_deals_per_cell", 0))
    except (OSError, ValueError, TypeError):
        return canonical
    if n_deals >= have:
        return canonical
    return canonical.with_name(f"{canonical.stem}_{n_deals}deal{canonical.suffix}")


def main(argv) -> int:
    n_deals = int(argv[0]) if argv else 200
    n_jobs = int(argv[1]) if len(argv) > 1 else 4
    dest = (Path(argv[2]) if len(argv) > 2
            else canonical_dest(ROOT / "results" / "arena.json", n_deals))
    field = default_field()
    print(f"KRAKEN arena | {len(field)} policies | {n_deals} duplicate deals "
          f"per ordered matchup\n", file=sys.stderr)
    t = run_tournament(field, n_deals=n_deals, n_jobs=n_jobs)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(t, indent=1))
    print()
    print(render_field(field))
    print()
    print(render_matrix(t))
    print(render_margins(t))
    print(f"\nWrote {dest} ({t['seconds']:.0f}s)")
    canonical = ROOT / "results" / "arena.json"
    if dest != canonical and len(argv) <= 2:
        print(f"NOT {canonical.name}: it holds a larger run, and {n_deals} "
              f"deals per cell must not replace it. Re-run at that size or "
              f"larger to claim the name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
