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
    # The function's route bodies call these helpers on ``self``, so they have to
    # exist here too. Borrowing the functions keeps one implementation of the
    # response format, rather than a dev copy that can drift from the deployed one.
    _send = ApiHandler._send
    _body = ApiHandler._body

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
