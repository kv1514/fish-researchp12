"""P47: the licensed arm G at confirm scale, on a fresh seed block.

Registered in `prereg/kraken_v12_g_confirm.md`, which fixes the arm, the
seeds, the bar and the predicted outcome before any game; this file only
executes it. P46's Stage 1 licensed and screened G (`opponent_gamma = 0.7`,
their seats and ours) at 600 pairings on 10,700,000 and it cleared neither
interval; P46 allowed its own confirm only for a clearing arm, so this is a
new registration, never pooled with that screen.

The design is `scripts4/p46_screen.py`'s, imported rather than copied:
`_one` plays champion and candidate against SESTINA on the same deal on both
parities plus candidate-versus-champion self-play on the same deal, and
`report` scores every difference within a deal with a 1.96-SE interval and a
second interval clustered by deal. One arm, these constants, 600 deals.

It refuses to run until `results/p46_screen_G.json` is on disk, because the
registration exists only as the follow-up to that file.

Usage:
  python scripts4/p47_confirm.py [--deals 600] [--jobs 3]
         [--out results/p47_confirm.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.p46_screen import ARMS, _one, report   # noqa: E402

#: Deal seed base: 600 deals x 2 parities. Barred from every block on the
#: record (the registration lists them); in particular not P46's unrun
#: 10,800,000.
SEED0 = 11_100_000
#: Agent seed base: seat p in deal d seeds at AGENT0 + 13 d + p.
AGENT0 = 111_000
#: The one arm. Its spec is P46's, read from P46's table so that the two
#: files cannot drift apart.
ARM = "G_gamma_07"
PREREG = "prereg/kraken_v12_g_confirm.md"
#: P46's Stage 1 reading of G. This run does not start until it exists.
STAGE1_RESULT = "results/p46_screen_G.json"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=600)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--require-stage1", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="refuse to run until P46's Stage 1 reading of G "
                         "exists (--no-require-stage1 is for tests only)")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)

    stage1 = ROOT / STAGE1_RESULT
    if a.require_stage1 and not stage1.exists():
        print(f"refusing to run: P46's Stage 1 reading of G is not on disk "
              f"({stage1} is absent). P47 is the follow-up to that file; "
              f"--no-require-stage1 is for tests only.", file=sys.stderr)
        return 2
    if ARMS[ARM] != {"opponent_gamma": 0.7}:
        print(f"{ARM} is not the licensed cell (0.7, 0.7)", file=sys.stderr)
        return 2

    todo = [(SEED0 + i, ke, ARM, AGENT0)
            for i in range(a.deals) for ke in (True, False)]
    print(f"P47 confirm: 1 arm x {a.deals} deals x 2 parities = "
          f"{len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {SEED0:,}, agent base {AGENT0:,}", flush=True)

    rows = []
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    rows.sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report({ARM: rows}, "confirm")
    out["registration"] = "P47"
    out["prereg"] = PREREG
    out["seconds"] = round(time.time() - t0, 1)
    out["seed_base"] = SEED0
    out["agent0"] = AGENT0
    out["deals"] = a.deals
    out["stage1_present"] = stage1.exists()
    out["per_pair"] = {ARM: rows}
    dest = a.out or str(ROOT / "results" / "p47_confirm.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
