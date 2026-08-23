"""Vercel entry point: one function, every /api route.

Vercel's Python runtime hands each request to a ``BaseHTTPRequestHandler``
subclass named ``handler``. Routing lives here rather than in ``vercel.json`` so
that a single warm instance serves every endpoint - the engine import costs a
second or so of cold start, and splitting the API across files would pay that
per endpoint instead of once.
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api._engine import (Session, new_session, parse_action,  # noqa: E402
                         wire_action)

MAX_BODY = 512 * 1024


class handler(BaseHTTPRequestHandler):

    # -- plumbing -------------------------------------------------------------

    def _send(self, obj, code: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > MAX_BODY:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    # -- routes ---------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path.endswith("/deck"):
                from fish.cards import (HALF_SUIT_NAMES, card_name,
                                        half_suit_cards, is_red)
                return self._send({"half_suits": [
                    {"hs": h, "name": HALF_SUIT_NAMES[h],
                     "cards": [{"id": c, "name": card_name(c), "red": is_red(c)}
                               for c in half_suit_cards(h)]}
                    for h in range(len(HALF_SUIT_NAMES))]})
            if path.endswith("/health"):
                return self._send({"ok": True})
            return self._send({"error": "not found"}, 404)
        except Exception as e:                       # pragma: no cover
            traceback.print_exc()
            return self._send({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()

            if path.endswith("/new"):
                s = new_session(body)
                played = s.advance()
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            # Every other route restores the session from the sealed token plus
            # the client's copy of the public action log.
            token = body.get("token")
            if not token:
                return self._send({"error": "missing session token"}, 400)
            s = Session.restore(token, body.get("actions") or [])

            if path.endswith("/state"):
                return self._send(s.snapshot())

            if path.endswith("/analyse"):
                return self._send(s.analysis())

            if path.endswith("/act"):
                if not s.snapshot()["your_turn"]:
                    return self._send({"error": "not your turn"}, 400)
                played = s.play(parse_action(body.get("action") or {}))
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            if path.endswith("/auto"):
                if not s.snapshot()["your_turn"]:
                    return self._send({"error": "not your turn"}, 400)
                played = s.play(s.suggest())
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            return self._send({"error": "not found"}, 404)

        except ValueError as e:
            return self._send({"error": str(e)}, 400)
        except Exception as e:                       # pragma: no cover
            traceback.print_exc()
            return self._send({"error": str(e)}, 500)

    def log_message(self, *args):                    # quieter function logs
        pass
