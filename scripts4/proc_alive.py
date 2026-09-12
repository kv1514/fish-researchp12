"""Is a specific python job actually running? Asks /proc, not the pattern.

WHY THIS EXISTS
---------------
``run_learn_v2.sh`` decided whether to restart the rollout pass with

    pgrep -f "learn_ask_objective.py rollout --run v2"

which matches the FULL COMMAND LINE OF EVERY PROCESS, including processes that
merely mention the job. A shell one-liner written to watch the pass -- literally
``pgrep -fc "learn_ask_objective.py rollout"`` inside a monitoring loop --
contains that string in its own command line, so the supervisor saw a match,
concluded the pass was alive, and never restarted it. The pass stayed dead for
as long as the watcher ran.

That is the mirror image of the ``arm_learned_weights`` bug this project already
documents. There, ``pgrep`` returning False on any exception made the guard fail
OPEN and arm something that should have waited. Here it fails CLOSED: a
bystander keeps a supervisor from doing the one thing it exists to do. Both come
from treating "a string appears somewhere in the process table" as if it meant
"this job is running".

WHAT THIS DOES INSTEAD
----------------------
Walks ``/proc``, and counts a process only when

  * it is a python interpreter -- argv[0]'s basename starts with ``python``,
    which excludes every shell, editor, grep and watcher that merely names the
    job; and
  * every one of the given tokens appears among argv[1:], so the match is
    against the job's own arguments rather than a substring of a longer line;
    and
  * it is not this process, and not an ancestor of it, so a wrapper that
    launched the check cannot answer for the job.

Exit status is 0 when at least one such process exists and 1 when none does,
so a shell can use it directly:

    if python scripts4/proc_alive.py learn_ask_objective.py rollout --run v2

Prints the matching PIDs on stdout, one per line, so a caller can act on them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _argv(pid: str) -> list[str] | None:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, PermissionError):
        return None
    if not raw:
        return None
    return [a for a in raw.decode("utf-8", "replace").split("\0") if a]


def _ancestors(pid: int) -> set[int]:
    """Every process from ``pid`` up to init, so a wrapper cannot self-match."""
    out, cur = set(), pid
    for _ in range(64):
        out.add(cur)
        if cur <= 1:
            break
        try:
            fields = Path(f"/proc/{cur}/stat").read_text().rsplit(")", 1)[-1]
            cur = int(fields.split()[1])
        except (OSError, IndexError, ValueError):
            break
    return out


def matching_pids(tokens: list[str]) -> list[int]:
    skip = _ancestors(os.getpid())
    hits = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in skip:
            continue
        argv = _argv(entry)
        if not argv:
            continue
        # A python interpreter, not a shell that mentions one.
        if not os.path.basename(argv[0]).startswith("python"):
            continue
        args = argv[1:]
        if all(any(tok == a or tok in a for a in args) for tok in tokens):
            hits.append(pid)
    return sorted(hits)


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: proc_alive.py TOKEN [TOKEN ...]", file=sys.stderr)
        return 2
    hits = matching_pids(argv)
    for pid in hits:
        print(pid)
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
