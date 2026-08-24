"""Serve public/ plus the serverless api/ handler, for local checking.

Vercel runs api/index.py as a function and serves public/ as static files. This
reproduces that split in one process so the deployed behaviour can be exercised
without deploying, which is the only way to catch a routing mistake before it is
live.
"""
from __future__ import annotations

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.index import handler as ApiHandler  # noqa: E402

PUBLIC = ROOT / "public"


class Dev(SimpleHTTPRequestHandler):
    """Serve public/ and hand /api/* to the deployed function's own routing.

    The route bodies call helpers on ``self``, so those helpers have to be
    reachable here. This used to name them one at a time::

        _send = ApiHandler._send
        _body = ApiHandler._body

    which meant every helper added to the deployed handler had to be
    remembered here as well -- and the first one that was not, ``_room``, made
    every room route return a 500 locally while working in production. A dev
    server that diverges from the deployed one is worse than no dev server,
    because it is trusted.

    So the delegation is generic: anything this class does not define, and
    ``SimpleHTTPRequestHandler`` does not either, is looked up on the deployed
    handler and bound to this connection. Adding a route helper now needs no
    change here at all.
    """

    def __getattr__(self, name):
        # Only reached when normal lookup fails, so nothing on
        # SimpleHTTPRequestHandler is shadowed. Dunders are excluded: letting
        # them through would answer protocol probes (__deepcopy__, __iter__)
        # with a bound method that happens to exist on the other class.
        if name.startswith("__"):
            raise AttributeError(name)
        fn = getattr(ApiHandler, name, None)
        if fn is None:
            raise AttributeError(name)
        return fn.__get__(self, type(self)) if callable(fn) else fn

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    def _api(self, verb):
        # Borrow the function's routing, bound to this live connection.
        fn = getattr(ApiHandler, verb)
        return fn(self)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("do_GET")
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("do_POST")
        self.send_error(405)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    print(f"http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Dev).serve_forever()
