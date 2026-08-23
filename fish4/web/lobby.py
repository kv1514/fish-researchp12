"""Rooms, matchmaking and bot seats for online Literature.

Six seats, any mixture of people and engines. The two things that make this a
lobby rather than a game loop:

**Seating is a team decision, not a cosmetic one.** Teams in Literature are the
alternating seats {0,2,4} against {1,3,5}, so "three of us against three bots"
is only expressible as a seating constraint. ``arrangement="one_team"`` puts the
humans on consecutive same-team seats, which is what somebody asking for 3v3
means; ``arrangement="alternate"`` mixes them, which is what you want when four
friends turn up and two engines fill in.

**Bots move on a clock, not instantly.** A bot decision costs about 4ms, which
would make an engine's whole possession appear as a single jump. Bot moves are
therefore paced (``bot_delay``) so a human can follow what happened, and a
single daemon thread drives every room rather than a thread per game.

Concurrency: one lock guards the whole lobby. Games are tiny and moves are
milliseconds, so there is nothing to gain from finer granularity and a great
deal to lose from getting it wrong.
"""

from __future__ import annotations

import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from fish.cards import (HALF_SUIT_NAMES, NUM_PLAYERS, card_name,
                        half_suit_cards, is_red, mask_to_cards, team_of,
                        teammates)
from fish.engine import (Ask, AskEvent, Claim, ClaimEvent, GameState, Pass,
                         PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig

#: seats in the order a "one team first" arrangement fills them
ONE_TEAM_ORDER = [0, 2, 4, 1, 3, 5]
ALTERNATE_ORDER = [0, 1, 2, 3, 4, 5]

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1


def _code(n: int = 4) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def event_dict(ev) -> dict:
    if isinstance(ev, AskEvent):
        return {"t": "ask", "asker": ev.asker, "target": ev.target,
                "card": ev.card, "card_name": card_name(ev.card),
                "ok": bool(ev.success)}
    if isinstance(ev, ClaimEvent):
        return {"t": "claim", "claimer": ev.claimer, "hs": ev.half_suit,
                "hs_name": HALF_SUIT_NAMES[ev.half_suit], "winner": ev.winner,
                "revealed": [{"card": c, "card_name": card_name(c), "holder": h}
                             for c, h in zip(half_suit_cards(ev.half_suit),
                                             ev.revealed)]}
    return {"t": "pass", "player": ev.player, "teammate": ev.teammate}


@dataclass
class Seat:
    index: int
    kind: str = "bot"            # "human" | "bot"
    name: str = "engine"
    token: Optional[str] = None
    connected_at: float = 0.0
    last_seen: float = 0.0

    def public(self) -> dict:
        return {"seat": self.index, "kind": self.kind, "name": self.name,
                "team": team_of(self.index)}


class Room:
    """One table: six seats, a game, and a log."""

    def __init__(self, humans: int, arrangement: str, host_name: str,
                 rules: RuleConfig, seed: Optional[int], gamma: float,
                 bot_delay: float, hints: bool):
        humans = max(1, min(6, int(humans)))
        self.code = _code()
        self.rules = rules
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.gamma = gamma
        self.bot_delay = max(0.0, float(bot_delay))
        self.hints = bool(hints)
        self.arrangement = ("one_team" if arrangement == "one_team"
                            else "alternate")
        order = (ONE_TEAM_ORDER if self.arrangement == "one_team"
                 else ALTERNATE_ORDER)
        self.human_seats = sorted(order[:humans])
        self.seats = [Seat(i) for i in range(NUM_PLAYERS)]
        for i in self.human_seats:
            self.seats[i].kind = "human"
            self.seats[i].name = "waiting..."
        self.state: Optional[GameState] = None
        self.bots: dict = {}
        self.analysers: dict = {}
        self.log: list = []
        self.status = "waiting"          # waiting | playing | finished
        self.version = 0
        self.created = time.time()
        self.updated = time.time()
        self.next_bot_at = 0.0
        self.host_name = host_name

    # -- seating ---------------------------------------------------------------

    @property
    def open_seats(self) -> list:
        return [i for i in self.human_seats if self.seats[i].token is None]

    def join(self, name: str) -> Optional[dict]:
        free = self.open_seats
        if not free:
            return None
        i = free[0]
        s = self.seats[i]
        s.token = secrets.token_hex(8)
        s.name = (name or f"Player {i}").strip()[:24]
        s.connected_at = s.last_seen = time.time()
        self.touch()
        if not self.open_seats:
            self.start()
        return {"seat": i, "token": s.token}

    def seat_of(self, token: str) -> Optional[int]:
        for s in self.seats:
            if s.token and secrets.compare_digest(s.token, token):
                s.last_seen = time.time()
                return s.index
        return None

    # -- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        from ..registry4 import make_agent
        self.state = GameState.deal(self.rules, seed=self.seed)
        rng = random.Random(self.seed ^ 0x5EED)
        spec = {"opponent_gamma": self.gamma}
        for i in range(NUM_PLAYERS):
            if self.seats[i].kind != "bot":
                continue
            self.seats[i].name = f"FishBot {i}"
            b = make_agent(("fishbot4", dict(spec)))
            b.begin_game(i, self.rules, rng.getrandbits(64))
            self.bots[i] = b
        self.status = "playing"
        self.next_bot_at = time.time() + self.bot_delay
        self.touch()

    def touch(self) -> None:
        self.version += 1
        self.updated = time.time()

    # -- play -------------------------------------------------------------------

    def apply(self, seat: int, action) -> None:
        if self.status != "playing":
            raise ValueError("this table is not playing")
        if self.state.turn != seat:
            raise ValueError("it is not your turn")
        ev = self.state.apply(seat, action)
        self.log.append(event_dict(ev))
        if self.state.is_terminal:
            self.status = "finished"
        self.next_bot_at = time.time() + self.bot_delay
        self.touch()

    def step_bot(self) -> bool:
        """Advance one bot move if one is due. Returns True if it moved."""
        if self.status != "playing" or self.state is None:
            return False
        turn = self.state.turn
        if self.seats[turn].kind != "bot":
            return False
        if time.time() < self.next_bot_at:
            return False
        bot = self.bots.get(turn)
        if bot is None:
            return False
        try:
            action = bot.act(Observation.from_state(self.state, turn))
            ev = self.state.apply(turn, action)
        except Exception:
            # A bot that cannot move must not wedge the table; skip its turn by
            # letting the game engine's own legality error surface as a pass.
            self.status = "finished"
            self.touch()
            return False
        self.log.append(event_dict(ev))
        if self.state.is_terminal:
            self.status = "finished"
        self.next_bot_at = time.time() + self.bot_delay
        self.touch()
        return True

    # -- views --------------------------------------------------------------------

    def lobby_view(self) -> dict:
        return {
            "code": self.code, "status": self.status,
            "host": self.host_name, "arrangement": self.arrangement,
            "humans": len(self.human_seats),
            "bots": NUM_PLAYERS - len(self.human_seats),
            "seats_open": len(self.open_seats),
            "players": [s.name for s in self.seats if s.kind == "human"
                        and s.token],
            "age": int(time.time() - self.created),
        }

    def view(self, seat: Optional[int]) -> dict:
        """Everything ``seat`` may legally see. ``seat=None`` is the waiting
        room view, which contains no cards at all."""
        base = {
            "code": self.code, "status": self.status, "version": self.version,
            "seat": seat, "seed": self.seed,
            "arrangement": self.arrangement,
            "seats": [s.public() for s in self.seats],
            "open_seats": self.open_seats,
            "bot_delay": self.bot_delay, "hints": self.hints,
            "half_suit_names": list(HALF_SUIT_NAMES),
        }
        if self.state is None or seat is None:
            base.update({"log": [], "hand": [], "your_turn": False})
            return base
        st = self.state
        a, b, nulls = st.scores()
        mine = team_of(seat)
        hand = st.hands[seat]
        base.update({
            "turn": st.turn,
            "your_turn": self.status == "playing" and st.turn == seat,
            "team": mine,
            "teammates": [p for p in teammates(seat) if p != seat],
            "score": {"you": a if mine == 0 else b,
                      "them": b if mine == 0 else a, "nulled": nulls},
            "hand_counts": list(st.hand_counts()),
            "set_winner": [
                None if w is None else
                ("ours" if w == mine else "theirs" if w in (0, 1) else "null")
                for w in st.set_winner],
            "hand": [{"id": c, "name": card_name(c), "red": is_red(c),
                      "hs": c // 6} for c in mask_to_cards(hand)],
            "askable": self._askable(st, seat),
            "log": self.log[-60:],
            "must_pass": bool(st.turn == seat and hand == 0
                              and self.status == "playing"),
            "reveal": ([[card_name(c) for c in mask_to_cards(h)]
                        for h in st.hands] if self.status == "finished"
                       else None),
        })
        return base

    def _askable(self, st, seat) -> list:
        """The legal asks, grouped for the UI: which half-suits this seat may
        ask in and which cards of them are askable."""
        if st.turn != seat or self.status != "playing":
            return []
        out = []
        hand = st.hands[seat]
        for hs in range(len(st.set_winner)):
            if st.set_winner[hs] is not None:
                continue
            cards = list(half_suit_cards(hs))
            if not any(hand >> c & 1 for c in cards):
                continue
            out.append({
                "hs": hs, "name": HALF_SUIT_NAMES[hs],
                "cards": [{"id": c, "name": card_name(c), "red": is_red(c)}
                          for c in cards if not (hand >> c & 1)],
            })
        return out

    def analysis(self, seat: int) -> dict:
        if not self.hints:
            return {"disabled": True,
                    "note": "hints are switched off for this table"}
        if self.state is None or self.status != "playing":
            return {"terminal": True}
        an = self.analysers.get(seat)
        if an is None:
            from ..analyse import Analyser
            from ..cli import _load_value
            an = self.analysers[seat] = Analyser(
                self.rules, seat, value_model=_load_value(None),
                gamma=self.gamma, n_draws=192, seed=seat * 7919 + 13)
        return an.analyse(Observation.from_state(self.state, seat)).to_dict()


class Lobby:
    """All rooms, plus the clock that moves the bots."""

    def __init__(self, tick: float = 0.15, ttl: float = 7200.0):
        self.rooms: dict = {}
        self.lock = threading.RLock()
        self.tick = tick
        self.ttl = ttl
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- the clock -----------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.wait(self.tick):
            try:
                with self.lock:
                    now = time.time()
                    for code in list(self.rooms):
                        room = self.rooms[code]
                        if now - room.updated > self.ttl:
                            del self.rooms[code]
                            continue
                        room.step_bot()
            except Exception:
                pass          # a wedged room must not kill the clock

    def stop(self) -> None:
        self._stop.set()

    # -- api ------------------------------------------------------------------

    def create(self, humans: int, arrangement: str, name: str,
               rules: RuleConfig, seed=None, gamma: float = 0.35,
               bot_delay: float = 0.8, hints: bool = True) -> Room:
        with self.lock:
            room = Room(humans, arrangement, name or "anon", rules, seed,
                        gamma, bot_delay, hints)
            self.rooms[room.code] = room
            return room

    def get(self, code: str) -> Optional[Room]:
        with self.lock:
            return self.rooms.get((code or "").strip().upper())

    def listing(self) -> list:
        with self.lock:
            rooms = [r for r in self.rooms.values()
                     if r.status == "waiting" or
                     (r.status == "playing" and time.time() - r.updated < 900)]
            rooms.sort(key=lambda r: (r.status != "waiting", -r.created))
            return [r.lobby_view() for r in rooms[:40]]


LOBBY: Optional[Lobby] = None


def lobby() -> Lobby:
    global LOBBY
    if LOBBY is None:
        LOBBY = Lobby()
    return LOBBY
