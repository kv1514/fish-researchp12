"""What is pairing actually worth in this project's experiments?

Section~\\ref{sec:eval} of the paper opens by asserting that raw win rates in a
card game are dominated by the deal, and every experiment here is paired on
that basis. `scripts4/deal_luck.py` then measured the deal's contribution to
the head-to-head margin at -1.3% [-4.0%, +1.5%] of variance -- zero -- and
found seat-parity duplication worth 0.99x the games.

That is only half the design, and it is the less important half. When two ARMS
are compared, both play the identical deal from the identical seats and differ
only by a knob, so they share far more than the cards: the same opponents, the
same seat rotation, and agent seeds derived the same way. Whether THAT pairing
pays is a separate question, and it is the one every ship decision in this
project rests on.

The measurement is direct and needs no new games. For arms A and B over n
paired games:

    paired    se = sd(B - A) / sqrt(n)
    unpaired  se = sqrt( (var(A) + var(B)) / n )

and the ratio of their squares is how many times the games an unpaired design
would need to reach the same precision. It is a pure function of the
correlation between the two arms' per-game margins.

Run over every multi-arm journal the repository holds, so the answer is not
one experiment's accident.

    py scripts4/pairing_value.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: (journal, arm keys). Each row is a paired multi-arm run against v0.7 or
#: against a sibling, written by a runner in scripts4/.
JOURNALS = [
    ("g1_gamma_cost_journal.jsonl", ["A_shipped", "B_none", "C_measured"]),
    ("stuck_gate_journal.jsonl", None),
    ("signal_gate_journal.jsonl", None),
    ("forced_exhaustive_v07_journal.jsonl", None),
    ("forced_exhaustive_journal.jsonl", None),
    ("tempo_journal.jsonl", None),
]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _var(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def _margin(v):
    """An arm's margin, or None if this field is not an arm at all.

    Strictly a dict carrying "margin". The first version also accepted a bare
    number, which swept in every scalar the runners write beside the arms --
    `deal`, `kv_even`, `rev` -- and reported the seed counter as an arm with an
    effect of -3,600,247 sets and a pairing efficiency of 1.0x. Those 1.0x rows
    then sat in the same table as the real ones and dragged the median to 1.0,
    which is the sort of summary that reads as a finding.
    """
    return v.get("margin") if isinstance(v, dict) else None


def _arms_of(row):
    return [k for k, v in row.items() if _margin(v) is not None]


def price(path: Path, arms=None) -> dict | None:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        return None
    arms = arms or _arms_of(rows[0])
    arms = [a for a in arms if all(_margin(r.get(a)) is not None for r in rows)]
    if len(arms) < 2:
        return None
    n = len(rows)
    base = arms[0]
    A = [_margin(r[base]) for r in rows]
    out = {"journal": path.name, "n_games": n, "base": base, "pairs": {}}
    print(f"\n{path.name}   {n:,} games, base arm {base!r}")
    print(f"  {'arm':16s} {'effect':>9s} {'paired se':>10s} {'unpaired se':>12s}"
          f" {'corr':>7s} {'same':>6s} {'efficiency':>11s}")
    for arm in arms[1:]:
        B = [_margin(r[arm]) for r in rows]
        d = [b - a for a, b in zip(A, B)]
        se_p = math.sqrt(_var(d) / n)
        se_u = math.sqrt((_var(A) + _var(B)) / n)
        vA, vB = _var(A), _var(B)
        rho = ((vA + vB - _var(d)) / (2 * math.sqrt(vA * vB))
               if vA > 0 and vB > 0 else float("nan"))
        eff = (se_u / se_p) ** 2 if se_p > 0 else float("inf")
        # The fraction of games the two arms finished on the SAME margin. This
        # is the mechanism the efficiency column is measuring: a knob that
        # fires on a rare branch leaves most games bit-identical, and pairing
        # then removes almost all the variance. A knob that touches every
        # decision leaves none of them identical, and pairing removes nothing.
        same = sum(1 for x, y in zip(A, B) if x == y) / n
        print(f"  {arm:16s} {_mean(d):+9.4f} {se_p:10.5f} {se_u:12.5f}"
              f" {rho:7.3f} {same:6.1%} {eff:10.1f}x")
        out["pairs"][arm] = {"effect": _mean(d), "se_paired": se_p,
                             "se_unpaired": se_u, "corr": rho,
                             "same_margin_share": same, "efficiency": eff}
    return out


def main() -> int:
    print("How many times the games an UNPAIRED design would need to match "
          "the\nprecision each paired run actually achieved.\n")
    results = []
    for name, arms in JOURNALS:
        p = ROOT / "results" / name
        if not p.exists():
            print(f"  (skipping {name}: not present)")
            continue
        r = price(p, arms)
        if r:
            results.append(r)
    effs = [v["efficiency"] for r in results for v in r["pairs"].values()]
    if effs:
        effs.sort()
        mid = effs[len(effs) // 2]
        print(f"\n{len(effs)} arm comparisons. Efficiency ranges "
              f"{effs[0]:.1f}x to {effs[-1]:.1f}x, median {mid:.1f}x.")
        print("\nThis is the number the paired design is actually for, and it "
              "is\nnot the one deal_luck.py priced. Swapping seats on the same "
              "deal buys\n0.99x, because there is no antisymmetric deal "
              "advantage to remove.\nHolding the deal, the seats and the "
              "opponents fixed and moving one knob\nremoves the shared "
              "position instead, which is where the variance is.")
    dest = ROOT / "results" / "pairing_value.json"
    dest.write_text(json.dumps({"runs": results,
                                "median_efficiency": (effs[len(effs)//2]
                                                      if effs else None)},
                               indent=1))
    print(f"\nwrote results/{dest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
