"""python -m arena [n_deals] [n_jobs] [out.json]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arena.roster import default_field
from arena.tournament import run_tournament
from arena.report import render_matrix, render_margins, render_field


def main(argv) -> int:
    n_deals = int(argv[0]) if argv else 200
    n_jobs = int(argv[1]) if len(argv) > 1 else 4
    dest = Path(argv[2]) if len(argv) > 2 else ROOT / "results" / "arena.json"
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
