"""A prediction from the null mechanism, scored against data that already exists.

``results/null_recoverability.json`` finds that at the moment of a null, an
independent re-draw of the SAME posterior picks the true split about a quarter
of the time. The declared split is always the agent's own MAP on every claim
path, so a probe that disagrees can only disagree because it sampled different
worlds. That share of nulls is sampler noise, not missing information -- and
sampler noise is the one kind more computation buys back.

THE PREDICTION, WRITTEN BEFORE LOOKING
--------------------------------------
The PRECISION pool ran ``n_draws=480`` against the champion's 160 over 6000
pairs and produced +0.340, the largest demonstrated gain in this project, with
no mechanism ever attached to it. If claim-time sampler noise is real, then:

  **the 480-draw arm should cause FEWER nulls per game than the 160-draw arm.**

That is a directional prediction with a falsifier. If the 480 arm nulls at the
same rate or more, claim-time sampling noise does not survive contact with
play at this budget, and the quarter-of-nulls figure describes a probe rather
than a policy.

Magnitude is deliberately not predicted. A quarter of nulls flipping on ONE
redraw does not translate into a known reduction at three times the draws, and
inventing a number to hit would make the test unfalsifiable in the other
direction.

The PRECISION2 pool (1440 vs 480) is scored the same way as a second, harder
test: the same mechanism predicts a smaller reduction there, because there is
less noise left to remove.

    py scripts4/precision_nulls.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"

POOLS = {
    "PRECISION 480 vs 160": [f"PRECISION n_draws 480 vs 160 block {i}"
                             for i in range(6)],
    "PRECISION2 1440 vs 480": [f"PRECISION2 n_draws 1440 vs 480 block {i}"
                               for i in range(6)],
    "GAMMA_SCHEDULE (control)": [f"GAMMA_SCHEDULE s1.0 vs champion block {i}"
                                 for i in range(6)],
}


def rows():
    out = {}
    for line in DUELS.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r.get("label", "")] = r
    return out


def main() -> int:
    by = rows()
    print("does buying posterior draws reduce nulls, as the mechanism says?\n")
    print(f"{'pool':<26}{'games':>8}{'x/game':>9}{'y/game':>9}"
          f"{'diff':>9}{'95% CI':>20}")
    out = {}
    for name, labels in POOLS.items():
        cells = [by[l] for l in labels if l in by]
        if len(cells) < len(labels):
            print(f"  {name}: only {len(cells)}/{len(labels)} blocks")
            continue
        # Each block contributes one x-rate and one y-rate; the blocks are
        # independent runs, so the between-block spread is the standard error.
        d = [(c["x_nulls"] - c["y_nulls"]) / c["n_pairs"] for c in cells]
        xr = sum(c["x_nulls"] for c in cells) / sum(c["n_pairs"] for c in cells)
        yr = sum(c["y_nulls"] for c in cells) / sum(c["n_pairs"] for c in cells)
        m = sum(d) / len(d)
        sd = math.sqrt(sum((v - m) ** 2 for v in d) / (len(d) - 1))
        se = sd / math.sqrt(len(d))
        lo, hi = m - 1.96 * se, m + 1.96 * se
        g = sum(c["n_pairs"] for c in cells)
        print(f"  {name:<24}{g:>8}{xr:>9.3f}{yr:>9.3f}{m:>9.3f}"
              f"   [{lo:+.3f}, {hi:+.3f}]")
        out[name] = {"games": g, "x_per_game": xr, "y_per_game": yr,
                     "diff": m, "se": se, "ci95": [lo, hi],
                     "per_block": d}

    p1 = out.get("PRECISION 480 vs 160")
    print()
    if not p1:
        print("PRECISION pool incomplete; nothing to score.")
        return 1
    if p1["ci95"][1] < 0:
        print(f"CONFIRMED. The 480-draw arm nulls {-p1['diff']:.3f} fewer times "
              f"per game,\n95% CI excludes zero. Claim-time sampler noise is "
              f"real in play, and it is\npart of what the +0.340 bought -- the "
              f"first mechanism ever attached to that\nnumber.")
        verdict = "confirmed"
    elif p1["diff"] < 0:
        print(f"DIRECTION RIGHT, NOT RESOLVED. The 480-draw arm nulls "
              f"{-p1['diff']:.3f} fewer\ntimes per game but the interval "
              f"includes zero at six blocks. Reported as a\nfailure to "
              f"resolve, not as support.")
        verdict = "unresolved_right_direction"
    else:
        print(f"REFUTED. The 480-draw arm nulls {p1['diff']:+.3f} per game "
              f"relative to 160 --\nthe wrong sign. Claim-time sampler noise "
              f"does not survive contact with play\nat this budget, so the "
              f"redraw share describes the probe and not the policy,\nand it "
              f"is not a route to a stronger engine.")
        verdict = "refuted"

    (ROOT / "results" / "precision_nulls.json").write_text(json.dumps(
        {"pools": out, "verdict": verdict,
         "prediction": "the larger-n_draws arm causes fewer nulls per game"},
        indent=1))
    print("\nwrote results/precision_nulls.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
