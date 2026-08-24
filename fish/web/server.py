"""Fish simulation platform: a dependency-free HTTP server for watching and
running engine-vs-engine games in the browser.

Uses only the standard library (http.server + json), so the platform runs
anywhere Python does with no install step.

IMPORTANT: the browser is a SPECTATOR. It may display all six hands because
a viewer is not a policy. The agents themselves still receive nothing but
their own Observation; the server drives them through exactly the same
boundary as every other harness.

API
  GET  /api/agents                      list available policies
  POST /api/games                       {agents:[...], seed, variant, ...}
  GET  /api/games/<id>                  full state snapshot
  POST /api/games/<id>/step             {n} advance n actions
  POST /api/games/<id>/run              play to the end
  POST /api/games/<id>/analyze          {seat} engine analysis of a position
  GET  /api/games                       list live games
  POST /api/match                       {x, y, deals} paired-deal matchup
"""

from __future__ import annotations

import json
import random
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..agents import AGENT_REGISTRY
from ..cards import (HALF_SUIT_NAMES, card_long_name, card_name, deck_size,
                     half_suit_cards, is_red, mask_to_cards, num_half_suits)
from ..engine import AskEvent, ClaimEvent, GameState, PassEvent
from ..observation import Observation
from ..rules import RuleConfig

STATIC = Path(__file__).parent / "static"
ROOT = Path(__file__).resolve().parents[2]

_games: dict[str, "LiveGame"] = {}
_coaches: dict[str, object] = {}
_lock = threading.Lock()
_counter = [0]


class LiveGame:
    """A game the browser can step through. Agents see only Observations."""

    def __init__(self, agent_names: list[str], seed: int, rules: RuleConfig,
                 agent_kwargs: list[dict] | None = None):
        with _lock:
            self.id = f"g{_counter[0]}"
            _counter[0] += 1
        self.agent_names = agent_names
        self.rules = rules
        self.seed = seed
        self.state = GameState.deal(rules, seed=seed)
        self.initial_hands = list(self.state.hands)
        kwargs = agent_kwargs or [{} for _ in agent_names]
        self.agents = [AGENT_REGISTRY[n](**kw)
                       for n, kw in zip(agent_names, kwargs)]
        self.agent_seed = random.getrandbits(64)
        arng = random.Random(self.agent_seed)
        for p, ag in enumerate(self.agents):
            ag.begin_game(p, rules, arng.getrandbits(64))
        self.error: str | None = None

    def step(self, n: int = 1) -> list[dict]:
        events = []
        for _ in range(n):
            if self.state.is_terminal or self.error:
                break
            if len(self.state.history) > 20000:
                self.error = "game exceeded 20000 actions (livelock)"
                break
            p = self.state.turn
            try:
                obs = Observation.from_state(self.state, p)
                ev = self.state.apply(p, self.agents[p].act(obs))
            except Exception as e:      # keep the server alive, surface the bug
                self.error = f"{type(e).__name__}: {e}"
                traceback.print_exc()
                break
            events.append(event_dict(ev, len(self.state.history) - 1))
        return events

    def snapshot(self, reveal: bool = True) -> dict:
        st = self.state
        a, b, nul = st.scores()
        return {
            "id": self.id,
            "seed": self.seed,
            "agent_seed": str(self.agent_seed),
            "variant": self.rules.variant,
            "agents": self.agent_names,
            "turn": st.turn,
            "terminal": st.is_terminal,
            "error": self.error,
            "scores": {"team0": a, "team1": b, "null": nul},
            "hand_counts": list(st.hand_counts()),
            "set_winner": list(st.set_winner),
            "half_suits": [
                {"index": i, "name": HALF_SUIT_NAMES[i],
                 "cards": [card_payload(c) for c in half_suit_cards(i)],
                 "winner": st.set_winner[i]}
                for i in range(num_half_suits(self.rules.variant))
            ],
            # spectator view: a viewer is not a policy
            "hands": [[card_payload(c) for c in mask_to_cards(st.hands[p])]
                      for p in range(6)] if reveal else None,
            "history": [event_dict(ev, i) for i, ev in enumerate(st.history)],
            "winner": st.winner() if st.is_terminal else None,
        }


def card_payload(c: int) -> dict:
    return {"id": c, "name": card_name(c), "long": card_long_name(c),
            "red": is_red(c), "hs": c // 6}


def event_dict(ev, idx: int) -> dict:
    if isinstance(ev, AskEvent):
        return {"i": idx, "type": "ask", "asker": ev.asker, "target": ev.target,
                "card": card_payload(ev.card), "success": ev.success,
                "text": (f"P{ev.asker} asks P{ev.target} for "
                         f"{card_long_name(ev.card)}: "
                         f"{'got it' if ev.success else 'no'}")}
    if isinstance(ev, ClaimEvent):
        who = ("Team A" if ev.winner == 0 else "Team B" if ev.winner == 1
               else "nobody (null)")
        return {"i": idx, "type": "claim", "claimer": ev.claimer,
                "half_suit": ev.half_suit,
                "half_suit_name": HALF_SUIT_NAMES[ev.half_suit],
                "declared": list(ev.declared), "revealed": list(ev.revealed),
                "winner": ev.winner,
                "text": (f"P{ev.claimer} claims "
                         f"{HALF_SUIT_NAMES[ev.half_suit]}: {who}")}
    return {"i": idx, "type": "pass", "player": ev.player,
            "teammate": ev.teammate,
            "text": f"P{ev.player} passes to P{ev.teammate}"}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "FishPlatform/1.0"

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _json(self, obj, code: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    def _file(self, path: Path, ctype: str):
        if not path.exists():
            return self._json({"error": "not found"}, 404)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path
        try:
            if p in ("/", "/index.html"):
                return self._file(STATIC / "index.html",
                                  "text/html; charset=utf-8")
            if p == "/app.js":
                return self._file(STATIC / "app.js", "application/javascript")
            if p == "/style.css":
                return self._file(STATIC / "style.css", "text/css")
            if p == "/coach" or p == "/coach.html":
                return self._file(STATIC / "coach.html",
                                  "text/html; charset=utf-8")
            if p == "/coach.js":
                return self._file(STATIC / "coach.js", "application/javascript")
            if p == "/api/cards":
                from ..cards import CARD_NAMES, card_long_name, is_red
                return self._json({"cards": [
                    {"id": i, "name": n, "long": card_long_name(i),
                     "red": is_red(i), "hs": i // 6}
                    for i, n in enumerate(CARD_NAMES)]})
            if p == "/api/agents":
                return self._json({"agents": sorted(AGENT_REGISTRY)})
            if p == "/api/games":
                with _lock:
                    return self._json({"games": [
                        {"id": g.id, "agents": g.agent_names,
                         "terminal": g.state.is_terminal,
                         "actions": len(g.state.history)}
                        for g in _games.values()]})
            if p.startswith("/api/games/"):
                g = _games.get(p.split("/")[3])
                if not g:
                    return self._json({"error": "no such game"}, 404)
                return self._json(g.snapshot())
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            body = self._body()
            if p == "/api/games":
                return self._new_game(body)
            parts = p.split("/")
            if len(parts) >= 5 and parts[1] == "api" and parts[2] == "games":
                g = _games.get(parts[3])
                if not g:
                    return self._json({"error": "no such game"}, 404)
                verb = parts[4]
                if verb == "step":
                    events = g.step(max(1, min(int(body.get("n", 1)), 5000)))
                    return self._json({"events": events, "state": g.snapshot()})
                if verb == "run":
                    g.step(20000)
                    return self._json({"state": g.snapshot()})
                if verb == "analyze":
                    return self._json(
                        self._analyze(g, int(body.get("seat", g.state.turn))))
            if p == "/api/match":
                return self._match(body)
            if p == "/api/coach":
                return self._coach_new(body)
            if len(parts) >= 5 and parts[1] == "api" and parts[2] == "coach":
                return self._coach_action(parts[3], parts[4], body)
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def _new_game(self, body: dict):
        names = body.get("agents") or ["probabilistic"] * 6
        if len(names) != 6:
            return self._json({"error": "need exactly 6 agents"}, 400)
        for n in names:
            if n not in AGENT_REGISTRY:
                return self._json({"error": f"unknown agent {n}"}, 400)
        seed = body.get("seed")
        seed = random.randrange(1 << 30) if seed in (None, "") else int(seed)
        rules = RuleConfig(
            variant=body.get("variant", "54"),
            claims_any_time=bool(body.get("claims_any_time", False)),
            allow_bluff_asks=bool(body.get("allow_bluff_asks", False)),
            wrong_distribution_outcome=body.get(
                "wrong_distribution_outcome", "null"),
            starting_player=int(body.get("starting_player", 0)),
        )
        kwargs = [{"model_path": str(ROOT / "checkpoints" / "pi_value_v1.pt")}
                  if n == "value_search" else {} for n in names]
        g = LiveGame(names, seed, rules, agent_kwargs=kwargs)
        with _lock:
            _games[g.id] = g
            if len(_games) > 40:            # keep memory bounded
                for k in list(_games)[:-40]:
                    _games.pop(k, None)
        return self._json({"state": g.snapshot()})

    def _analyze(self, g: LiveGame, seat: int) -> dict:
        """Engine analysis of the live position, from that seat's legal view."""
        from ..agents import ValueSearchAgent
        from ..engine import Ask as _Ask, Claim as _Claim
        obs = Observation.from_state(g.state, seat)
        agent = ValueSearchAgent(
            model_path=str(ROOT / "checkpoints" / "pi_value_v1.pt"),
            n_worlds=12, n_candidates=6, n_samples=32)
        agent.begin_game(seat, g.rules, random.getrandbits(64))
        agent.bel.update(obs)
        worlds = [agent.bel.sample_current_hands(agent.rng) for _ in range(32)]
        n = len(worlds)
        rows = []
        for a in obs.legal_asks():
            hits = sum(1 for w in worlds if w[a.target] & (1 << a.card))
            rows.append({"kind": "ask", "target": a.target,
                         "card": card_payload(a.card), "p": hits / n,
                         "text": f"ask P{a.target} for {card_long_name(a.card)}"})
        rows.sort(key=lambda r: -r["p"])
        claims = []
        for prob, cl in sorted(agent._claim_candidates(obs, worlds),
                               key=lambda t: -t[0])[:4]:
            claims.append({"kind": "claim", "half_suit": cl.half_suit,
                           "half_suit_name": HALF_SUIT_NAMES[cl.half_suit],
                           "assignment": list(cl.assignment), "p": prob,
                           "text": f"claim {HALF_SUIT_NAMES[cl.half_suit]}"})
        beliefs = []
        for c in range(deck_size(g.rules.variant)):
            if obs.set_winner[c // 6] is not None or obs.hand & (1 << c):
                continue
            probs = [0.0] * 6
            for w in worlds:
                for pl in range(6):
                    if w[pl] & (1 << c):
                        probs[pl] += 1 / n
            beliefs.append({"card": card_payload(c), "probs": probs,
                            "certainty": max(probs)})
        beliefs.sort(key=lambda b: -b["certainty"])
        best = None
        try:
            action = agent.act(obs)
            if isinstance(action, _Ask):
                best = f"ASK P{action.target} for {card_long_name(action.card)}"
            elif isinstance(action, _Claim):
                best = f"CLAIM {HALF_SUIT_NAMES[action.half_suit]}"
            else:
                best = str(action)
        except Exception:
            best = None
        return {"seat": seat, "best": best, "asks": rows[:12],
                "claims": claims, "beliefs": beliefs[:16],
                "uses_model": agent.uses_model}

    # -- live coaching ------------------------------------------------------

    def _coach_new(self, body: dict):
        from ..coach import CoachError, CoachSession
        try:
            s = CoachSession.create(
                seat=int(body.get("seat", 0)),
                hand_names=body.get("hand") or [],
                variant=body.get("variant", "54"),
                starting_player=int(body.get("starting_player", 0)))
        except CoachError as e:
            return self._json({"error": str(e)}, 400)
        with _lock:
            s.id = f"c{_counter[0]}"
            _counter[0] += 1
            _coaches[s.id] = s
            if len(_coaches) > 60:
                for k in list(_coaches)[:-60]:
                    _coaches.pop(k, None)
        return self._json({"id": s.id, "state": s.advise(
            engine=body.get("engine"))})

    def _coach_action(self, cid: str, verb: str, body: dict):
        from ..coach import CoachError
        s = _coaches.get(cid)
        if s is None:
            return self._json({"error": "That coaching session has expired; "
                                        "start a new one."}, 404)
        engine = body.get("engine")
        try:
            if verb == "ask":
                s.add_ask(int(body["asker"]), int(body["target"]),
                          str(body["card"]), bool(body["success"]))
            elif verb == "claim":
                s.add_claim(int(body["claimer"]), int(body["half_suit"]),
                            [int(h) for h in body["holders"]],
                            body.get("winner"),
                            bool(body.get("nulled", False)))
            elif verb == "pass":
                s.add_pass(int(body["player"]), int(body["teammate"]))
            elif verb == "undo":
                s.undo()
            elif verb == "state":
                pass
            else:
                return self._json({"error": "unknown action"}, 404)
        except CoachError as e:
            return self._json({"error": str(e)}, 400)
        except (KeyError, ValueError, TypeError):
            return self._json({"error": "Missing or malformed fields for "
                                        f"'{verb}'."}, 400)
        return self._json({"id": cid, "state": s.advise(engine=engine)})

    def _match(self, body: dict):
        from ..eval.tournament import play_matchup
        x = body.get("x", "memory")
        y = body.get("y", "probabilistic")
        if x not in AGENT_REGISTRY or y not in AGENT_REGISTRY:
            return self._json({"error": "unknown policy"}, 400)
        deals = max(2, min(int(body.get("deals", 20)), 200))
        stats = play_matchup((x, {}), (y, {}), n_deals=deals, n_jobs=4)
        m, lo, hi = stats.diff_mean_ci()
        wlo, whi = stats.wilson_ci()
        return self._json({
            "x": x, "y": y, "pairs": stats.n_pairs,
            "pair_score": stats.pair_score(), "ci": [wlo, whi],
            "set_diff": m, "set_diff_ci": [lo, hi],
            "record": [stats.x_pair_wins, stats.pair_ties, stats.y_pair_wins],
            "nulls": stats.null_sets,
        })


def serve(host: str = "127.0.0.1", port: int = 8777) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Fish platform running at http://{host}:{port}")
    print("  Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
