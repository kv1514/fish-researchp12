"""Why does signalling ADD an error in 52 games and avoid one in 72?

prereg/deadline_signalling.md measured the deadline-priced signalling protocol
at +0.122 [+0.029, +0.215] sets/game, declined it against a +0.15 bar, and named
where the ceiling is:

    "Its ceiling is that it adds errors almost as often as it avoids them --
     52 games against 72. That is the number to attack if this mechanism is
     ever revisited, not the gate."

This attacks that number, and it needs no new play: results/signal_gate_journal
.jsonl already carries a per-game, per-arm declaration path ledger for all
1,000 games -- `paths` maps each path to [declarations, wrong].

THE RECONCILIATION FIRST, because a different baseline gives a different split
and the wrong one would look like a new finding. C against A_shipped gives
52 added / 72 avoided / 876 unchanged, exactly as registered. C against
B_incumbent gives 22 / 28 / 950. This uses A_shipped, which is what the
registration used.

Usage: python scripts4/signal_error_paths.py [out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

JOURNAL = ROOT / "results" / "signal_gate_journal.jsonl"
BASE, ARM = "A_shipped", "C_measured"
PATHS = ("voluntary", "gate", "forced", "exact")


def wrong(a) -> int:
    return sum(v[1] for v in a["paths"].values())


def count(a, p) -> int:
    return a["paths"].get(p, [0, 0])[0]


def main(out: str | None = None) -> int:
    rows = [json.loads(l) for l in JOURNAL.open()]
    added = [r for r in rows if wrong(r[ARM]) - wrong(r[BASE]) > 0]
    avoid = [r for r in rows if wrong(r[ARM]) - wrong(r[BASE]) < 0]

    def shift(grp, p):
        return sum(count(r[ARM], p) - count(r[BASE], p) for r in grp) / len(grp)

    rates = {}
    for p in PATHS:
        n = sum(count(r[ARM], p) for r in rows)
        w = sum(r[ARM]["paths"].get(p, [0, 0])[1] for r in rows)
        rates[p] = {"declarations": n, "wrong": w,
                    "rate": (w / n) if n else None}

    print(f"\n{len(rows)} games, {ARM} against {BASE}")
    print(f"  errors ADDED {len(added)}   AVOIDED {len(avoid)}   "
          f"unchanged {len(rows) - len(added) - len(avoid)}   "
          "(registered: 52 / 72 / 876)\n")
    print("  WHERE THE DECLARATIONS MOVE, per game")
    print("  %-16s %10s %9s %9s %9s" % ("group", *PATHS))
    for name, grp in (("errors ADDED", added), ("errors AVOIDED", avoid)):
        print("  %-16s %+10.3f %+9.3f %+9.3f %+9.3f   (n=%d)"
              % (name, *[shift(grp, p) for p in PATHS], len(grp)))
    print("\n  ERROR RATE BY PATH, arm C over all games")
    for p in PATHS:
        r = rates[p]
        print("    %-10s %5d declarations, %4d wrong = %5.1f%%"
              % (p, r["declarations"], r["wrong"], 100 * (r["rate"] or 0)))

    print("""
  THE ANSWER. Signalling drains the GATE path in both groups, and by about the
  same amount (-0.635 added, -0.847 avoided). What separates them is entirely
  where those declarations land instead:

    avoided  ->  VOLUNTARY (+0.139) and exact (+0.111): the split got placed,
                 so the declaration is made knowingly.  Voluntary is 0.1% wrong.
    added    ->  FORCED (+1.327) while voluntary FALLS (-0.788): the split did
                 not get placed, the spent turn pushed the seat past the
                 deadline.  Forced is 46.3% wrong.

  So the protocol is not choosing badly between targets or thresholds. It is
  spending a turn on information that arrives in time in 72 games and too late
  in 52, and the price of "too late" is a 0.1%-wrong declaration becoming a
  46.3%-wrong one.""")

    payload = {
        "what": ("Why signalling adds an error in 52 games and avoids one in "
                 "72 -- the number prereg/deadline_signalling.md names as the "
                 "ceiling to attack."),
        "source": "results/signal_gate_journal.jsonl",
        "baseline": BASE, "arm": ARM, "n_games": len(rows),
        "added": len(added), "avoided": len(avoid),
        "path_shift_per_game": {
            "added": {p: shift(added, p) for p in PATHS},
            "avoided": {p: shift(avoid, p) for p in PATHS}},
        "path_error_rate": rates,
    }
    path = Path(out) if out else ROOT / "results" / "signal_error_paths.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(a[0] if a else None))
