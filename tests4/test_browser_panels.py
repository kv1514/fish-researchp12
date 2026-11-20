"""The end-of-game panels, in a browser that actually does layout.

``tests4/js/`` drives ``public/app.js`` against a DOM stub. That is fast, it
covers the logic, and it is structurally blind to layout: a stub element has
no width, so nothing can overflow it. The first run of this file at a 390px
viewport found the page scrolling 233px sideways, from two independent causes
that had been live for as long as the round table has:

  * ``.pacebar`` was ``display: flex`` with no ``flex-wrap``. Pause, Next, the
    pace slider, Voice, Think and the auto checkbox measure 467px in a row.
  * ``.felt`` combines ``aspect-ratio: 15/10`` with ``min-height: 340px``,
    which together imply a MINIMUM WIDTH of 510px. As a grid item with the
    default ``min-width: auto`` it dragged its whole column out with it.

The engine is deliberately not in the loop. Two earlier attempts played a real
game and timed out at 180s under load, which measured the engine's speed
rather than the page. Here ``/api/**`` is intercepted and answered with a
finished game, so the page walks its own real code path from the start screen
to the three panels in about a second.

Skipped, not failed, where Chromium or Playwright is absent: this is the one
suite with a dependency outside the repository.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests4" / "browser" / "panels.mjs"
GLOBAL_MODULES = "/opt/node22/lib/node_modules"


def _have(cmd) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(
    not _have(["node", "-e",
               f"require('module').createRequire('{GLOBAL_MODULES}/')"
               f"('playwright')"]),
    reason="playwright is not installed for this node")


@pytest.fixture(scope="module")
def site():
    """Serve public/ on a free port for the life of the module."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = partial(http.server.SimpleHTTPRequestHandler,
                      directory=str(ROOT / "public"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def test_panels_paint_and_the_page_does_not_scroll_sideways(site):
    env = dict(os.environ, BASE=site)
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True,
                       timeout=300, env=env, cwd=str(ROOT))
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert out.strip().startswith("ok"), out
