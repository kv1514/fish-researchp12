"""A browser front end for FishBot v0.4: play it, and see what it is thinking.

Standard library only - ``http.server`` plus vanilla JavaScript - so it runs
anywhere Python does with no install step and no build. Start it with

    py -m fish4 serve

and open http://127.0.0.1:8420.

THE INFORMATION BOUNDARY, IN A UI
---------------------------------
A spectator is not a policy, so a UI may legitimately show things a player may
not. This one deliberately does not. Every payload is built from the *seat's*
``Observation``: you see your own hand, the public log, hand counts, and the
engine's posterior over the hidden cards - which is an inference from public
information, not a peek at it. The one exception is the end-of-game reveal,
after every card is public anyway.
"""

from __future__ import annotations

import json
import random
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from fish.cards import (CARD_NAMES, HALF_SUIT_NAMES, NUM_PLAYERS, card_id,
                        card_name, half_suit_cards, is_red, mask_to_cards,
                        team_of, teammates)
from fish.engine import (Ask, AskEvent, Claim, ClaimEvent, GameState, Pass,
                         PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig

STATIC = Path(__file__).resolve().parent / "static"
_games: dict = {}
_lock = threading.Lock()


class Session:
    """One human-vs-engine game, plus a persistent analyser for the human seat."""

    def __init__(self, seat: int, seed: int, rules: RuleConfig, gamma: float,
                 draws: int, opponent: str):
        from ..analyse import Analyser
        from ..cli import _load_value
        from ..registry4 import make_agent
        self.id = secrets.token_hex(6)
        self.seat = seat
        self.seed = seed
        self.rules = rules
        self.state = GameState.deal(rules, seed=seed)
        rng = random.Random(seed ^ 0x9E3779B9)
        spec = {"opponent_gamma": gamma} if opponent == "champion" else {}
        self.bots = {}
        for p in range(NUM_PLAYERS):
            if p == seat:
                continue
            self.bots[p] = make_agent(("fishbot4", dict(spec)))
            self.bots[p].begin_game(p, rules, rng.getrandbits(64))
        self.analyser = Analyser(rules, seat, value_model=_load_value(None),
                                 gamma=gamma, n_draws=draws,
                                 seed=rng.getrandbits(31))
        # "Let the engine move" must play the ACTUAL policy, claim rule and
        # endgame solver included, not a re-implementation of its move ranking.
        # A hand-rolled version here would never declare while an ask existed.
        self.helper = make_agent(("fishbot4", dict(spec)))
        self.helper.begin_game(seat, rules, rng.getrandbits(64))
        self.log: list = []

    # -- driving --------------------------------------------------------------

    def advance(self, cap: int = 500) -> None:
        """Let the engine play until it is the human's turn (or the game ends)."""
        n = 0
        while (not self.state.is_terminal and self.state.turn != self.seat
               and n < cap):
            p = self.state.turn
            ev = self.state.apply(
                p, self.bots[p].act(Observation.from_state(self.state, p)))
            self.log.append(_ev(ev))
            n += 1

    def act(self, action) -> dict:
        ev = self.state.apply(self.seat, action)
        self.log.append(_ev(ev))
        self.advance()
        return self.snapshot()

    # -- views ----------------------------------------------------------------

    def obs(self) -> Observation:
        return Observation.from_state(self.state, self.seat)

    def snapshot(self) -> dict:
        st = self.state
        a, b, nulls = st.scores()
        mine = team_of(self.seat)
        hand = st.hands[self.seat]
        return {
            "id": self.id, "seat": self.seat, "team": mine, "seed": self.seed,
            "turn": st.turn, "terminal": st.is_terminal,
            "your_turn": (not st.is_terminal) and st.turn == self.seat,
            "score": {"you": a if mine == 0 else b,
                      "them": b if mine == 0 else a, "nulled": nulls},
            "hand_counts": list(st.hand_counts()),
            "teammates": [p for p in teammates(self.seat) if p != self.seat],
            "set_winner": [
                None if w is None else
                ("ours" if w == mine else "theirs" if w in (0, 1) else "null")
                for w in st.set_winner],
            "half_suits": [
                {"index": i, "name": n,
                 "cards": [{"id": c, "name": card_name(c), "red": is_red(c),
                            "mine": bool(hand >> c & 1)}
                           for c in half_suit_cards(i)]}
                for i, n in enumerate(HALF_SUIT_NAMES[:len(st.set_winner)])],
            "hand": [{"id": c, "name": card_name(c), "red": is_red(c),
                      "hs": c // 6} for c in mask_to_cards(hand)],
            "log": self.log[-40:],
            "must_pass": bool(st.turn == self.seat and hand == 0
                              and not st.is_terminal),
            "reveal": ([[card_name(c) for c in mask_to_cards(h)]
                        for h in st.hands] if st.is_terminal else None),
        }

    def analysis(self) -> dict:
        if self.state.is_terminal:
            return {"terminal": True}
        seat_obs = Observation.from_state(self.state, self.seat)
        return self.analyser.analyse(seat_obs).to_dict()


def _ev(ev) -> dict:
    if isinstance(ev, AskEvent):
        return {"t": "ask", "asker": ev.asker, "target": ev.target,
                "card": card_name(ev.card), "ok": ev.success,
                "text": (f"P{ev.asker} asked P{ev.target} for "
                         f"{card_name(ev.card)} - "
                         f"{'got it' if ev.success else 'no'}")}
    if isinstance(ev, ClaimEvent):
        who = ("team " + str(ev.winner)) if ev.winner in (0, 1) else "nobody"
        return {"t": "claim", "claimer": ev.claimer, "hs": ev.half_suit,
                "winner": ev.winner,
                "text": (f"P{ev.claimer} declared "
                         f"{HALF_SUIT_NAMES[ev.half_suit]} - {who} scores"),
                "revealed": [f"{card_name(c)}=P{h}" for c, h in zip(
                    half_suit_cards(ev.half_suit), ev.revealed)]}
    return {"t": "pass", "text": f"P{ev.player} passed to P{ev.teammate}"}


# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "FishBot/0.4"

    def log_message(self, fmt, *a):     # quiet
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    def _file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            return self._json({"error": f"missing {path.name}"}, 404)
        self._send(path.read_bytes(), ctype)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        p = urlparse(self.path).path
        try:
            if p in ("/", "/index.html"):
                return self._file(STATIC / "index.html",
                                  "text/html; charset=utf-8")
            if p == "/app.js":
                return self._file(STATIC / "app.js",
                                  "application/javascript; charset=utf-8")
            if p == "/style.css":
                return self._file(STATIC / "style.css", "text/css")
            if p == "/cards.js":
                return self._file(STATIC / "cards.js",
                                  "application/javascript; charset=utf-8")
            if p == "/api/deck":
                from fish.cards import (HALF_SUIT_NAMES, card_name,
                                        half_suit_cards, is_red)
                return self._json({"half_suits": [
                    {"hs": h, "name": HALF_SUIT_NAMES[h],
                     "cards": [{"id": c, "name": card_name(c), "red": is_red(c)}
                               for c in half_suit_cards(h)]}
                    for h in range(len(HALF_SUIT_NAMES))]})
            if p == "/api/lobby":
                from .lobby import lobby
                return self._json({"rooms": lobby().listing()})
            if p.startswith("/api/room/"):
                return self._room_get(p, urlparse(self.path).query)
            parts = p.strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "game":
                g = _games.get(parts[2])
                if not g:
                    return self._json({"error": "no such game"}, 404)
                if len(parts) == 3:
                    return self._json(g.snapshot())
                if parts[3] == "analyse":
                    return self._json(g.analysis())
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            body = self._body()
            if p == "/api/new":
                return self._new(body)
            if p == "/api/room":
                return self._room_create(body)
            if p.startswith("/api/room/"):
                return self._room_post(p, body)
            parts = p.strip("/").split("/")
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "game":
                g = _games.get(parts[2])
                if not g:
                    return self._json({"error": "no such game"}, 404)
                if parts[3] == "act":
                    return self._act(g, body)
                if parts[3] == "auto":
                    return self._auto(g)
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    # -- handlers -------------------------------------------------------------

    def _new(self, body):
        seat = int(body.get("seat", 0)) % NUM_PLAYERS
        seed = body.get("seed")
        seed = random.randrange(1 << 30) if seed in (None, "") else int(seed)
        rules = RuleConfig(variant=body.get("variant", "54"),
                           claims_any_time=bool(body.get("any_time", False)))
        g = Session(seat, seed, rules, float(body.get("gamma", 0.35)),
                    int(body.get("draws", 320)),
                    body.get("opponent", "champion"))
        g.advance()
        with _lock:
            _games[g.id] = g
            for k in list(_games)[:-40]:      # keep the last 40 sessions
                _games.pop(k, None)
        return self._json(g.snapshot())

    def _act(self, g, body):
        kind = body.get("type")
        try:
            if kind == "ask":
                act = Ask(int(body["target"]), int(body["card"]))
            elif kind == "claim":
                act = Claim(int(body["half_suit"]),
                            tuple(int(x) for x in body["assignment"]))
            elif kind == "pass":
                act = Pass(int(body["teammate"]))
            else:
                return self._json({"error": "unknown action"}, 400)
        except (KeyError, ValueError, TypeError) as e:
            return self._json({"error": f"bad action: {e}"}, 400)
        try:
            return self._json(g.act(act))
        except Exception as e:
            return self._json({"error": str(e), "state": g.snapshot()}, 400)

    def _auto(self, g):
        if g.state.is_terminal or g.state.turn != g.seat:
            return self._json(g.snapshot())
        try:
            action = g.helper.act(g.obs())
        except Exception as e:
            return self._json({"error": f"engine found no move: {e}",
                               "state": g.snapshot()}, 400)
        return self._json(g.act(action))


# ---------------------------------------------------------------------------
# multiplayer rooms
# ---------------------------------------------------------------------------

def _room_routes(cls):
    from urllib.parse import parse_qs

    def _room_create(self, body):
        from .lobby import lobby
        rules = RuleConfig(variant=body.get("variant", "54"),
                           claims_any_time=bool(body.get("any_time", False)))
        seed = body.get("seed")
        seed = None if seed in (None, "") else int(seed)
        room = lobby().create(
            humans=int(body.get("humans", 1)),
            arrangement=body.get("arrangement", "one_team"),
            name=body.get("name", "anon"), rules=rules, seed=seed,
            gamma=float(body.get("gamma", 0.35)),
            bot_delay=float(body.get("bot_delay", 0.8)),
            hints=bool(body.get("hints", True)))
        joined = room.join(body.get("name", "anon"))
        if joined is None:
            return self._json({"error": "could not seat the host"}, 500)
        return self._json({**joined, "code": room.code,
                           "state": room.view(joined["seat"])})

    def _room_get(self, path, query):
        from .lobby import lobby
        parts = path.strip("/").split("/")
        room = lobby().get(parts[2] if len(parts) > 2 else "")
        if room is None:
            return self._json({"error": "no such table"}, 404)
        q = parse_qs(query or "")
        token = (q.get("token") or [""])[0]
        seat = room.seat_of(token) if token else None
        if len(parts) > 3 and parts[3] == "analyse":
            if seat is None:
                return self._json({"error": "not seated at this table"}, 403)
            return self._json(room.analysis(seat))
        return self._json(room.view(seat))

    def _room_post(self, path, body):
        from .lobby import lobby
        parts = path.strip("/").split("/")
        room = lobby().get(parts[2] if len(parts) > 2 else "")
        if room is None:
            return self._json({"error": "no such table"}, 404)
        verb = parts[3] if len(parts) > 3 else ""
        if verb == "join":
            joined = room.join(body.get("name", "anon"))
            if joined is None:
                return self._json({"error": "this table is full"}, 409)
            return self._json({**joined, "code": room.code,
                               "state": room.view(joined["seat"])})
        token = body.get("token", "")
        seat = room.seat_of(token) if token else None
        if seat is None:
            return self._json({"error": "not seated at this table"}, 403)
        if verb == "act":
            try:
                act = _action_from(body)
            except Exception as e:
                return self._json({"error": f"bad action: {e}"}, 400)
            try:
                room.apply(seat, act)
            except Exception as e:
                return self._json({"error": str(e),
                                   "state": room.view(seat)}, 400)
            return self._json(room.view(seat))
        if verb == "pace":
            # Pacing is a property of the table, so any seated player may
            # change it; there is no host privilege to get wrong.
            room.pace(paused=body.get("paused"), delay=body.get("delay"),
                      skip=bool(body.get("skip")))
            return self._json(room.view(seat))
        if verb == "auto":
            if room.state is None or room.state.turn != seat:
                return self._json(room.view(seat))
            from ..registry4 import make_agent
            helper = room.bots.get(("helper", seat))
            if helper is None:
                helper = make_agent(("fishbot4",
                                     {"opponent_gamma": room.gamma}))
                helper.begin_game(seat, room.rules, seat * 104729 + 7)
                room.bots[("helper", seat)] = helper
            try:
                act = helper.act(Observation.from_state(room.state, seat))
                room.apply(seat, act)
            except Exception as e:
                return self._json({"error": str(e),
                                   "state": room.view(seat)}, 400)
            return self._json(room.view(seat))
        return self._json({"error": "not found"}, 404)

    cls._room_create = _room_create
    cls._room_get = _room_get
    cls._room_post = _room_post
    return cls


def _action_from(body: dict):
    kind = body.get("type")
    if kind == "ask":
        return Ask(int(body["target"]), int(body["card"]))
    if kind == "claim":
        return Claim(int(body["half_suit"]),
                     tuple(int(x) for x in body["assignment"]))
    if kind == "pass":
        return Pass(int(body["teammate"]))
    raise ValueError(f"unknown action {kind!r}")


_room_routes(Handler)


def serve(host: str = "127.0.0.1", port: int = 8420) -> int:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"\n  FishBot v0.4  ->  http://{host}:{port}\n"
          f"  (Ctrl-C to stop)\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    return 0
