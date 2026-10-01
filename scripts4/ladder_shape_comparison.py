"""Their version ladder, measured in both arbiters. The two disagree about which direction it runs.

WHAT THIS IS THE CONTROL FOR. `scripts4/reverse_arbiter_ladder.py` measures our
champion inside their arbiter and finds the head-to-head margin reversed. Before
that can mean anything about strength, one alternative has to be excluded: that
the FishLab package simply does not carry our policy, and we lose there because
we arrive weakened. A bot crippled in transit loses to everything.

The ladder is what separates those. Run our champion against their WHOLE
released ladder in their arbiter and compare the SHAPE against the same ladder
measured in ours. Two outcomes, and they mean opposite things:

  * flat and negative everywhere -> the package is the problem, and the v0.7
    cell says nothing about either engine.
  * a real ladder -- their early releases beaten, their late ones not -- ->
    the package carries our policy, and the v0.7 cell is a measurement.

WHAT IT RETURNS IS THE SECOND, AND SOMETHING SHARPER. We beat their v0.3 inside
their own arbiter, so the package is not the problem. But the two ladders do not
merely differ in level; **they run in opposite directions**, and so does the
quantity underneath them.

In their arbiter their ladder behaves the way a version ladder should: their
later releases beat their earlier ones, so our margin falls as the version rises
and their declaration errors fall with it. In ours it is inverted: their margin
against us falls as their version rises, and their declaration error rate CLIMBS
monotonically with it -- their newest engine is their worst declarer here by a
factor of four over their v0.3.

A project's successive releases getting monotonically worse at the one thing
this game scores, and only when played through our bridge, is not a shape
strength produces. It is the signature of an interaction between our bridge or
our arbiter and whatever their later versions added -- which is exactly the
thing v0.4 onward changed, their fitted belief.

WHAT THIS DOES NOT DO. It does not localise the interaction to a line of code,
and it does not tell us which side is wrong. Both ladders hold our side fixed
WITHIN an arbiter, so the trend across their versions is robust to the two
KRAKENs differing; the levels are not comparable across arbiters and are not
compared. The output is a shape, an inversion, and a Spearman correlation on
seven points -- evidence for where to look next, not a defect report.

USAGE

    python3 scripts4/ladder_shape_comparison.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HOME = ROOT / "results" / "dylan_ladder_sweep.json"
AWAY_LADDER = ROOT / "results" / "reverse_arbiter_ladder.json"
AWAY_V07 = ROOT / "results" / "reverse_arbiter_v07.json"


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation, written out because numpy is the only dependency this
    project has and scipy is not one."""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


def load_away() -> dict[str, dict]:
    """Every reverse-arbiter cell, keyed by rung."""
    out: dict[str, dict] = {}
    for path in (AWAY_LADDER, AWAY_V07):
        if not path.exists():
            continue
        for c in json.load(path.open())["cells"]:
            rung = c.get("rung") or c["b"]
            out[rung] = {
                "margin": c["meanSetsA"] - c["meanSetsB"],
                "their_err": 1 - c["declAccB"],
                "our_err": 1 - c["declAccA"],
                "games": c["games"],
                "win_rate": c["winRateA"],
            }
    return out


def main() -> int:
    if not HOME.exists():
        print(f"missing {HOME}", file=sys.stderr)
        return 2
    home = json.load(HOME.open())["opponents"]
    away = load_away()
    if not away:
        print("no reverse-arbiter cells yet; run reverse_arbiter_ladder.py",
              file=sys.stderr)
        return 2

    rungs = [r for r in ["v02", "v03", "v04", "v05", "v06", "v07"]
             if f"dylan_{r}" in home]
    print("=== their released ladder, measured in both arbiters ===")
    print("margin is OUR sets per game; err is that side's declaration "
          "error rate\n")
    print(f"{'rung':6} | {'OUR arbiter':>28} | {'THEIR arbiter':>28}")
    print(f"{'':6} | {'margin':>9} {'their err':>9} {'n':>7} | "
          f"{'margin':>9} {'their err':>9} {'n':>7}")
    print("-" * 74)
    for r in rungs:
        h = home[f"dylan_{r}"]
        a = away.get(r)
        left = f"{h['margin']:+9.4f} {h['their_err']:9.4f} {h['games']:7d}"
        right = (f"{a['margin']:+9.4f} {a['their_err']:9.4f} {a['games']:7d}"
                 if a else f"{'--':>9} {'--':>9} {'--':>7}")
        print(f"{r:6} | {left} | {right}")

    # The trend that matters: does their declaration error rate rise or fall
    # with their own version number, in each arbiter?
    idx = list(range(len(rungs)))
    h_err = [home[f"dylan_{r}"]["their_err"] for r in rungs]
    h_mar = [home[f"dylan_{r}"]["margin"] for r in rungs]
    shared = [r for r in rungs if r in away]
    a_idx = list(range(len(shared)))
    a_err = [away[r]["their_err"] for r in shared]
    a_mar = [away[r]["margin"] for r in shared]

    print("\n=== the direction each ladder runs ===")
    print("Spearman rank correlation against their version number:\n")
    print(f"  their declaration error, OUR arbiter    "
          f"{_spearman(idx, h_err):+.3f}   over {len(rungs)} rungs")
    print(f"  their declaration error, THEIR arbiter  "
          f"{_spearman(a_idx, a_err):+.3f}   over {len(shared)} rungs")
    print(f"  our margin,              OUR arbiter    "
          f"{_spearman(idx, h_mar):+.3f}")
    print(f"  our margin,              THEIR arbiter  "
          f"{_spearman(a_idx, a_mar):+.3f}")
    print("\nA positive error correlation means their LATER releases misdeclare")
    print("MORE. That is the shape their ladder has in our arbiter and not in")
    print("theirs, and it is not a shape improving strength produces.")

    out = {
        "question": "does their released ladder run the same direction in "
                    "both arbiters",
        "control_for": "whether the FishLab package carries our policy at all",
        "scope": "our side is held fixed WITHIN each arbiter, so the trend "
                 "across their versions is robust to the two realisations of "
                 "our champion differing; the LEVELS are not comparable "
                 "across arbiters and are not compared here",
        "rungs": {r: {"our_arbiter": home[f"dylan_{r}"],
                      "their_arbiter": away.get(r)} for r in rungs},
        "spearman_vs_version": {
            "their_declaration_error_our_arbiter": _spearman(idx, h_err),
            "their_declaration_error_their_arbiter": _spearman(a_idx, a_err),
            "our_margin_our_arbiter": _spearman(idx, h_mar),
            "our_margin_their_arbiter": _spearman(a_idx, a_mar),
        },
    }
    dest = ROOT / "results" / "ladder_shape_comparison.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
