"""Every script a document tells you to run must exist.

A README that names a script which was renamed or deleted is the same failure
mode as a paper quoting a number its results file no longer holds: it reads
exactly like a working instruction. The listing in README.md grew by twenty
entries in one session, and nothing else checks any of them.

Scope is deliberately narrow -- the existence of the file, not whether the
command works -- because running them is hours of compute. A path that is right
is not proof the invocation is; a path that is wrong is proof it is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

DOCS = [ROOT / "README.md",
        ROOT / "scripts4" / "browser" / "README.md",
        ROOT / "fish4" / "NEGATIVE_CLAIMS.md"]

#: "py scripts4/foo.py", "python scripts4/foo.py", or a bare path in backticks.
PATTERNS = [
    re.compile(r"\bpy(?:thon)?\s+(scripts4/[A-Za-z0-9_./-]+\.py)"),
    re.compile(r"`(scripts4/[A-Za-z0-9_./-]+\.py)`"),
    re.compile(r"`(fish4/[A-Za-z0-9_./-]+\.(?:py|md))`"),
    re.compile(r"`(jobs/[A-Za-z0-9_./-]+\.md)`"),
    re.compile(r"`(results/[A-Za-z0-9_./-]+\.json)`"),
]


def _referenced(doc: Path) -> set[str]:
    if not doc.exists():
        return set()
    text = doc.read_text(encoding="utf-8")
    out: set[str] = set()
    for rx in PATTERNS:
        out |= set(rx.findall(text))
    return out


@pytest.mark.parametrize("doc", DOCS, ids=lambda d: str(d.name))
def test_referenced_paths_exist(doc):
    missing = sorted(r for r in _referenced(doc) if not (ROOT / r).exists())
    assert not missing, f"{doc.relative_to(ROOT)} names files that do not exist: {missing}"


def test_the_patterns_actually_match_something():
    """A regex that matches nothing makes this whole file a no-op."""
    total = sum(len(_referenced(d)) for d in DOCS)
    assert total > 20, f"only {total} paths matched; the patterns have rotted"
