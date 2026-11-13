"""A liveness check must not be answerable by a bystander.

``run_learn_v2.sh`` restarted the rollout pass whenever

    pgrep -f "learn_ask_objective.py rollout --run v2"

found nothing. ``pgrep -f`` matches the full command line of every process, so
a shell loop written to WATCH the pass -- one whose own command line contained
that string -- was itself a match. The supervisor concluded the pass was alive
and stopped restarting it; the pass stayed dead for as long as the watcher ran.
``widen_rollout.sh`` used the same pattern to pick a PID to ``kill``, which is
the same bug pointed at something destructive.

That is the mirror of the ``arm_learned_weights`` failure this project already
records, where ``pgrep`` returning False on any exception made a guard fail
OPEN. Both come from reading "this string is somewhere in the process table" as
"this job is running".
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from proc_alive import matching_pids                            # noqa: E402

TOKENS = ["definitely_not_a_real_job.py", "--flavour", "kipper"]


def test_a_shell_that_merely_names_the_job_is_not_the_job():
    assert matching_pids(TOKENS) == [], "fixture tokens must match nothing"
    # A bystander whose command line contains every token, exactly the shape
    # that fooled the supervisor.
    text = " ".join(TOKENS)
    proc = subprocess.Popen(
        ["/bin/sh", "-c", f'echo "{text}" > /dev/null; sleep 30'])
    try:
        time.sleep(0.4)
        # It IS findable by a full-command-line search...
        found = subprocess.run(["pgrep", "-f", TOKENS[0]],
                               capture_output=True, text=True)
        assert str(proc.pid) in found.stdout.split(), (
            "the control did not reproduce the pgrep match this test is about")
        # ...and must NOT be findable by ours.
        assert matching_pids(TOKENS) == [], (
            "a /bin/sh process answered for a python job")
    finally:
        proc.kill()
        proc.wait()


def test_a_real_python_process_with_those_arguments_is_found():
    """And the check has to be able to say yes, or it is just always-no."""
    script = "import sys, time; time.sleep(30)"
    proc = subprocess.Popen([sys.executable, "-c", script, *TOKENS])
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if proc.pid in matching_pids(TOKENS):
                break
            time.sleep(0.1)
        assert proc.pid in matching_pids(TOKENS), (
            "a python process carrying every token was not found")
    finally:
        proc.kill()
        proc.wait()


def test_the_caller_and_its_ancestors_never_answer_for_the_job():
    """A wrapper that launched the check must not match on its own behalf."""
    from proc_alive import _ancestors
    anc = _ancestors(os.getpid())
    assert os.getpid() in anc
    assert len(anc) >= 2, "expected at least this process and its parent"
    # pytest's own command line mentions this test file, which mentions the
    # tokens; that must not be able to register as the job.
    assert os.getpid() not in matching_pids(TOKENS)


def test_both_supervisors_stopped_using_pgrep_for_this():
    """The scripts are the thing that was wrong; assert they were changed.

    ``widen_rollout.sh`` in particular feeds the result to ``kill``.
    """
    for name in ("run_learn_v2.sh", "widen_rollout.sh"):
        text = (ROOT / "scripts4" / name).read_text()
        assert "proc_alive.py" in text, f"{name} does not use the exact check"
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "pgrep -f \"learn_ask_objective" not in stripped, (
                f"{name} still identifies the rollout job with pgrep -f: "
                f"{stripped}")
