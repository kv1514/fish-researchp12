"""Apply the pre-registered selection rule and emit the settling job.

The rule lives in `jobs/PREREGISTRATION_value_keep.md`:

    The cell with the HIGHEST POINT ESTIMATE is carried forward. Ties broken by
    the smaller `value_keep` (the weaker intervention).

Writing it as code, and committing that code before the screen has finished, is
the point of this file. A selection rule applied by hand after five numbers are
on screen is indistinguishable from a rule chosen because of them -- not to
anyone reading it later, and not reliably to the person applying it. Here the
rule runs, prints what it picked and what it passed over, and cannot see
anything the pre-registration did not already name.

It also refuses to run on a partial screen. The first attempt at this screen
died silently four minutes into its second cell, and a selection over "whatever
happened to finish" is exactly the failure that would produce.

    py scripts4/value_keep_settle.py            # select, write the job file
    py scripts4/value_keep_settle.py --run 3    # ... and run it with 3 workers

The settling run itself is 2 blocks x 1000 pairs on seeds 32 000 000 and
32 200 000, reserved in the pre-registration and disjoint from the screen.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DUELS = ROOT / "results" / "v04_duels.jsonl"
SCREEN = ROOT / "jobs" / "j24_value_keep_screen.json"
OUT = ROOT / "jobs" / "j25_value_keep_settle.json"

#: Fixed in the pre-registration, before any cell reported.
BLOCKS = ((32_000_000, 32001), (32_200_000, 32002))
N_PAIRS = 1000
BASELINE = -7.355            # value pure vs champion, 200 pairs
BASELINE_CI = (-7.875, -6.835)
ADOPT = 0.05                 # interval must lie entirely above this


def screen_cells() -> list:
    """The screen's cells, matched to results by label. Order preserved."""
    want = [c["label"] for c in json.loads(SCREEN.read_text())]
    got = {}
    for line in DUELS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("label") in want:
            got[r["label"]] = r          # last wins, if ever re-run
    return [got[l] for l in want if l in got], want


def keep_of(label: str) -> float:
    """The value_keep this cell played, read from the spec rather than the name."""
    for line in DUELS.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("label") == label:
            return float(r["spec_x"][1]["value_keep"])
    raise KeyError(label)


def main(argv) -> int:
    cells, want = screen_cells()
    if len(cells) != len(want):
        have = {c["label"] for c in cells}
        print(f"screen is INCOMPLETE: {len(cells)}/{len(want)} cells.")
        for l in want:
            print(f"  {'done' if l in have else 'MISSING'}  {l}")
        print("\nRefusing to select. A rule applied to whichever cells happened\n"
              "to finish is not the rule that was pre-registered.")
        return 1

    rows = [(keep_of(c["label"]), c["diff_mean"], c["diff_ci"], c["label"])
            for c in cells]

    print(f"{'keep':>6}  {'estimate':>9}   95% CI                  recovery vs "
          f"{BASELINE:+.3f}")
    print("-" * 74)
    for k, m, ci, _ in sorted(rows):
        print(f"{k:>6.2f}  {m:>+9.3f}   [{ci[0]:+.3f}, {ci[1]:+.3f}]   "
              f"{m - BASELINE:>+8.3f}")

    # The rule: highest point estimate, ties to the smaller keep. Sorting by
    # (-estimate, keep) and taking the first is exactly that, and is written
    # this way so the tie-break is visible rather than incidental.
    pick = sorted(rows, key=lambda r: (-r[1], r[0]))[0]
    keep, est, ci, label = pick
    print(f"\nselected: value_keep = {keep:g}  ({est:+.3f})")
    runners = [r for r in sorted(rows, key=lambda r: (-r[1], r[0]))[1:3]]
    if runners:
        print("passed over: " + ", ".join(
            f"{r[0]:g} ({r[1]:+.3f})" for r in runners))
    print("\nThis number is SELECTED-ON and is not an estimate of anything. The\n"
          "claim-threshold screen decayed +0.035 -> +0.002 when re-run\n"
          "unselected. The settling run below is what gets reported.")

    job = [
        {"label": f"SETTLE value_keep {keep:.2f} vs champion block {i}",
         "n_pairs": N_PAIRS, "base_seed": seed, "agent_seed": aseed,
         "x": ["fishbot4", {"opponent_gamma": 0.35, "objective": "value",
                            "value_turn": 0.15, "value_keep": keep,
                            "hsvalue_path": "checkpoints/hsvalue_v1.json"}],
         "y": ["fishbot4", {"opponent_gamma": 0.35}]}
        for i, (seed, aseed) in enumerate(BLOCKS)
    ]
    OUT.write_text(json.dumps(job, indent=1) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(job)} blocks x {N_PAIRS} "
          f"pairs, seeds {', '.join(str(s) for s, _ in BLOCKS)}")
    print(f"adoption needs the 95% interval entirely above {ADOPT:+.2f}")

    if "--run" in argv:
        i = argv.index("--run")
        jobs = argv[i + 1] if len(argv) > i + 1 else "3"
        print(f"\nchecking seeds before running")
        rc = subprocess.run([sys.executable, str(ROOT / "scripts4"
                                                 / "check_seeds.py")]).returncode
        if rc != 0:
            print("seed check FAILED; not running")
            return 1
        return subprocess.run([sys.executable, str(ROOT / "scripts4" / "duel.py"),
                               str(OUT), jobs]).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
