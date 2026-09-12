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


def result_for(journal: Path, *, canonical_journal: Path,
               canonical_name: str, results_dir: Path | None = None) -> Path:
    """Where a run's result file belongs, given the journal it actually read.

    THE DEFECT THIS EXISTS TO END. A runner that writes to a fixed path is
    correct exactly once: the first time it is pointed at a different journal,
    it overwrites the previous run's result with a different population's.
    That happened three times on 2026-08-28 alone, by three different routes:

      * a smoke test pointed at a scratch journal dropped `cj_confirm.json`
        into `results/`, where the indexer listed it as an orphan;
      * an 8-game check of new instrumentation replaced an 1,800-game
        `declarer_holding_self.json` with eight games of noise;
      * `error_value.py` run on the signalling journal replaced the stuck-gate
        fit -- and the paper cites that file twice for +1.7898, which it no
        longer contained. Nothing caught that one. Every check passed.

    Three local patches would leave the convention that produced them intact,
    so the rule lives here instead.

    THE RULE.

    The *canonical* journal -- the one this script exists to process -- keeps
    the historical filename, so nothing already pointing at it breaks. Any
    other journal gets a name derived from its own stem, and lands beside that
    journal when the journal is outside the results directory, so a throwaway
    run leaves nothing permanent behind.

    >>> R = Path("/repo/results")
    >>> can = R / "tempo_journal.jsonl"
    >>> result_for(can, canonical_journal=can,
    ...            canonical_name="tempo_confirm.json", results_dir=R).name
    'tempo_confirm.json'
    >>> result_for(R / "tempo_rep8k_journal.jsonl", canonical_journal=can,
    ...            canonical_name="tempo_confirm.json", results_dir=R).name
    'tempo_rep8k_confirm.json'
    >>> result_for(Path("/tmp/cj.jsonl"), canonical_journal=can,
    ...            canonical_name="tempo_confirm.json", results_dir=R).parent
    PosixPath('/tmp')
    """
    journal, canonical_journal = Path(journal), Path(canonical_journal)
    home = Path(results_dir) if results_dir is not None \
        else Path(__file__).resolve().parents[1] / "results"
    try:
        is_canonical = journal.resolve() == canonical_journal.resolve()
    except OSError:                       # a path that cannot be resolved yet
        is_canonical = str(journal) == str(canonical_journal)
    if is_canonical:
        return home / canonical_name

    stem = journal.stem
    if stem.endswith("_journal"):
        stem = stem[: -len("_journal")]
    can_stem = canonical_journal.stem
    if can_stem.endswith("_journal"):
        can_stem = can_stem[: -len("_journal")]

    base, dot, ext = canonical_name.rpartition(".")
    base = base or canonical_name
    ext = f".{ext}" if dot else ""
    # "tempo_confirm.json" for the "tempo" journal -> "<stem>_confirm.json".
    # "error_value.json" for the "stuck_gate" journal shares no prefix, so the
    # stem is appended instead -> "error_value_<stem>.json".
    name = (stem + base[len(can_stem):] + ext if base.startswith(can_stem)
            else f"{base}_{stem}{ext}")

    try:
        journal.resolve().relative_to(home.resolve())
        out_dir = home
    except (ValueError, OSError):
        out_dir = journal.parent
    return out_dir / name
