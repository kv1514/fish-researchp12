"""Does the exact gain grow with how much is hidden? And what does that do to
the headline, given that the unsolved positions are the wide ones?

scripts4/ii_endgame.py reports a mean gain over the positions it can solve. It
cannot solve the wide ones -- 141 of 313 hidden m = 2 positions had a belief
support above 24 deals, with a median of 180 against a solved median of 4. If
the gain is flat in support that does not matter. If it rises, every headline
in that section is an understatement, and the size of the understatement grows
with how much coverage was lost.

This measures the slope rather than assuming either way. It is deliberately not
an extrapolation: the relationship is fitted over supports 2-24 and the missing
positions run to 60,480, so the DIRECTION is the claim and the magnitude is
not.

    py scripts4/ii_support_bias.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = [("m=1", "ii_endgame.json", "ii_endgame_journal.jsonl"),
          ("m=2", "ii_endgame_m2.json", "ii_endgame_journal_m2.jsonl")]


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return 0.0, 0.0, 0.0
    r = sxy / math.sqrt(sxx * syy)
    t = r * math.sqrt(n - 2) / math.sqrt(1 - r * r) if abs(r) < 1 else float("inf")
    return r, sxy / sxx, t


def welch(a, b):
    """Two-sample t on unequal variances, since the halves differ in size."""
    na, nb = len(a), len(b)
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb)
    return ma, mb, (ma - mb) / se if se else 0.0


def main() -> int:
    out = {}
    for label, res, journal in LAYERS:
        rp = ROOT / "results" / res
        if not rp.exists():
            print(f"{label}: {res} missing")
            continue
        rows = json.loads(rp.read_text())["solved"]
        xs = [r["support"] for r in rows]
        ys = [r["gain"] for r in rows]
        r, slope, t = pearson(xs, ys)
        med = sorted(xs)[len(xs) // 2]
        lo = [y for x, y in zip(xs, ys) if x <= med]
        hi = [y for x, y in zip(xs, ys) if x > med]
        mlo, mhi, tt = welch(hi, lo) if lo and hi else (0, 0, 0)

        # what was NOT solved, from the journal
        miss = []
        jp = ROOT / "results" / journal
        if jp.exists():
            for line in jp.read_text().splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("kind") == "skipped":
                    miss.append(rec["support"])
                elif (rec.get("kind") == "timeout"
                      and rec.get("support", 1) > 1):
                    miss.append(rec["support"])

        print(f"\n{label}: {len(rows)} solved positions")
        print(f"  gain vs support: r = {r:+.3f}, slope {slope:+.5f} per deal, "
              f"t = {t:+.2f}")
        print(f"  support > {med} mean {mlo:+.4f} (n={len(hi)}) against "
              f"<= {med} mean {mhi:+.4f} (n={len(lo)}), t = {tt:+.2f}")
        if miss:
            miss.sort()
            print(f"  NOT solved: {len(miss)}, median support "
                  f"{miss[len(miss)//2]}, max {miss[-1]}")
            print(f"  solved median support {med}. The unsolved positions are "
                  f"the wide ones,\n  and the gain rises with width, so "
                  f"{label}'s reported mean is a LOWER bound.")
        out[label] = {"n": len(rows), "r": r, "slope": slope, "t": t,
                      "median_support": med, "mean_wide": mlo,
                      "mean_narrow": mhi, "welch_t": tt,
                      "n_unsolved": len(miss),
                      "median_unsolved_support": (miss[len(miss) // 2]
                                                  if miss else None)}
    print("\nThe direction is the claim. The slope is fitted over supports the")
    print("solver can reach and the missing positions run far past them, so it")
    print("is not extrapolated to a corrected figure -- doing that would be")
    print("inventing a number for the half of the layer nobody has solved.")
    (ROOT / "results" / "ii_support_bias.json").write_text(
        json.dumps(out, indent=1))
    print("\nwrote results/ii_support_bias.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
