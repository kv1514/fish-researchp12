"""Fill the learned-weight job file from the v2 fit, and nothing else from it.

``jobs/j29_learned_weights.json`` was written before the fit existed, with the
seeds, the block count, the labels and the baseline all fixed, and a placeholder
where the weights go. This script replaces only that placeholder.

Splitting it this way is the point. The design cannot be adjusted after the
weights are seen, because the design is already on disk and in git; and the
weights cannot be adjusted at all, because they come out of the regression. The
only thing this script is allowed to do is copy one vector.

It plays the **pinned-p** vector and no other. v0.4 validated three variants and
reported the best of them, which is a maximum over three noisy arms;
``jobs/PREREGISTRATION_learned_weights.md`` fixes one in advance so that there is
no maximum to take.

Usage: python scripts4/arm_learned_weights.py [run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

JOBS = ROOT / "jobs" / "j29_learned_weights.json"
PLACEHOLDER = "__weights__"


def _rollout_running() -> bool:
    """Is the v2 strong-continuation rollout pass still adding positions?"""
    import subprocess
    try:
        out = subprocess.run(["pgrep", "-f",
                              "learn_ask_objective.py rollout --run v2"],
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return False
    return bool(out.stdout.strip())


def main(argv):
    run = argv[0] if argv else "v2"
    from learn_ask_objective import results_path

    src = results_path(run)
    if not src.exists():
        print(f"no fit for run {run!r} at {src}; run the fit stage first")
        return 1
    res = json.loads(src.read_text())
    if "fit" not in res or "agent_kwargs" not in res["fit"]:
        print(f"{src} has no fit.agent_kwargs; the fit stage did not complete")
        return 1

    # REFUSE while the rollout pass is still running. The pre-registration says
    # the fit uses every position completed when the duel queue drains, and I
    # armed this once from a 91-block dry run by simply forgetting that -- which
    # is exactly the kind of slip a document cannot prevent and a check can.
    if _rollout_running():
        print("the v2 rollout pass is still running.\n"
              "jobs/PREREGISTRATION_learned_weights.md fixes the fit to use "
              "every position\ncompleted when the duel queue drains, so arming "
              "now would validate a vector\nfitted on an arbitrary prefix -- "
              "and one chosen, in effect, by when someone\nhappened to run this "
              "script. Wait for the pass to finish, re-run the fit,\nthen arm.")
        return 1
    weights = dict(res["fit"]["agent_kwargs"])

    jobs = json.loads(JOBS.read_text())
    changed = 0
    for j in jobs:
        kw = j["x"][1]
        if PLACEHOLDER not in kw:
            continue
        kw.pop(PLACEHOLDER)
        kw.update(weights)
        changed += 1
    if not changed:
        print("nothing to fill; the job file is already armed")
        print(json.dumps(jobs[0]["x"][1], indent=1))
        return 0
    JOBS.write_text(json.dumps(jobs, indent=1))
    print(f"armed {changed} block(s) from {src.name}")
    print(f"  positions in the fit: {res['fit'].get('n_blocks')}")
    print(f"  weights: {json.dumps(weights)}")
    print(f"  baseline: {json.dumps(jobs[0]['y'])}")
    print("\nSeeds, block count and baseline were fixed before this ran and are "
          "unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
