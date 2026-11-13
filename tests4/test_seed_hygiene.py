"""No queued experiment may share deals with a different experiment.

``scripts4/check_seeds.py`` is the tool; this makes it a gate. The failure it
guards against does not announce itself: two runs on overlapping ``base_seed``
ranges play some of the same deals, so they are correlated, and every
pre-registration in this project claims fresh seeds. It already happened once --
the retake-gate cells were checked against every recorded result and passed,
never having been compared against the other jobs queued beside them.

Two assertions, and the second is the one that would be a wrong number rather
than a wrong claim: a pooled estimate over correlated cells has a standard error
smaller than the truth, so no analysis here may average two cells that share a
deal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from check_seeds import POOLS, load                          # noqa: E402


def test_no_queued_cell_collides_with_another_experiment():
    cells = load()
    live = []
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            if b[2] >= a[3]:
                break
            if a[1] == b[1] or (a[0] == b[0] and a[0] != "legacy"):
                continue
            if a[4] or b[4]:
                live.append((a[1], a[2], b[1], b[2]))
    assert not live, f"queued cells share deals across experiments: {live}"


def test_no_pool_averages_two_cells_that_share_a_deal():
    cells = load()
    bad = {}
    for name, labels in POOLS.items():
        members = [c for c in cells if c[1] in labels]
        clash = [(a[1], b[1]) for i, a in enumerate(members)
                 for b in members[i + 1:] if a[2] < b[3] and b[2] < a[3]]
        if clash:
            bad[name] = clash
    assert not bad, f"pooled cells share deals: {bad}"


def test_every_pool_names_cells_that_exist_somewhere():
    """A pool whose labels match nothing is a check that silently passes."""
    known = {c[1] for c in load()}
    missing = {name: [l for l in labels if l not in known]
               for name, labels in POOLS.items()}
    missing = {k: v for k, v in missing.items() if len(v) == len(POOLS[k])}
    assert not missing, f"pools matching no cell at all: {missing}"


def test_check_seeds_script_runs_clean():
    r = subprocess.run([sys.executable, "scripts4/check_seeds.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_engine_fingerprint_names_files_that_exist():
    """A fingerprint over a renamed file records MISSING, not a hash.

    That is deliberate -- silently shrinking what is fingerprinted would be
    worse -- but it means a rename degrades the record until someone notices.
    This is the noticing.
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts4"))
    from duel import FINGERPRINTED, engine_fingerprint
    gone = [k for k, v in engine_fingerprint()["files"].items()
            if v == "MISSING"]
    assert not gone, f"fingerprinted files that do not exist: {gone}"
    assert len(FINGERPRINTED) >= 8, "the fingerprint has been narrowed"
