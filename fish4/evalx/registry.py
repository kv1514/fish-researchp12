"""Append-only experiment registry (v0.4).

Modelled on ``fish/registry.py``, hardened in four places that mattered:

1. SCHEMA VERSION on every line. v0.3's registry grew fields over time and
   old lines silently lack them, so any reader has to guess. Every record
   here declares ``schema``, and ``verify()`` refuses to load a file
   containing a version it does not know.

2. ATOMIC APPEND. v0.3 opened the file in text-append mode and wrote through
   Python's buffered layer with no lock and no fsync. Two scripts running at
   once (which is the normal state of this project, given the 4-worker runs)
   could interleave partial lines and corrupt the record permanently. Here a
   record is serialized to a single line, an exclusive lock is taken on a
   sidecar lock file, and the line goes out as ONE ``os.write`` to an
   O_APPEND handle followed by ``os.fsync``.

3. BOTH SEED STREAMS, EXPLICITLY. Reproducing a matchup needs the deal seed
   base AND the agent seed base; they are deliberately independent (see the
   integrity note in ``fish/runner.py``) and recording only one makes a
   record un-rerunnable. ``seeds`` is a required, non-empty field.

4. RETRACTION INSTEAD OF DELETION. A result that turns out to be wrong must
   stay visible, because it was probably cited somewhere. ``retract()``
   appends a retraction record naming the target and the reason; nothing is
   ever rewritten or removed, and ``load_all`` folds retractions into the
   records they target so a reader cannot miss one. This is the mechanism the
   v0.3 ratings retraction had to be done by hand in a Markdown file.

CLI::

    py -m fish4.evalx.registry --list
    py -m fish4.evalx.registry --show <id>
    py -m fish4.evalx.registry --retract <id> --reason "confounded ablation"
    py -m fish4.evalx.registry --verify
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "results" / "experiments_v04.jsonl"

SCHEMA_VERSION = "evalx-registry/1"
KNOWN_SCHEMAS = {SCHEMA_VERSION}

#: Deliberately short and ordered. A tier is a claim about how much weight a
#: number can carry, not a mood.
EVIDENCE_TIERS = ("DEMONSTRATED", "PROMISING", "SPECULATIVE", "EXPLORATORY")

RECORD_KIND = "experiment"
RETRACTION_KIND = "retraction"


class RegistryError(Exception):
    """The registry file is not something we are willing to read or extend."""


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def _git(*args) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=str(ROOT), text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:                                      # noqa: BLE001
        return ""


#: Shelling out to git costs ~0.2s per call on Windows, and a script that
#: records many experiments in a burst would spend most of its time in
#: subprocess spawn. Provenance is therefore cached for a few seconds: long
#: enough to collapse a burst into one call, short enough that a run which
#: edits files between experiments still records the change.
_PROVENANCE_TTL_S = 5.0
_prov_cache: dict = {}


def _cached(key: str, fn):
    now = time.time()
    hit = _prov_cache.get(key)
    if hit is not None and now - hit[0] < _PROVENANCE_TTL_S:
        return hit[1]
    val = fn()
    _prov_cache[key] = (now, val)
    return val


def git_commit() -> str:
    return _cached("commit",
                   lambda: (_git("rev-parse", "HEAD") or "unknown")[:12])


def _git_status_uncached() -> tuple:
    out = _git("status", "--porcelain")
    if not out:
        # Distinguish "clean" from "git failed": rev-parse succeeding means
        # we really are in a repo and really did see an empty status.
        if _git("rev-parse", "--git-dir"):
            return (False, 0)
        return (True, -1)
    return (True, len([ln for ln in out.splitlines() if ln.strip()]))


def git_status() -> tuple:
    """Return ``(dirty, n_changed_files)``.

    Unknown git state counts as DIRTY. Assuming clean when we cannot tell is
    the mistake that turns "reproducible from this commit" into a false claim.
    """
    return _cached("status", _git_status_uncached)


# ---------------------------------------------------------------------------
# Atomic append
# ---------------------------------------------------------------------------

class _FileLock:
    """Cross-platform exclusive lock on a sidecar file.

    ``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere. The lock is
    advisory and only guards writers of this registry, which is all we need:
    readers tolerate a torn final line by design (``load_all`` skips
    unparseable lines).
    """

    def __init__(self, path: Path, timeout: float = 30.0):
        self.path = Path(str(path) + ".lock")
        self.timeout = timeout
        self._fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.time() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() > deadline:
                    raise RegistryError(
                        f"could not acquire {self.path} within {self.timeout}s")
                time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
        return False


def _append_line(path: Path, obj: dict) -> None:
    blob = (json.dumps(obj, separators=(",", ":"), default=str) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(path):
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, blob)          # one write, one line
            os.fsync(fd)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------

@dataclass
class ExperimentRecord:
    """One experiment, in enough detail to re-run it from the commit alone."""

    name: str
    kind: str = "matchup"          # matchup | ablation | benchmark | calibration
    agent_specs: dict = field(default_factory=dict)   # {"x": [...], "y": [...]}
    harness_config: dict = field(default_factory=dict)
    seeds: dict = field(default_factory=dict)         # both streams, required
    result: dict = field(default_factory=dict)        # includes CIs
    wall_clock_s: float = 0.0
    evidence_tier: str = "PROMISING"
    notes: str = ""

    # filled by finalize()
    id: str = ""
    schema: str = SCHEMA_VERSION
    record_kind: str = RECORD_KIND
    created: str = ""
    commit: str = ""
    dirty_worktree: bool = True
    dirty_files: int = -1
    python: str = ""
    platform_: str = ""

    def finalize(self) -> "ExperimentRecord":
        if self.evidence_tier not in EVIDENCE_TIERS:
            raise RegistryError(
                f"evidence_tier {self.evidence_tier!r} is not one of "
                f"{EVIDENCE_TIERS}")
        if not self.seeds:
            raise RegistryError(
                "seeds is required and must name BOTH streams (deal and "
                "agent); a record without them cannot be re-run")
        self.id = self.id or uuid.uuid4().hex[:12]
        self.created = self.created or time.strftime("%Y-%m-%dT%H:%M:%S")
        self.commit = self.commit or git_commit()
        self.dirty_worktree, self.dirty_files = git_status()
        self.python = sys.version.split()[0]
        self.platform_ = platform.platform()
        return self

    def to_dict(self) -> dict:
        d = asdict(self)
        d["platform"] = d.pop("platform_")
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentRecord":
        d = dict(d)
        d["platform_"] = d.pop("platform", "")
        d.pop("retracted", None)
        d.pop("retraction", None)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def record(rec: ExperimentRecord, path: Path = REGISTRY_PATH) -> ExperimentRecord:
    """Append a finalized experiment record. Never overwrites anything."""
    rec.finalize()
    _append_line(Path(path), rec.to_dict())
    return rec


def retract(experiment_id: str, reason: str, by: str = "",
            path: Path = REGISTRY_PATH) -> dict:
    """Mark an experiment retracted by APPENDING a retraction record.

    The original line stays byte-identical. Readers see the retraction
    because ``load_all`` folds it in; a reader that ignores retractions is a
    reader bug, not a registry one, which is why ``summary`` shows them in
    the leftmost column.
    """
    if not reason.strip():
        raise RegistryError("a retraction must state a reason")
    rows = _read_raw(Path(path))
    targets = [r for r in rows if r.get("id") == experiment_id
               and r.get("record_kind", RECORD_KIND) == RECORD_KIND]
    if not targets:
        raise RegistryError(f"no experiment with id {experiment_id!r} in {path}")
    entry = {
        "schema": SCHEMA_VERSION,
        "record_kind": RETRACTION_KIND,
        "id": uuid.uuid4().hex[:12],
        "targets": experiment_id,
        "reason": reason.strip(),
        "by": by or os.environ.get("USERNAME") or os.environ.get("USER") or "",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "commit": git_commit(),
    }
    _append_line(Path(path), entry)
    return entry


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read_raw(path: Path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"[registry] line {i + 1} of {p} is unparseable and was "
                  f"skipped (torn write from an interrupted run?)",
                  file=sys.stderr)
    return rows


def load_all(path: Path = REGISTRY_PATH, include_retracted: bool = True) -> list:
    """Return experiment dicts with retractions folded in.

    Retracted records carry ``retracted=True`` and a ``retraction`` block.
    They are included by default: hiding them would recreate exactly the
    problem retraction exists to solve.
    """
    rows = _read_raw(path)
    retractions: dict = {}
    for r in rows:
        if r.get("record_kind") == RETRACTION_KIND:
            retractions.setdefault(r["targets"], []).append(r)
    out = []
    for r in rows:
        if r.get("record_kind", RECORD_KIND) != RECORD_KIND:
            continue
        r = dict(r)
        rs = retractions.get(r.get("id"), [])
        r["retracted"] = bool(rs)
        r["retraction"] = rs[0] if rs else None
        if r["retracted"] and not include_retracted:
            continue
        out.append(r)
    return out


def get(experiment_id: str, path: Path = REGISTRY_PATH) -> Optional[dict]:
    for r in load_all(path):
        if r.get("id") == experiment_id:
            return r
    return None


def verify(path: Path = REGISTRY_PATH) -> list:
    """Structural check. Returns a list of problem strings (empty == fine)."""
    problems = []
    rows = _read_raw(path)
    seen = set()
    ids = {r.get("id") for r in rows
           if r.get("record_kind", RECORD_KIND) == RECORD_KIND}
    for i, r in enumerate(rows, 1):
        schema = r.get("schema")
        if schema not in KNOWN_SCHEMAS:
            problems.append(f"line {i}: unknown schema {schema!r}")
        kind = r.get("record_kind", RECORD_KIND)
        if kind == RETRACTION_KIND:
            if r.get("targets") not in ids:
                problems.append(f"line {i}: retraction targets unknown id "
                                f"{r.get('targets')!r}")
            if not r.get("reason"):
                problems.append(f"line {i}: retraction has no reason")
            continue
        rid = r.get("id")
        if not rid:
            problems.append(f"line {i}: record has no id")
        elif rid in seen:
            problems.append(f"line {i}: duplicate id {rid}")
        seen.add(rid)
        if r.get("evidence_tier") not in EVIDENCE_TIERS:
            problems.append(f"line {i}: bad evidence_tier "
                            f"{r.get('evidence_tier')!r}")
        if not r.get("seeds"):
            problems.append(f"line {i}: no seed streams recorded")
    return problems


def summary(path: Path = REGISTRY_PATH) -> str:
    rows = load_all(path)
    if not rows:
        return f"no experiments recorded in {path}"
    lines = [f"{'':1s} {'id':13s} {'when':20s} {'kind':11s} "
             f"{'tier':13s} {'commit':13s} name"]
    for r in rows:
        flag = "R" if r["retracted"] else ("*" if r.get("dirty_worktree") else " ")
        lines.append(f"{flag} {r.get('id', ''):13s} {r.get('created', ''):20s} "
                     f"{r.get('kind', ''):11s} {r.get('evidence_tier', ''):13s} "
                     f"{r.get('commit', ''):13s} {r.get('name', '')}")
        if r["retracted"]:
            lines.append(f"    RETRACTED: {r['retraction']['reason']}")
    lines.append("\nR = retracted (kept on purpose; it was probably cited)")
    lines.append("* = recorded from a modified working tree "
                 "(not exactly reproducible from the commit alone)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience: build a record straight from a harness result
# ---------------------------------------------------------------------------

def record_paired_result(name: str, result, evidence_tier: str = "PROMISING",
                         kind: str = "matchup", notes: str = "",
                         extra: Optional[dict] = None,
                         path: Path = REGISTRY_PATH) -> ExperimentRecord:
    """Turn a ``harness.PairedResult`` into a registry record.

    Pulls both seed streams and the full agent specs out of the harness
    config so callers cannot forget them.
    """
    cfg = result.config
    res = result.to_dict()
    if extra:
        res = {**res, **extra}
    return record(ExperimentRecord(
        name=name, kind=kind,
        agent_specs={"x": [cfg.spec_x[0], dict(cfg.spec_x[1])],
                     "y": [cfg.spec_y[0], dict(cfg.spec_y[1])]},
        harness_config=cfg.to_dict(),
        seeds={"deal_seed_base": cfg.base_seed,
               "agent_seed_base": cfg.agent_seed_base,
               "seat_offsets": list(cfg.seat_offsets)},
        result=res, wall_clock_s=result.wall_clock_s,
        evidence_tier=evidence_tier, notes=notes), path=path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="v0.4 experiment registry")
    ap.add_argument("--path", default=str(REGISTRY_PATH))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show", metavar="ID")
    ap.add_argument("--retract", metavar="ID")
    ap.add_argument("--reason", default="")
    ap.add_argument("--by", default="")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args(argv)
    path = Path(args.path)

    if args.retract:
        if not args.reason:
            print("--retract requires --reason", file=sys.stderr)
            return 2
        entry = retract(args.retract, args.reason, by=args.by, path=path)
        print(f"retracted {args.retract}: {entry['reason']}")
        return 0
    if args.show:
        rec = get(args.show, path)
        if rec is None:
            print(f"no experiment {args.show}", file=sys.stderr)
            return 1
        print(json.dumps(rec, indent=2))
        return 0
    if args.verify:
        problems = verify(path)
        if problems:
            print("\n".join(problems))
            return 1
        print(f"{path}: ok ({len(load_all(path))} experiments)")
        return 0
    print(summary(path))
    return 0


__all__ = ["SCHEMA_VERSION", "EVIDENCE_TIERS", "REGISTRY_PATH",
           "RegistryError", "ExperimentRecord", "record", "retract",
           "load_all", "get", "verify", "summary", "record_paired_result",
           "git_commit", "git_status", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
