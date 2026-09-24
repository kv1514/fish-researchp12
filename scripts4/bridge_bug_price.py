"""What did the bridge defect cost their engine? Paired, on the same deals.

An adversarial read of Dylan's C++ (workflow of 2026-08-28) found that our
bridge, not his engine, was answering one question wrongly. Forced to declare,
his own driver picks the first live half-suit the mover HOLDS A CARD IN::

    // engine/src/game.hpp:535
    for (int st = 0; st < NSET; st++)
      if (g.pub.setActive[st] && (g.hand[g.turn] & setMask(st)))
        { chosen = st; break; }

Ours picked the first live half-suit, full stop. So his ``bestGuess`` was
periodically asked to name all six owners of a half-suit it held nothing of --
a question with no anchor in its own hand, which it gets wrong nearly every
time, and which under the opponent-award rule hands the set to US.

The defect ran in our favour. That is the direction nobody catches by looking
at their own results and nodding, so it is worth pricing exactly rather than
waving at.

WHY PAIRED. Both journals were generated from the same seed base (SEED0 =
900,000) with the same seat rotation, so a deal played under rev 1 has a
rev-2 twin with an identical deal and identical seeding. Differencing within
the twin removes deal variance -- the same reason every screen in this project
is a duplicate-deal design -- and turns a comparison that would need thousands
of games into one that is decisive in hundreds.

WHAT IT CANNOT TELL YOU. This is not a clean A/B of one code path: repairing
the forced choice changes which half-suit is declared, so the games diverge
from that point and everything downstream differs. The estimate is the
end-to-end price of the defect as it was actually published, which is the
quantity a retraction needs, not the marginal effect of one decision.

    py scripts4/bridge_bug_price.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OLD = ROOT / "results" / "mega_match_journal_prefix_bridgebug.jsonl"
NEW = ROOT / "results" / "mega_match_journal.jsonl"


def _load(path: Path) -> dict:
    rows = {}
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows[(r["deal"], r["kv_even"])] = r
    return rows


def main() -> int:
    old, new = _load(OLD), _load(NEW)
    keys = sorted(set(old) & set(new))
    if len(keys) < 100:
        print(f"{len(keys)} paired games; need 100+ to report")
        return 1

    d = [new[k]["margin"] - old[k]["margin"] for k in keys]
    n = len(d)
    mean = sum(d) / n
    var = sum((x - mean) ** 2 for x in d) / (n - 1)
    se = (var / n) ** 0.5

    def side(rows, key, sub, i=None):
        num = sum(rows[k][key][sub][i] if i is not None
                  else rows[k][key][sub] for k in keys)
        return num

    print(f"\n=== what the forced-declaration bridge defect was worth ===")
    print(f"{n:,} deals played under both bridge revisions "
          f"(identical deals, identical seating)\n")
    print(f"  our margin, rev 1 (defective)  "
          f"{sum(old[k]['margin'] for k in keys)/n:+.4f} sets/game")
    print(f"  our margin, rev 2 (repaired)   "
          f"{sum(new[k]['margin'] for k in keys)/n:+.4f} sets/game")
    print(f"  paired difference              {mean:+.4f} "
          f"[{mean-1.96*se:+.4f}, {mean+1.96*se:+.4f}]")
    verdict = ("the defect FLATTERED us" if mean < 0 else
               "the defect did not flatter us" if mean > 0 else "no change")
    print(f"  -> {verdict}"
          + (f" by {-mean:.4f} sets/game" if mean < 0 else ""))

    # The counter was added WITH the fix, so rev 1 has no field to read. Say
    # "not recorded" -- summing a missing key to 0 would print the defect's
    # own signature as absent, which is the opposite of the truth.
    def _anchorless(rows, sub):
        vals = [rows[k].get("anchorless") for k in keys]
        if any(v is None for v in vals):
            return None
        return sum(v.get(sub, 0) for v in vals)

    print(f"\n  their forced-declaration anchor, the mechanism itself:")
    for tag, rows in (("rev 1", old), ("rev 2", new)):
        a = _anchorless(rows, "dy")
        got = "not recorded (counter added with the fix)" if a is None else \
              f"{a:,} ({a/n:.2f}/game)"
        print(f"    {tag}  declarations by their seats holding no card of "
              f"the half-suit: {got}")
    print(f"  (ours, for contrast -- deliberate, from the posterior:)")
    for tag, rows in (("rev 1", old), ("rev 2", new)):
        a = _anchorless(rows, "kv")
        print(f"    {tag}  " + ("not recorded" if a is None
                                else f"{a:,} ({a/n:.2f}/game)"))

    print(f"\n  their declaration accuracy:")
    for tag, rows in (("rev 1", old), ("rev 2", new)):
        c = side(rows, "dec", "dy", 0)
        t = side(rows, "dec", "dy", 1)
        print(f"    {tag}  {100*c/t:.2f}%  (n={t:,})")
    print(f"  ours, which the fix does not touch:")
    for tag, rows in (("rev 1", old), ("rev 2", new)):
        c = side(rows, "dec", "kv", 0)
        t = side(rows, "dec", "kv", 1)
        print(f"    {tag}  {100*c/t:.2f}%  (n={t:,})")

    out = {
        "n_paired_games": n,
        "margin_rev1": sum(old[k]["margin"] for k in keys) / n,
        "margin_rev2": sum(new[k]["margin"] for k in keys) / n,
        "paired_difference": mean,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "their_anchorless_rev1": _anchorless(old, "dy"),
        "their_anchorless_rev2": _anchorless(new, "dy"),
        "our_anchorless_rev1": _anchorless(old, "kv"),
        "our_anchorless_rev2": _anchorless(new, "kv"),
        "their_declare_acc_rev1": side(old, "dec", "dy", 0) / side(old, "dec", "dy", 1),
        "their_declare_acc_rev2": side(new, "dec", "dy", 0) / side(new, "dec", "dy", 1),
        "our_declare_acc_rev1": side(old, "dec", "kv", 0) / side(old, "dec", "kv", 1),
        "our_declare_acc_rev2": side(new, "dec", "kv", 0) / side(new, "dec", "kv", 1),
    }
    (ROOT / "results" / "bridge_bug_price.json").write_text(
        json.dumps(out, indent=1))
    print("\nwrote results/bridge_bug_price.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
