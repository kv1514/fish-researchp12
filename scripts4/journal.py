"""Where a resumable runner appends while it is still running.

Every paired runner in this directory journals each played row so a killed
container can resume from disk instead of replaying half an hour. That works,
and it has one cost nobody designed for: the journal is a tracked file that
changes on every flush, so a repository with a run in flight is never clean,
and "commit your changes" becomes a prompt to commit a half-finished
measurement.

So a run in flight appends to ``<journal>.partial``, which is ignored, and the
file is renamed to its real name only when the run completes. Resumability is
unaffected -- the loader reads whichever exists, preferring the partial -- and
a partial journal on disk now means exactly what it says: a run that did not
finish.
"""
from __future__ import annotations

from pathlib import Path

SUFFIX = ".partial"


def in_flight(dest: Path) -> Path:
    """The path to append to while the run is going."""
    return Path(str(dest) + SUFFIX)


def to_read(dest: Path) -> Path:
    """The journal to resume from: the partial if there is one, else the
    finished file. A finished run leaves no partial, so this reads the real
    journal; an interrupted one leaves both only if a previous run finished
    and a later one was killed, and the partial is the newer of the two."""
    p = in_flight(dest)
    return p if p.exists() else dest


def finish(dest: Path) -> None:
    """Promote a completed run's journal to its real name.

    Appends rather than clobbers when a finished journal is already there:
    two runs of the same experiment on disjoint seed blocks are a legitimate
    thing to want, and silently discarding the older one is not.
    """
    p = in_flight(dest)
    if not p.exists():
        return
    if dest.exists():
        with dest.open("a") as out, p.open() as src:
            for line in src:
                out.write(line)
        p.unlink()
    else:
        p.rename(dest)
