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


def _rollout_incomplete(run: str):
    """Is the strong-continuation rollout pass for ``run`` still unfinished?

    Returns a reason string, or None when every harvested position has been
    evaluated.

    This asks the DISK, not the process table, and that is the whole point.
    The first version ran ``pgrep`` for a hard-coded ``--run v2`` and returned
    False on any exception, so it failed OPEN three ways: a missing pgrep, a
    permission error or a timeout all read as "not running" and armed; asking
    about run v3 checked whether v2 was running; and ``run_learn_v2.sh`` polls
    with ``sleep 120`` while ``widen_rollout.sh`` deliberately kills the pass
    mid-flight, leaving a window of up to ~150 s in which no process matches
    and arming succeeds on whatever prefix is on disk. A guard written because
    a slip already happened once must fail closed.
    """
    from fish4.learn.dataset import iter_positions
    from fish4.learn.rollout import completed_rollouts
    from learn_ask_objective import data_root

    root = data_root(run)
    if not root.exists():
        return f"no harvest at {root}"
    done = completed_rollouts(root)
    pids = [rec["pid"] for rec in iter_positions(root)]
    if not pids:
        return f"no harvested positions under {root}"
    missing = [x for x in pids if x not in done]
    if missing:
        return (f"{len(missing)} of {len(pids)} harvested positions have no "
                f"rollout yet")
    return None


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
    reason = _rollout_incomplete(run)
    if reason:
        print(f"the {run} rollout pass is not finished: {reason}.\n"
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
        # "Already armed" is not the same as "armed with the right vector", and
        # conflating them made the recovery path a no-op that exits success.
        # This script exists because the job file was once armed from a 91-block
        # dry run; the fix for that is to re-run the fit and re-arm, and the
        # old code answered that with "nothing to fill" and status 0, leaving
        # the prefix weights in place.
        armed = {k: v for k, v in jobs[0]["x"][1].items()
                 if k in weights}
        stale = {k: (armed.get(k), v) for k, v in weights.items()
                 if armed.get(k) != v}
        if stale:
            print("the job file is armed with a DIFFERENT vector from the "
                  "current fit.")
            for k, (was, now) in sorted(stale.items()):
                print(f"  {k:<12} armed {was!r}  fit now {now!r}")
            print("\nRefusing to leave that standing. Re-arm deliberately: "
                  "remove the armed\nvalues from jobs/j29_learned_weights.json "
                  f"(restoring {PLACEHOLDER!r}) and run\nthis again, or keep "
                  "the armed vector if it is the one you meant.")
            return 1
        print("nothing to fill; the job file is already armed, and with the "
              "vector this fit\nproduces")
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
