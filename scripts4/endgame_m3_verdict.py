"""Pool the m = 3 blocks and read the verdict prereg/endgame_m3.md fixed.

TWO THINGS HAD TO BE CLEANED UP, AND NEITHER IS A DETAIL.

Block 04 was run twice -- a job file holding two blocks was re-invoked after the
first used the whole window, and scripts4/duel.py has no skip logic, so it redid
the first. Pooling per-pair differentials without noticing would have counted
250 deals twice, and since the duplicate is a bit-identical rerun of the same
seeds it would have narrowed the interval rather than moved it: the failure that
looks like more evidence.

Blocks 01 and 03 ran against a DIFFERENT ENGINE. A design workflow was
exploring the repository while the duels ran, and its agents edited
fish4/agent4.py and fish4/claim4.py in the working tree and then reverted them.
Nothing was committed, so git showed a clean tree afterwards and the only
surviving evidence is the per-block engine digest that scripts4/duel.py records
with every result. Those two blocks are discarded and re-run as "01r" and "03r"
against the clean engine.

That is the whole reason the digest is recorded, and it is the first time it has
caught anything. The lesson is narrower than "do not use agents": do not let
agents with write access explore a repository while measurements are running in
it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUELS = ROOT / "results" / "v04_duels.jsonl"
PREFIX = "endgame-m3-"
EXPECTED = 8


def main() -> int:
    rows = [json.loads(x) for x in DUELS.read_text().splitlines() if x.strip()]
    hits = [r for r in rows if r.get("label", "").startswith(PREFIX)]
    by_label = {}
    for r in hits:
        by_label[r["label"]] = r
    # A rerun supersedes the block it replaces: "endgame-m3-01r" for "-01".
    superseded = {k[:-1] for k in by_label if k.endswith("r")}
    for k in superseded:
        by_label.pop(k, None)
    dropped = len(hits) - len(by_label)
    b = [by_label[k] for k in sorted(by_label)]
    if superseded:
        print(f"  {len(superseded)} block(s) re-run against the clean engine "
              f"and superseded: {sorted(superseded)}")
    print(f"{len(hits)} journal rows -> {len(b)} distinct blocks "
          f"({dropped} duplicate rerun(s) dropped)")
    if len(b) != EXPECTED:
        print(f"{len(b)} blocks, expected {EXPECTED}.")
        return 1
    digs = sorted(set(r["engine"]["digest"] for r in b))
    if len(digs) > 1:
        print(f"blocks ran against {len(digs)} engines: {digs}. "
              f"Refusing to pool.")
        return 1
    diffs = [d for r in b for d in r["diffs"]]
    n = len(diffs)
    m = sum(diffs) / n
    var = sum((x - m) ** 2 for x in diffs) / (n - 1)
    se = (var / n) ** 0.5
    lo, hi = m - 1.96 * se, m + 1.96 * se
    print(f"\nengine {digs[0]}; {n} pairs")
    print("   " + "  ".join(f"{r['diff_mean']:+.3f}" for r in b))
    print(f"\npooled: {m:+.4f} sets, 95% CI [{lo:+.4f}, {hi:+.4f}]")
    pos = sum(1 for r in b if r["diff_mean"] > 0)
    print(f"  {pos}/{len(b)} blocks positive; "
          f"timeouts {sum(r['timeouts'] for r in b)}, "
          f"dropped {sum(r['dropped_pairs'] for r in b)}")

    m2 = json.loads((ROOT / "results" / "endgame_ask_stack.json").read_text())
    print(f"\n  for scale, taking the same correction from m<=1 to m<=2 was "
          f"worth {m2['diff']:+.4f}")
    if lo > 0:
        print("\n  Outcome 1: it extends. Ship endgame_m = 3.")
        v = "extends"
    elif m > 0:
        print("\n  Outcome 2: unresolved. The point estimate is positive and "
              "the interval is\n  not. The offline evidence does not license "
              "a default change on its own,\n  which is the rule the m = 2 "
              "stacking run was held to. Not shipped, and no\n  second run.")
        v = "unresolved"
    else:
        print("\n  Outcome 3: it does NOT extend. That is worth more than the "
              "change would\n  have been: the sampled one-ply target "
              "identified a defect at m = 3 that\n  does not convert into "
              "play, so the target stops predicting play somewhere\n  between "
              "m = 2 and m = 3, and anything built on it above the endgame is\n"
              "  suspect.")
        v = "does-not-extend"
    dest = ROOT / "results" / "endgame_m3_verdict.json"
    dest.write_text(json.dumps({
        "n_pairs": n, "n_blocks": len(b), "duplicates_dropped": dropped,
        "engine": digs[0], "diff": m, "ci95": [lo, hi],
        "blocks_positive": pos, "verdict": v,
        "m2_stack_for_scale": m2["diff"]}, indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
