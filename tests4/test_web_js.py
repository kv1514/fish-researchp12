"""Run the browser-side checks under node, from the same suite as everything else.

The table's JavaScript had two defects that no Python test could reach, because
both were about WHEN a value is read rather than about what any endpoint
returns: a stale analysis surviving a new deal (which pre-filled the declare
dialog from the previous game's assignment, and is how a player voids a set
they hold), and an in-flight analysis landing on a position the player had
already moved past.

``tests4/js/`` holds a DOM stub thin enough to load ``public/app.js`` and drive
its handlers. Keeping it behind a pytest wrapper means it runs whenever the
suite runs, rather than whenever someone remembers.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "tests4" / "js"

SUITES = sorted(p.name for p in JS.glob("test_*.js"))


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="node is not installed")
@pytest.mark.parametrize("suite", SUITES)
def test_browser_suite(suite):
    r = subprocess.run(["node", str(JS / suite)], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_there_is_at_least_one_browser_suite():
    """A parametrised test over an empty list passes by running nothing."""
    assert SUITES, f"no test_*.js under {JS}"
