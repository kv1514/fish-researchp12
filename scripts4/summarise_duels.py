"""Aggregate results/v04_duels.jsonl into a readable table.

Prints every duel with its paired score, set differential, interval and the
minimum effect the run could have resolved, so a "no difference" is never read
as evidence of absence when it is only absence of evidence. The measured
per-pair SD is 3.869 sets (fish4/evalx/README.md), which is what the
minimum-detectable-effect column uses.
"""
import json
import math
import sys
from pathlib import Path

SD = 3.869          # measured, see fish4/evalx/README.md


def mde(n, sd=SD, alpha=0.05, power=0.8):
    if not n:
        return float("inf")
    return (1.959964 + 0.8416212) * sd / math.sqrt(n)


def main(path=None, filt=None):
    p = Path(path or Path(__file__).resolve().parents[1] / "results"
             / "v04_duels.jsonl")
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if filt:
        rows = [r for r in rows if filt in r.get("label", "")]
    print(f"{'label':40s} {'n':>5s} {'score':>7s} {'diff':>8s} "
          f"{'95% CI':>20s} {'MDE':>6s}  verdict")
    for r in rows:
        lo, hi = r["diff_ci"]
        v = ("X stronger" if lo > 0 else "Y stronger" if hi < 0
             else "unresolved")
        print(f"{r['label'][:40]:40s} {r['n_pairs']:5d} "
              f"{r['pair_score']:7.3f} {r['diff_mean']:+8.3f} "
              f"[{lo:+7.3f},{hi:+7.3f}] {mde(r['n_pairs']):6.2f}  {v}")


if __name__ == "__main__":
    main(None, sys.argv[1] if len(sys.argv) > 1 else None)
