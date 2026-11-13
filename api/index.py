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
import time
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
from api import _tables as T                                   # noqa: E402
from api import _profiles as P                                 # noqa: E402
from api import _auth as A                                     # noqa: E402

MAX_BODY = 512 * 1024

#: Origins allowed to call the API from another origin: the native app shells.
#: A Capacitor build serves its bundled pages from these, not from this site,
#: so every request it makes is cross-origin. Nothing here uses cookies -- a
#: seat is identified by a secret in the request body -- so this widens no
#: credentialed surface; it is an allowlist rather than "*" only so the API
#: does not quietly become everybody's backend.
APP_ORIGINS = frozenset({
    "capacitor://localhost",     # iOS
    "ionic://localhost",         # older iOS shells
    "https://localhost",         # Android
    "http://localhost",          # Android, cleartext dev builds
})


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
    if not op:
        op = path
    op = op.strip("/").split("/")[-1]
    # AND THE EXTENSION COMES OFF, because the deployed platform routes on the
    # PATH and not on the ?op= this file asks it to carry. /api/health works
    # either way -- with or without the query, the last segment is "health" --
    # so nothing revealed the difference until a rewrite whose SOURCE has an
    # extension arrived: /paper.pdf reached the function as "paper.pdf", missed
    # every route, and returned a 404 that looked like a missing file rather
    # than a missing route. Dropping it here keeps the dev server and the
    # deployment agreeing on one spelling instead of the route carrying two.
    # No route name contains a dot.
    return op.rsplit(".", 1)[0] if "." in op else op


class handler(BaseHTTPRequestHandler):

    # -- plumbing -------------------------------------------------------------

    def _cors(self) -> None:
        origin = (self.headers.get("Origin") or "").strip()
        if origin in APP_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, obj, code: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """CORS preflight. A JSON POST from the app shell triggers one."""
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_file(self, path: Path, ctype: str, cache: str):
        """Stream a file from the deployment bundle.

        Vercel serves public/ statically and everything else only through this
        function, so a file that must stay in ONE place in the repository -- the
        paper, which paper/build.sh writes next to its own sources -- can still
        be served without committing a second copy that drifts. vercel.json's
        includeFiles has to name it or it is not in the bundle at all; the
        smoke test in tests4/test_paper_route.py is what notices if it stops
        being.
        """
        try:
            data = path.read_bytes()
        except OSError:
            return self._send({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition",
                         f'inline; filename="{path.name}"')
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

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
            if op == "paper":
                # The paper itself, at /paper.pdf via vercel.json's rewrite.
                # Cached at the edge rather than in the browser: a deploy
                # purges the CDN, so a reader gets the new build the first
                # time anyone asks for it after a push, and max-age=0 keeps a
                # browser from holding a stale copy past that.
                return self._send_file(
                    ROOT / "paper" / "kraken.pdf", "application/pdf",
                    "public, max-age=0, s-maxage=3600, "
                    "stale-while-revalidate=86400")

            if op == "health":
                # room_backend is reported because the difference matters and
                # is otherwise invisible: on "memory" a room works for exactly
                # one player, which looks like a bug in the game rather than a
                # deployment that has no shared store configured.
                #
                # `paper` is here for the same reason and was learnt the same
                # way. Whether the PDF reached the bundle depends on
                # vercel.json's includeFiles AND on .vercelignore, neither of
                # which fails at build time -- the first deploy of the route
                # 404ed on the live site while every local check passed. One
                # boolean here says which side of that a deployment is on.
                return self._send({"ok": True,
                                   "room_backend": _rooms.backend_name(),
                                   "paper": (ROOT / "paper"
                                             / "kraken.pdf").exists()})
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
            # Identity checks, not `in`: membership uses ==, and 0 == False in
            # Python, so `step: 0` used to mean NO cap -- a request for zero
            # engine moves played every engine move up to the person's turn.
            cap = (None if step is None or step is False or step == ""
                   else int(step))
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

            if op.startswith("t_"):
                return self._table(op, body)

            if op.startswith("p_"):
                return self._profile(op, body)

            if op.startswith("a_"):
                return self._account(op, body)

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

            if op == "claimcheck":
                # The player's own split, priced before they commit. See
                # Session.claim_check for why this is not a leak.
                try:
                    return self._send(s.claim_check(
                        body.get("half_suit"), body.get("assignment") or []))
                except (ValueError, TypeError) as e:
                    return self._send({"error": str(e)}, 400)

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

    # -- tables (the poker-style app) -----------------------------------------

    def _table(self, op: str, body: dict):
        """Every /api/t_* route: public quick play, join codes, turn clocks.

        Each route identifies the caller by their seat secret and hands back
        that seat's view and nothing else. Polling (`t_state`) also drives the
        table -- bot moves and expired clocks happen on being looked at -- and
        writes only when something actually changed.
        """
        _rooms.require_shared_store()
        now = time.time()
        try:
            if op == "t_list":
                return self._send({"tables": T.open_tables()})

            name = body.get("name", "")
            card = None
            if op in ("t_quick", "t_create", "t_join") and body.get("pid"):
                # A profile rides along when the app has one. A bad one is
                # refused rather than silently dropped, so the app can make a
                # fresh profile instead of playing unrated without knowing.
                try:
                    if P.profiles() is not None:
                        prof = P.auth(body.get("pid"), body.get("psecret"))
                        card, name = P.seat_card(prof), prof.get("name", name)
                except ValueError as e:
                    return self._send({"error": str(e),
                                       "profile_invalid": True}, 403)

            if op == "t_quick":
                code, seat, secret, doc, v = T.quick_play(name, card=card)
                return self._send({"code": code, "secret": secret,
                                   "table": T.view(doc, code, seat, v)})

            if op == "t_create":
                code, seat, secret, doc = T.create(
                    name, bool(body.get("public", False)),
                    body.get("turn", T.TURN_DEFAULT),
                    body.get("pace", T.PACE_DEFAULT), card=card)
                return self._send({"code": code, "secret": secret,
                                   "table": T.view(doc, code, seat, 1)})

            code = str(body.get("code") or "").strip().upper()[:8]
            if not code:
                return self._send({"error": "missing table code"}, 400)

            if op == "t_join":
                def _join(d):
                    T.tick(d, now)
                    return T.join(d, name, now=now, card=card), True
                doc, out, v = T.mutate(code, _join)
                return self._send({"code": code, "secret": out["secret"],
                                   "table": T.view(doc, code, out["seat"], v)})

            secret = str(body.get("secret") or "")

            if op == "t_state":
                def _poll(d):
                    me = T.seat_of(d, secret)
                    if me is None:
                        raise ValueError("you are not seated at that table")
                    seen = T.touch(d, me, now)
                    moved = T.tick(d, now)
                    return me, (seen or moved)
                doc, me, v = T.mutate(code, _poll)
                doc, v = T.maybe_settle(code, doc, v)
                return self._send({"table": T.view(doc, code, me, v)})

            if op == "t_leave":
                T.mutate(code, lambda d: (T.leave(d, secret, now=now), True))
                return self._send({"left": True})

            if op == "t_act":
                action = parse_action(body.get("action") or {})
                lost = bool(body.get("focus_lost"))
                fn = lambda d: (T.act(d, secret, action, now=now,  # noqa: E731
                                      focus_lost=lost), True)
            elif op == "t_start":
                fn = lambda d: (T.start(d, secret, now=now), True)  # noqa: E731
            elif op == "t_rematch":
                fn = lambda d: (T.rematch(d, secret, now=now), True)  # noqa: E731
            elif op == "t_sit":
                fn = lambda d: (T.sit(d, secret, body.get("seat", -1),  # noqa: E731
                                      now=now), True)
            elif op == "t_seat":
                fn = lambda d: (T.set_seat_kind(  # noqa: E731
                    d, secret, body.get("seat", -1), body.get("kind"),
                    now=now), True)
            elif op == "t_kick":
                fn = lambda d: (T.kick(d, secret, body.get("seat", -1),  # noqa: E731
                                       now=now), True)
            elif op == "t_settings":
                fn = lambda d: (T.update_settings(  # noqa: E731
                    d, secret, body.get("turn"), body.get("pace"),
                    now=now), True)
            elif op == "t_emote":
                fn = lambda d: (T.emote(d, secret, str(body.get("emote")),  # noqa: E731
                                        now=now), True)
            elif op == "t_back":
                fn = lambda d: (T.back(d, secret, now=now), True)  # noqa: E731
            else:
                return self._send({"error": "not found"}, 404)

            doc, _, v = T.mutate(code, fn)
            doc, v = T.maybe_settle(code, doc, v)
            return self._send({"table": T.view(doc, code,
                                               T.seat_of(doc, secret), v)})
        except _rooms.NotFound:
            return self._send({"error": "no such table"}, 404)
        except RuntimeError as e:
            # Raised only with messages written to be shown: a lost race
            # ("the table is busy") or the store being unreachable.
            return self._send({"error": str(e)}, 503)

    # -- profiles ------------------------------------------------------------

    def _profile(self, op: str, body: dict):
        """Every /api/p_* route: profiles, the leaderboard, and fair-play review.

        A profile is identified by its public id and proved by its secret, the
        same shape as a table seat. The review routes need FISH_ADMIN_KEY and
        are a plain 404 without it, so their existence is not advertised.
        """
        try:
            pid = str(body.get("id") or "")
            psec = str(body.get("secret") or "")
            if op == "p_get":
                return self._send({"profile": P.get(pid)})
            if op == "p_top":
                return self._send({"players": P.leaderboard(50)})
            if op == "p_rename":
                return self._send({"profile": P.rename(pid, psec,
                                                       body.get("name"))})
            if op == "p_me":
                return self._send({"profile": P.me(pid, psec)})
            if op == "p_logout":
                P.logout(pid, psec)
                return self._send({"logged_out": True})
            if op == "p_delete":
                P.delete(pid, psec)
                return self._send({"deleted": True})
            if op == "p_report":
                P.report(pid, psec, str(body.get("target") or ""),
                         body.get("reason"))
                return self._send({"reported": True})
            if op in ("p_review", "p_clear", "p_ban"):
                if not P.admin_ok(body.get("admin")):
                    return self._send({"error": "not found"}, 404)
                if op == "p_review":
                    return self._send({"queue": P.review_queue(50)})
                if op == "p_clear":
                    P.clear(pid)
                    return self._send({"cleared": True})
                return self._send(P.ban(pid))
            return self._send({"error": "not found"}, 404)
        except P.ProfilesUnavailable as e:
            return self._send({"error": str(e)}, 503)
        except _rooms.NotFound:
            return self._send({"error": "no such player"}, 404)
        except ValueError as e:
            return self._send({"error": str(e)}, 400)
        except RuntimeError as e:
            return self._send({"error": str(e)}, 503)

    # -- accounts ------------------------------------------------------------

    #: Where a Google sign-in may return to: the web app, or the iOS app's own
    #: link. Supabase checks its own allowlist too; this one keeps the server
    #: from minting sign-in links that land anywhere else.
    OAUTH_RETURNS = ("https://fish-engine.vercel.app/play/", "fish://auth",
                     "http://127.0.0.1:8420/play/")

    def _account(self, op: str, body: dict):
        """Every /api/a_* route: sign up, sign in, and the sign-in options.

        Each successful sign-in ends the same way -- the account's profile,
        and a fresh secret for THIS device -- so the rest of the app never
        needs to know how someone signed in.
        """
        def done(user):
            pid, secret, doc = P.sign_in(user, body.get("name"),
                                         A.login_label(user)
                                         if isinstance(user, dict) else "")
            return self._send({"id": pid, "secret": secret,
                               "profile": dict(P.public(doc),
                                               login=doc.get("login", ""))})
        try:
            if op == "a_config":
                return self._send({"accounts": A.config()})
            if op == "a_signup":
                # The name first: checked after the account exists, a blank
                # one would leave an account with no profile behind it.
                if not _rooms.clean_name(body.get("name"), ""):
                    return self._send({"error": "pick a name"}, 400)
                user = A.signup_email(body.get("email"), body.get("password"))
                if user is None:
                    return self._send({"confirm": True})
                return done(user)
            if op == "a_login":
                user = A.login_email(body.get("email"), body.get("password"))
                if not body.get("name"):
                    body = dict(body, name=A.suggested_name(user))
                return done(user)
            if op == "a_phone_start":
                A.phone_start(body.get("phone"))
                return self._send({"sent": True})
            if op == "a_phone_verify":
                return done(A.phone_verify(body.get("phone"), body.get("code")))
            if op == "a_oauth":
                back = str(body.get("redirect_to") or "")
                if back not in self.OAUTH_RETURNS:
                    return self._send({"error": "unknown return address"}, 400)
                return self._send({"url": A.oauth_url(
                    str(body.get("provider") or ""), back)})
            if op == "a_token":
                user = A.from_token(body.get("access_token"))
                if not body.get("name"):
                    body = dict(body, name=A.suggested_name(user))
                return done(user)
            return self._send({"error": "not found"}, 404)
        except (A.AuthUnavailable, P.ProfilesUnavailable) as e:
            return self._send({"error": str(e)}, 503)
        except ValueError as e:                 # includes A.AuthError
            return self._send({"error": str(e)}, 400)
        except RuntimeError as e:
            return self._send({"error": str(e)}, 503)

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

        if op == "room_claimcheck":
            # Same posture as room_analyse: read-only, and it must not tick
            # the clock. Pricing a split you are considering is not a move.
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
            try:
                return self._send(RG.session_for(doc, me).claim_check(
                    body.get("half_suit"), body.get("assignment") or []))
            except (ValueError, TypeError) as e:
                return self._send({"error": str(e)}, 400)

        return self._send({"error": "not found"}, 404)

    def log_message(self, *args):                    # quieter function logs
        pass
