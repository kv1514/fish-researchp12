"""What did the history-less memo key actually do to the m = 1 aggregate?

The corrected solver does not solve the same set of positions as the broken one
-- it visits roughly eighty times more nodes, so the hard positions now exceed
the budget -- and comparing two means over two different sets of positions
measures the difference in the sets as much as the difference in the solver.

So this compares them where they are MATCHED. The game line is driven by the
champion agents and is not affected by solving, so both runs encounter exactly
the same positions in exactly the same order. For a (game, support) group where
the new run recorded no timeout and no skip, both runs solved every position in
that group, and the two groups are the same positions.

Two things come out of that:

  * A CHECK. ``champion_value`` is a rollout and never touched the memo, so on
    a matched group the champion values must be IDENTICAL, position for
    position. If they are not, something other than the memo changed and the
    rest of this comparison is meaningless.
  * THE ANSWER. On the same matched groups, the difference in the optimum is
    the memo bug's effect on the aggregate, with the coverage change divided
    out.

    py scripts4/ii_memo_effect.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OLD = ROOT / "results" / "void" / "ii_endgame_broken_memo.json"
NEW = ROOT / "results" / "ii_endgame.json"
JOURNAL = ROOT / "results" / "ii_endgame_journal.jsonl"


def group(rows):
    out = defaultdict(list)
    for r in rows:
        out[(r["game"], r["support"])].append(r)
    return out


def main() -> int:
    if not OLD.exists() or not NEW.exists():
        print(f"need both {OLD.name} and {NEW.name}")
        return 1
    old = json.loads(OLD.read_text())
    new = json.loads(NEW.read_text())
    # Run this before the re-run lands and NEW is still a copy of OLD: every
    # difference is zero, the check passes, and the output reads exactly like
    # "the memo bug changed nothing". It is not a result, it is the same file
    # twice, and it should say so rather than print a table of zeros.
    if old["solved"] == new["solved"]:
        print(f"{NEW.name} is still the broken run's own output -- identical "
              f"records.\nThere is nothing to compare until the corrected run "
              f"writes it.")
        return 1
    og, ng = group(old["solved"]), group(new["solved"])

    # groups the new run did not fully cover
    incomplete = set()
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") in ("timeout", "skipped"):
                incomplete.add((r["game"], r["support"]))
    else:
        print("no journal; cannot tell which groups are fully covered")
        return 1

    matched = [k for k in og
               if k in ng and k not in incomplete and len(og[k]) == len(ng[k])]
    dropped = [k for k in og if k not in matched]
    n_old = sum(len(og[k]) for k in matched)
    print(f"matched groups: {len(matched)} of {len(og)} "
          f"({n_old} positions of {len(old['solved'])})")
    print(f"  unmatched: {len(dropped)} groups the new run did not fully cover")

    bad = []
    for k in matched:
        a = sorted(round(r["champion"], 12) for r in og[k])
        b = sorted(round(r["champion"], 12) for r in ng[k])
        if a != b:
            bad.append((k, a, b))
    print(f"\nCHECK -- the champion is a rollout and never touched the memo")
    print(f"  champion values identical on matched groups: "
          f"{len(matched) - len(bad)}/{len(matched)}")
    for k, a, b in bad[:5]:
        print(f"    game {k[0]} support {k[1]}: old {a} vs new {b}")
    if bad:
        print("\nThe rollout moved, so something other than the memo changed")
        print("between these runs and the comparison below means nothing.")
        return 1

    def mean(gs, key):
        vals = [r[key] for k in matched for r in gs[k]]
        return sum(vals) / len(vals) if vals else float("nan")

    print(f"\nTHE MEMO'S EFFECT, on {n_old} matched positions")
    rows = [("optimum", mean(og, "value"), mean(ng, "value")),
            ("champion", mean(og, "champion"), mean(ng, "champion")),
            ("gain", mean(og, "gain"), mean(ng, "gain"))]
    print(f"  {'':<10}{'broken':>10}{'fixed':>10}{'change':>10}")
    for name, a, b in rows:
        print(f"  {name:<10}{a:>+10.4f}{b:>+10.4f}{b - a:>+10.4f}")

    # where the two disagree at all, and by how much
    diffs = []
    for k in matched:
        a = sorted(r["value"] for r in og[k])
        b = sorted(r["value"] for r in ng[k])
        for x, y in zip(a, b):
            if abs(x - y) > 1e-9:
                diffs.append((k[1], x, y))
    print(f"\n  positions whose optimum moved: {len(diffs)}/{n_old}")
    if diffs:
        up = sum(1 for _, x, y in diffs if y > x)
        print(f"    the fix raised it in {up}, lowered it in "
              f"{len(diffs) - up}")
        by = defaultdict(int)
        for s, _, _ in diffs:
            by[s] += 1
        tot = defaultdict(int)
        for k in matched:
            tot[k[1]] += len(og[k])
        print(f"    by support: " + ", ".join(
            f"{s}: {by[s]}/{tot[s]}" for s in sorted(tot)))

    out = ROOT / "results" / "ii_memo_effect.json"
    out.write_text(json.dumps({
        "matched_groups": len(matched), "matched_positions": n_old,
        "old_positions": len(old["solved"]),
        "new_positions": len(new["solved"]),
        "champion_identical": len(bad) == 0,
        "broken": {n: a for n, a, _ in rows},
        "fixed": {n: b for n, _, b in rows},
        "optimum_moved": len(diffs)}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
