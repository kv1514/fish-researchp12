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

from fish.engine import IllegalAction                          # noqa: E402
from api._engine import (Session, new_session, parse_action,  # noqa: E402
                         wire_action)
from api import _rooms                                         # noqa: E402
from api import _room_game as RG                               # noqa: E402

MAX_BODY = 512 * 1024


def route_of(path: str, query: str) -> str:
    """The requested operation.

    Vercel's rewrite routes on the *destination* path, so by the time the
    function runs, ``self.path`` says ``/api/index`` and the original route is
    gone. vercel.json therefore carries it through as ``?op=``. Locally there is
    no rewrite and the path is intact, so fall back to its last segment - which
    keeps scripts4/devserve.py exercising the same code as production rather
    than a dev-only branch.
    """
    op = parse_qs(query or "").get("op", [None])[0]
    if op:
        return op.strip("/").split("/")[-1]
    return path.strip("/").split("/")[-1]


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
        u = urlparse(self.path)
        op = route_of(u.path, u.query)
        try:
            if op == "deck":
                from fish.cards import (HALF_SUIT_NAMES, card_name,
                                        half_suit_cards, is_red)
                return self._send({"half_suits": [
                    {"hs": h, "name": HALF_SUIT_NAMES[h],
                     "cards": [{"id": c, "name": card_name(c), "red": is_red(c)}
                               for c in half_suit_cards(h)]}
                    for h in range(len(HALF_SUIT_NAMES))]})
            if op == "health":
                # room_backend is reported because the difference matters and
                # is otherwise invisible: on "memory" a room works for exactly
                # one player, which looks like a bug in the game rather than a
                # deployment that has no shared store configured.
                return self._send({"ok": True,
                                   "room_backend": _rooms.backend_name()})
            return self._send({"error": "not found"}, 404)
        except Exception:                            # pragma: no cover
            traceback.print_exc()
            return self._send({"error": "internal error"}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        op = route_of(u.path, u.query)
        try:
            body = self._body()

            # A paced client asks for one engine move at a time and does the
            # waiting itself; one that omits the field gets the whole possession
            # in a single response, as before.
            step = body.get("step")
            cap = int(step) if step not in (None, "", False) else None
            capkw = {"max_moves": cap} if cap is not None else {}

            if op == "new":
                s = new_session(body)
                # Pacing has to cover the opening possession too. Without it the
                # first thing a player ever sees is the whole opening arriving as
                # one jump, which is the exact thing the pacing exists to prevent
                # at the moment it matters most.
                played = s.advance(cap) if cap is not None else s.advance()
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            # Rooms first. A room request is authenticated by its seat
            # SECRET and addressed by a room code; it never carries a session
            # token, because the server -- not the client -- holds the
            # authoritative log for a shared table. Dispatching after the token
            # check below rejected every room route with "missing session
            # token" before it reached the handler.
            if op.startswith("room_"):
                return self._room(op, body)

            # Every other route restores the session from the sealed token plus
            # the client's copy of the public action log.
            token = body.get("token")
            if not token:
                return self._send({"error": "missing session token"}, 400)
            s = Session.restore(token, body.get("actions") or [])

            if op == "state":
                return self._send(s.snapshot())

            if op == "analyse":
                return self._send(s.analysis())

            if op == "deduce":
                return self._send(s.deductions())

            if op == "act":
                if not s.snapshot()["your_turn"]:
                    return self._send({"error": "not your turn"}, 400)
                played = s.play(parse_action(body.get("action") or {}), **capkw)
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            if op == "step":
                # One engine move, for a paced table. Idempotent like every
                # other route: the log decides the position, so a repeated or
                # lost request costs nothing.
                snap = s.snapshot()
                if snap["your_turn"] or snap["terminal"]:
                    return self._send(snap)
                played = s.advance(cap if cap is not None else 1)
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            if op == "auto":
                if not s.snapshot()["your_turn"]:
                    return self._send({"error": "not your turn"}, 400)
                played = s.play(s.suggest(),
                                **({"max_moves": cap} if cap is not None else {}))
                out = s.snapshot()
                out["actions"] = played
                return self._send(out)

            return self._send({"error": "not found"}, 404)

        except _rooms.RoomsUnavailable as e:
            # 503, not 500: the deployment is missing configuration, the
            # request was fine, and retrying will not help until somebody sets
            # the variables. The message is safe to show by construction --
            # see the class docstring.
            return self._send({"error": str(e)}, 503)
        except (ValueError, IllegalAction) as e:
            # IllegalAction is NOT a ValueError, so without naming it here it
            # reached the handler below and its message was echoed to the
            # client. Those messages are statements about the on-turn player's
            # hidden hand ("cannot ask for a card you hold", "must hold a card
            # of the half-suit"), and replay lets a client choose who is on
            # turn, which made the error body an exact hand-membership oracle.
            return self._send({"error": str(e)}, 400)
        except Exception:                            # pragma: no cover
            # Never echo the exception text: an unexpected error deep in the
            # engine can carry hidden state in its message just as readily.
            traceback.print_exc()
            return self._send({"error": "internal error"}, 500)

    # -- rooms ---------------------------------------------------------------

    def _room(self, op: str, body: dict):
        """Every /api/room_* route.

        Split out so the solo routes above stay readable, and because rooms
        share one shape: identify the caller by their seat secret, mutate under
        compare-and-set, hand back that seat's view and nothing else.
        """
        # Fail here rather than three requests later on a different instance.
        _rooms.require_shared_store()

        if op == "room_new":
            doc = RG.new_room(body.get("humans", 2), body.get("name", ""),
                              body.get("pace", 12))
            host = doc["seats"][0]
            code = _rooms.store().create(doc)
            return self._send({"code": code, "seat": host["seat"],
                               "secret": host["secret"],
                               "room": RG.lobby_view(doc, code,
                                                     host["seat"])})

        code = str(body.get("code") or "").strip().upper()[:8]
        if not code:
            return self._send({"error": "missing room code"}, 400)

        if op == "room_join":
            name = body.get("name", "")
            try:
                doc, out = RG.mutate(code, lambda d: RG.join_room(d, name))
            except _rooms.NotFound:
                return self._send({"error": "no such room"}, 404)
            return self._send({"code": code, "seat": out["seat"],
                               "secret": out["secret"],
                               "room": RG.lobby_view(doc, code, out["seat"])})

        secret = str(body.get("secret") or "")

        # Every route below both reads and may WRITE, because a room advances
        # on being looked at: an engine move that is due fires on the next
        # request from anybody at the table. There is no daemon thread here to
        # do it, so the readers drive the clock -- and `next_move_at` in the
        # document is what stops them driving it faster than the pace.
        def with_room(fn):
            try:
                return RG.mutate(code, fn)
            except _rooms.NotFound:
                raise ValueError("no such room")

        if op == "room_state":
            def _tick(d):
                if RG.seat_of(d, secret) is None:
                    raise ValueError("you are not seated at that table")
                RG.maybe_start(d)
                RG.step_bot(d)
                return None
            doc, _ = with_room(_tick)
            me = RG.seat_of(doc, secret)
            return self._send(RG.table_view(doc, code, me)
                              if doc["phase"] == "playing"
                              else {"room": RG.lobby_view(doc, code, me),
                                    "phase": doc["phase"]})

        if op == "room_ready":
            want = bool(body.get("ready", True))
            def _rdy(d):
                RG.set_ready(d, secret, want)
                RG.maybe_start(d)
                return None
            doc, _ = with_room(_rdy)
            me = RG.seat_of(doc, secret)
            return self._send(RG.table_view(doc, code, me)
                              if doc["phase"] == "playing"
                              else {"room": RG.lobby_view(doc, code, me),
                                    "phase": doc["phase"]})

        if op == "room_rename":
            seat = int(body.get("seat", -1))
            name = body.get("name", "")
            doc, _ = with_room(lambda d: RG.rename(d, secret, seat, name))
            me = RG.seat_of(doc, secret)
            return self._send({"room": RG.lobby_view(doc, code, me),
                               "phase": doc["phase"]})

        if op == "room_act":
            action = parse_action(body.get("action") or {})
            def _act(d):
                me = RG.seat_of(d, secret)
                if me is None:
                    raise ValueError("you are not seated at that table")
                RG.apply_action(d, me, action)
                return None
            doc, _ = with_room(_act)
            return self._send(RG.table_view(doc, code,
                                            RG.seat_of(doc, secret)))

        if op == "room_analyse":
            # Read-only, and the one room route that does not tick the clock:
            # asking the engine what it thinks must not advance the game.
            try:
                _, doc = _rooms.store().read(code)
            except _rooms.NotFound:
                return self._send({"error": "no such room"}, 404)
            me = RG.seat_of(doc, secret)
            if me is None:
                return self._send({"error": "you are not seated at that "
                                            "table"}, 403)
            if doc["phase"] != "playing":
                return self._send({"error": "that table has not started"}, 400)
            return self._send(RG.session_for(doc, me).analysis())

        return self._send({"error": "not found"}, 404)

    def log_message(self, *args):                    # quieter function logs
        pass
