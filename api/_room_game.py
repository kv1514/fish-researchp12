"""What a room IS, and what each player at it is allowed to see.

A room document is small on purpose. It holds the deal nonce, the public action
log, the six seats and who has pressed ready -- and nothing derived. Every view
is rebuilt from that by the same ``Session`` the solo build uses, so there is
one implementation of "what does seat 3 know" rather than two that can drift.

THREE RULES THAT ARE NOT COSMETIC
---------------------------------
**Nobody joins a game in progress.** A player who arrives mid-deal would have to
reconstruct the tracking from a log, which is exactly the work the interface
exists to spare them. So a room is either seating or playing, and joining is
only possible while seating.

**The deal waits for everyone.** Ready is per-seat and the deal needs all of
them. A host who could start early would be starting a game somebody had not
finished naming themselves in.

**Seats are a team decision.** Teams in Literature are {0,2,4} against {1,3,5},
so "three of us against three bots" is a statement about which seats the people
take and cannot be expressed any other way. People fill one team first, so a
group that turns up together plays together.

WHO STARTS
----------
With one human at the table, that human. A player whose first experience of a
game is watching four engine possessions has been given a puzzle instead of a
turn. With more than one, the seat that has been waiting longest -- the host --
because somebody has to and "whoever created the table" is the least arbitrary
rule available.
"""

from __future__ import annotations

import secrets
import time

from fish.cards import NUM_PLAYERS, team_of

from api._rooms import Conflict, NotFound, clean_name, store
from api._engine import CHAMPION_GAMMA, Session
from fish.rules import RuleConfig

#: Seat fill order. People take one team first ({0,2,4}), then the other, so a
#: group of three that turns up together is a team rather than being scattered.
TEAM_FIRST_ORDER = [0, 2, 4, 1, 3, 5]

#: Bounds on how long a table waits between engine moves. Zero is allowed --
#: some tables want it instant -- and the ceiling stops a typo parking a room.
MIN_PACE, MAX_PACE = 0.0, 60.0

MAX_PLAYERS_REQUESTED = NUM_PLAYERS

#: Default names for bot seats, matching public/names.js so a bot is called the
#: same thing whichever screen names it.
BOT_NAMES = ["Marlin", "Nori", "Coral", "Reef", "Tide"]


def _bot_default(i: int) -> str:
    return BOT_NAMES[i % len(BOT_NAMES)]


def new_room(humans: int, host_name: str, pace: float) -> dict:
    """A fresh seating room. No deal is made until everyone is ready."""
    humans = max(1, min(MAX_PLAYERS_REQUESTED, int(humans)))
    pace = max(MIN_PACE, min(MAX_PACE, float(pace)))
    people = TEAM_FIRST_ORDER[:humans]
    seats = []
    bot_i = 0
    for p in range(NUM_PLAYERS):
        if p in people:
            seats.append({"seat": p, "kind": "human", "name": "",
                          "secret": None, "ready": False})
        else:
            seats.append({"seat": p, "kind": "bot",
                          "name": _bot_default(bot_i), "secret": None,
                          "ready": True})
            bot_i += 1
    now = time.time()
    doc = {
        "phase": "seating",
        "seats": seats,
        "humans": humans,
        "pace": pace,
        # Never sent to any client. The deal is derived from it, so a client
        # holding it holds every hand.
        "nonce": secrets.token_urlsafe(12),
        "log": [],
        "start_seat": 0,
        "created": now,
        "touched": now,
        # Earliest wall-clock time the next engine move may be applied. The
        # pace belongs to the ROOM, not to whichever client asks first: any
        # player could otherwise poll `room_step` in a loop and rush the table
        # past everybody else's reading speed, which is the one thing the
        # pacing exists to prevent.
        "next_move_at": 0.0,
    }
    # The host takes the first people-seat immediately, so a room always has
    # somebody in it and cannot be created empty and abandoned with a code.
    join_room(doc, host_name)
    return doc


def join_room(doc: dict, name: str) -> dict:
    """Seat a person. Returns ``{"seat", "secret"}``.

    The secret is the player's proof that they are that seat. It is generated
    here and returned once; every later request carries it, and it is the only
    thing standing between a player and acting as somebody else.
    """
    if doc.get("phase") != "seating":
        raise ValueError("that table has already started")
    for s in doc["seats"]:
        if s["kind"] == "human" and not s["secret"]:
            s["secret"] = secrets.token_urlsafe(16)
            s["name"] = clean_name(name, "")
            doc["touched"] = time.time()
            return {"seat": s["seat"], "secret": s["secret"]}
    raise ValueError("that table is full")


def seat_of(doc: dict, secret: str):
    if not secret:
        return None
    for s in doc["seats"]:
        if s["kind"] == "human" and s["secret"] and s["secret"] == secret:
            return s["seat"]
    return None


def rename(doc: dict, secret: str, seat: int, name: str) -> None:
    """Rename a seat.

    Anybody at the table may rename a BOT -- they are shared furniture, and the
    alternative is that only the host can make the table readable. Only the
    occupant may rename a person, because a seat label is how the others
    identify who acted, and letting one player relabel another is letting them
    misattribute moves.
    """
    me = seat_of(doc, secret)
    if me is None:
        raise ValueError("you are not seated at that table")
    if doc.get("phase") != "seating":
        raise ValueError("names are fixed once the deal starts")
    seat = int(seat) % NUM_PLAYERS
    target = doc["seats"][seat]
    if target["kind"] == "human" and seat != me:
        raise ValueError("you can only rename yourself")
    target["name"] = clean_name(
        name, _bot_default(seat) if target["kind"] == "bot" else "")
    doc["touched"] = time.time()


def set_ready(doc: dict, secret: str, ready: bool) -> None:
    me = seat_of(doc, secret)
    if me is None:
        raise ValueError("you are not seated at that table")
    doc["seats"][me]["ready"] = bool(ready)
    doc["touched"] = time.time()


def everyone_ready(doc: dict) -> bool:
    """Every people-seat filled and ready. Bots are ready by construction."""
    for s in doc["seats"]:
        if s["kind"] != "human":
            continue
        if not s["secret"] or not s["ready"]:
            return False
    return True


def maybe_start(doc: dict) -> bool:
    """Deal, if the table is full and ready. Returns whether it dealt."""
    if doc.get("phase") != "seating" or not everyone_ready(doc):
        return False
    humans = [s["seat"] for s in doc["seats"] if s["kind"] == "human"]
    # One human: they start, so the game opens on a decision of theirs rather
    # than on four engine possessions they then have to reconstruct.
    # More than one: the host, who is the first people-seat.
    doc["start_seat"] = humans[0] if humans else 0
    doc["phase"] = "playing"
    doc["touched"] = time.time()
    # Give the table one pace-length before the first engine move, so a player
    # who has just pressed Ready gets a moment to look at their hand.
    doc["next_move_at"] = time.time() + float(doc.get("pace") or 0)
    return True


def is_bot_turn(doc: dict) -> bool:
    if doc.get("phase") != "playing":
        return False
    s = session_for(doc, 0)
    if s.state.is_terminal:
        return False
    return doc["seats"][s.state.turn]["kind"] == "bot"


def step_bot(doc: dict) -> int:
    """Apply at most one engine move, if one is due. Returns moves applied.

    Returns 0 rather than raising when it is not yet time, when it is a
    person's turn, or when the game is over -- every client polls this, so
    "nothing to do" is the common case and not an error.
    """
    if doc.get("phase") != "playing":
        return 0
    now = time.time()
    if now < float(doc.get("next_move_at") or 0):
        return 0
    seat = int(doc["start_seat"])
    s = session_for(doc, seat)
    if s.state.is_terminal or doc["seats"][s.state.turn]["kind"] != "bot":
        return 0
    played = s.advance(1)
    if not played:
        return 0
    doc["log"] = list(s.wire_log)
    doc["next_move_at"] = now + float(doc.get("pace") or 0)
    doc["touched"] = now
    return len(played)


def apply_action(doc: dict, seat: int, action) -> None:
    """Apply a person's action. Raises if it is not their turn."""
    if doc.get("phase") != "playing":
        raise ValueError("that table has not started")
    s = session_for(doc, seat)
    if s.state.is_terminal:
        raise ValueError("that game is over")
    if s.state.turn != seat:
        raise ValueError("not your turn")
    s.play(action, max_moves=0)
    doc["log"] = list(s.wire_log)
    # A person's move resets the engine clock, so the table pauses for the
    # pace AFTER a human acts rather than firing a bot move instantly on top
    # of it -- which would make the human's own move unreadable.
    doc["next_move_at"] = time.time() + float(doc.get("pace") or 0)
    doc["touched"] = time.time()


def session_for(doc: dict, seat: int) -> Session:
    """Rebuild the game from the room document, viewed from ``seat``.

    The same Session the solo build uses, so ``snapshot()`` applies one
    definition of what a seat may see. A second implementation here would be a
    second chance to leak a hand.
    """
    rules = RuleConfig(variant="54", starting_player=int(doc["start_seat"]))
    s = Session(int(seat), str(doc["nonce"]), rules, CHAMPION_GAMMA)
    log = list(doc.get("log") or [])
    if log:
        from api._engine import _action_of, narrate
        s.wire_log = log
        for a in log:
            ev = s.state.apply(s.state.turn, _action_of(a))
            s.log.append(narrate(ev))
    return s


def public_seats(doc: dict, me) -> list:
    """The seat list as any player may see it. Secrets never appear."""
    out = []
    bot_i = 0
    for s in doc["seats"]:
        kind = s["kind"]
        name = s["name"]
        if kind == "bot":
            name = name or _bot_default(bot_i)
            bot_i += 1
        out.append({
            "seat": s["seat"],
            "kind": kind,
            "name": name,
            "team": team_of(s["seat"]),
            "taken": kind == "bot" or bool(s["secret"]),
            "ready": bool(s["ready"]) if kind == "human" else True,
            "me": s["seat"] == me,
        })
    return out


def lobby_view(doc: dict, code: str, me) -> dict:
    seats = public_seats(doc, me)
    waiting = [s for s in seats if s["kind"] == "human" and not s["taken"]]
    return {
        "phase": doc["phase"],
        "code": code,
        # Seconds until the next engine move may fire. The client renders a
        # countdown from this rather than running its own clock, so every
        # player at the table sees the same number.
        "next_in": max(0.0, float(doc.get("next_move_at") or 0) - time.time()),
        "seat": me,
        "pace": doc.get("pace", 12.0),
        "seats": seats,
        "names": [s["name"] for s in seats],
        "waiting_for": len(waiting),
        "ready_count": sum(1 for s in seats
                           if s["kind"] == "human" and s["taken"]
                           and s["ready"]),
        "human_count": sum(1 for s in seats if s["kind"] == "human"),
    }


def table_view(doc: dict, code: str, me: int) -> dict:
    """A playing room, from one seat. Lobby metadata plus the game snapshot."""
    s = session_for(doc, me)
    snap = s.snapshot()
    # The room's own token is meaningless to a room client -- the server holds
    # the authoritative log -- and handing one over would invite a client to
    # replay a room position as a solo game with a log of its choosing.
    snap.pop("token", None)
    snap["room"] = lobby_view(doc, code, me)
    snap["names"] = snap["room"]["names"]
    return snap


# ---------------------------------------------------------------------------
# Store-level operations, each retried on a lost race
# ---------------------------------------------------------------------------

RETRIES = 4


def mutate(code: str, fn):
    """Read, apply ``fn(doc)``, write. Retries a compare-and-set conflict.

    Two players acting in the same instant is ordinary, not exceptional: one of
    them re-reads and re-applies. What must never happen is the write silently
    winning and dropping the other player's move, which is what a
    last-write-wins store would do.
    """
    st = store()
    last = None
    for _ in range(RETRIES):
        version, doc = st.read(code)
        out = fn(doc)
        try:
            st.write(code, version, doc)
            return doc, out
        except Conflict as e:
            last = e
            continue
    raise RuntimeError("the table is busy; try that again") from last
