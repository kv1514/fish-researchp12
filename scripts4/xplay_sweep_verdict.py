"""The endgame-m sweep against a foreign opponent, paired on identical deals.

Every configuration played the same 500 deals against the same v0.3 champion
with the same seat rotation and agent seeds, so each deal's differential can be
differenced BETWEEN configurations, removing deal variance entirely. The
unpaired block intervals are about +/-0.45; the paired ones below are what the
design actually affords.

Sign convention: scripts4/duel.py stores diffs as X minus Y with v0.3 as X, so
NEGATIVE means the fishbot configuration is stronger. This report flips the
sign so positive = margin over v0.3, and says so.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"
MS = (0, 2, 3, 5, 9)


def main() -> int:
    rows = [json.loads(x) for x in DUELS.read_text().splitlines() if x.strip()]
    per = {}
    for m in MS:
        d = []
        for k in (0, 1):
            hit = [r for r in rows
                   if r.get("label") == f"xplay-m{m}-v03-{k}"]
            if not hit:
                print(f"missing block xplay-m{m}-v03-{k}")
                return 1
            d.extend(-x for x in hit[-1]["diffs"])   # flip: + = beats v0.3
        per[m] = d
    n = len(per[0])
    if any(len(v) != n for v in per.values()):
        print("blocks are different sizes; pairing is invalid")
        return 1

    def stat(v):
        m_ = sum(v) / len(v)
        var = sum((x - m_) ** 2 for x in v) / (len(v) - 1)
        return m_, (var / len(v)) ** 0.5

    print(f"{n} deals, every configuration on the same ones\n")
    print("  m    margin over v0.3        paired vs m=0")
    out = {}
    for m in MS:
        mm, se = stat(per[m])
        if m == 0:
            print(f"  {m}    {mm:+.4f} [{mm-1.96*se:+.4f}, {mm+1.96*se:+.4f}]"
                  f"        --")
            out[m] = {"margin": mm, "ci": [mm - 1.96 * se, mm + 1.96 * se]}
        else:
            d = [a - b for a, b in zip(per[m], per[0])]
            dm, dse = stat(d)
            print(f"  {m}    {mm:+.4f} [{mm-1.96*se:+.4f}, {mm+1.96*se:+.4f}]"
                  f"   {dm:+.4f} [{dm-1.96*dse:+.4f}, {dm+1.96*dse:+.4f}]")
            out[m] = {"margin": mm, "ci": [mm - 1.96 * se, mm + 1.96 * se],
                      "vs_m0": dm, "vs_m0_ci": [dm - 1.96 * dse,
                                                dm + 1.96 * dse]}
    d2 = [a - b for a, b in zip(per[2], per[0])]
    dm, dse = stat(d2)
    print()
    if dm - 1.96 * dse > 0:
        print("  m = 2 genuinely helps against a foreign opponent.")
        v = "m2-helps"
    elif dm + 1.96 * dse < 0:
        print("  m = 2 HURTS against a foreign opponent. Even the rung with "
              "exact-solver\n  evidence behind it does not survive leaving "
              "the family, and the honest\n  default is m = 0.")
        v = "m2-hurts"
    else:
        print("  m = 2 is indistinguishable from no correction against a "
              "foreign opponent\n  -- the interval is paired on identical "
              "deals and still straddles zero. Its\n  +0.1220 was measured "
              "against the sibling and is family-relative. Under the\n  "
              "registered rule ties default to m = 2, which keeps the "
              "family-relative gain\n  at a foreign-relative cost bounded by "
              "the interval below.")
        v = "m2-tie"
    dest = ROOT / "results" / "xplay_sweep.json"
    dest.write_text(json.dumps({
        "n_deals": n, "opponent": "v0.3 champion (tuned)",
        "by_m": out, "verdict": v}, indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
